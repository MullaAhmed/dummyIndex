"""Pure matching, gating, scanning and ranking of upstream specialist skills.

No I/O: callers fetch text and repo metadata (see :mod:`.sources`) and pass
them in. Trust comes from the repo, never from the skill name.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .discover import capabilities_for
from .marketplace import PluginEntry
from .sources import RepoMeta

_WORD_RE = re.compile(r"[a-z0-9]+")
_MAX_BYTES = 64 * 1024
# Keeps newlines so per-line patterns (pipe-to-shell, iex+iwr) stay line-scoped.
_HSPACE_RE = re.compile(r"[^\S\n]+")
_WS_RE = re.compile(r"\s+")

_INJECTION_MARKERS: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous",
    "ignore the above instructions",
    "disregard prior instructions",
    "disregard previous instructions",
    "disregard all previous",
    "forget previous instructions",
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
)
# Bounded repeats keep scans linear on hostile 64 KiB input (no quadratic backtracking).
_PIPE_RE = re.compile(
    r"\b(?:curl|wget)\b[^|\n]{0,400}\|\s{0,8}(?:sudo\s{1,8})?(?:ba|z|da)?sh\b"
)
_IEX_RE = re.compile(r"\b(?:iex|invoke-expression)\b")
_IWR_RE = re.compile(r"\b(?:iwr|irm|invoke-webrequest|invoke-restmethod)\b")
_REMOTE_IMAGE_RE = re.compile(
    r"!\[[^\]\n]{0,400}\]\(\s{0,8}<?\s{0,8}(?:https?:|data:)"
    r"|<img\b[^>]{0,400}\bsrc\s{0,8}=\s{0,8}[\"']?\s{0,8}(?:https?:|data:)"
)
_URL_RE = re.compile(r"https?://")
_SCRIPT_RE = re.compile(r"\bscripts/|\w\.(?:sh|py|ps1)\b")

# Extra sourcing-local tokens; the global capability table is left unchanged.
_EXTRA_TOKENS: dict[str, tuple[str, ...]] = {
    "api": ("api", "rest", "graphql", "endpoint", "openapi"),
    "migration": ("migration", "migrate"),
    "ci": ("ci", "cicd"),
}


@dataclass(frozen=True)
class SkillCandidate:
    """One upstream SKILL.md candidate with its provenance and gate inputs."""

    repo: str
    skill: str
    path: str
    channel: str
    marketplace: str
    trusted: bool
    installs: int | None = None
    meta: RepoMeta | None = None
    ref: str | None = None
    text: str | None = None
    description: str = ""


def lf(text: str) -> str:
    """Normalize CR and CRLF line endings to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _has_invisible(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if (
            0x200B <= cp <= 0x200F
            or 0x202A <= cp <= 0x202E
            or 0x2060 <= cp <= 0x2064
            or 0x2066 <= cp <= 0x2069
            or 0xE0000 <= cp <= 0xE007F
        ):
            return True
    # A leading BOM is file encoding noise; a BOM anywhere later is a hiding spot.
    return "\ufeff" in text[1:]


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split a SKILL.md into ``(description, body)``; ``None`` when unfenced."""
    text = lf(text)
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---\n"):
        return None
    pos = 4
    fm_lines: list[str] = []
    while True:
        nl = text.find("\n", pos)
        line = text[pos:] if nl == -1 else text[pos:nl]
        if line == "---":
            body = "" if nl == -1 else text[nl + 1 :]
            break
        if nl == -1:
            return None
        fm_lines.append(line)
        pos = nl + 1
    description = ""
    for line in fm_lines:
        if line.startswith("description:"):
            value = line[len("description:") :].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            description = value
            break
    return description, body


def scan_body(text: str) -> tuple[str, ...]:
    """Return sorted unique scan codes for a full upstream file, frontmatter included."""
    codes: set[str] = set()
    if _has_invisible(text):
        codes.add("block:invisible-unicode")
    if len(text.encode("utf-8")) > _MAX_BYTES:
        codes.add("block:oversize")
    parts = split_frontmatter(text)
    if parts is None:
        codes.add("block:bad-frontmatter")
    body = parts[1] if parts is not None else text
    if not body.strip():
        codes.add("block:empty")

    norm = unicodedata.normalize("NFKC", lf(text)).lower()
    lines_norm = _HSPACE_RE.sub(" ", norm)
    flat = _WS_RE.sub(" ", norm)
    if any(marker in flat for marker in _INJECTION_MARKERS):
        codes.add("block:injection")
    if _PIPE_RE.search(lines_norm) or any(
        _IEX_RE.search(line) and _IWR_RE.search(line) for line in lines_norm.split("\n")
    ):
        codes.add("block:pipe-to-shell")
    if "<!--" in norm:
        codes.add("block:html-comment")
    if _REMOTE_IMAGE_RE.search(norm):
        codes.add("block:remote-image")
    if _URL_RE.search(norm):
        codes.add("warn:url")
    if _SCRIPT_RE.search(norm):
        codes.add("warn:script")
    return tuple(sorted(codes))


def matches(skill: str, description: str, capability: str) -> bool:
    """True when the skill serves ``capability`` by table or sourcing-local tokens."""
    if capability in capabilities_for(PluginEntry(name=skill, description=description)):
        return True
    words = set(_WORD_RE.findall(f"{skill} {description}".lower()))
    return any(
        t in words or f"{t}s" in words for t in _EXTRA_TOKENS.get(capability, ())
    )


def gate_reason(c: SkillCandidate) -> str | None:
    """Return why a candidate is rejected, or ``None`` when it qualifies."""
    if c.ref is None:
        return "no sha"
    if c.meta is None:
        return "no repo meta"
    if c.meta.license in (None, "", "NOASSERTION"):
        return "no license"
    if c.meta.archived:
        return "archived"
    if c.text is None:
        return "not fetched"
    blocks = [code for code in scan_body(c.text) if code.startswith("block:")]
    if blocks:
        return ", ".join(blocks)
    return None


def qualifies(c: SkillCandidate) -> bool:
    """True when the candidate passes every gate."""
    return gate_reason(c) is None


def toolchain_hits(c: SkillCandidate, toolchain: tuple[str, ...]) -> int:
    """Count distinct toolchain words appearing in the skill name or description."""
    words = set(_WORD_RE.findall(f"{c.skill} {c.description}".lower()))
    return len({t.lower() for t in toolchain} & words)


def rank(
    cands: tuple[SkillCandidate, ...] | list[SkillCandidate],
    capability: str,
    toolchain: tuple[str, ...],
) -> tuple[SkillCandidate, ...]:
    """Gate, match, then rank candidates; return at most three."""
    pool = [
        c for c in cands if qualifies(c) and matches(c.skill, c.description, capability)
    ]
    # Stable sort: the first pass fixes the (repo, skill) tiebreak under reverse=True.
    pool.sort(key=lambda c: (c.repo, c.skill))
    pool.sort(
        key=lambda c: (
            c.trusted,
            toolchain_hits(c, toolchain),
            c.installs or 0,
            c.meta.stars,
            c.meta.pushed_at,
        ),
        reverse=True,
    )
    return tuple(pool[:3])


def needs_approval(c: SkillCandidate, codes: tuple[str, ...]) -> bool:
    """True when adoption needs ``--yes``: untrusted repo or any ``warn:`` code."""
    return not c.trusted or any(x.startswith("warn:") for x in codes)
