"""Doc word-budget ratchet: measure, read, check, update, reseed. Pure, root-injectable."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from pathlib import Path

from ..atomic_io import write_text_atomic
from .constants import (
    CONTEXT_CEILING,
    RATCHET_SEPARATOR,
    SKILLS_CEILING,
    STE_RULESET_VERSION,
    STYLE_CEILING,
)
from .enums import BudgetGroup
from .models import BudgetViolation, UpdateResult
from .style import count_violations

__all__ = [
    "check",
    "format_ratchet",
    "measure",
    "read_ratchet",
    "read_ratchet_ruleset",
    "reseed",
    "reseed_stale_style",
    "scan",
    "update_ratchet",
    "write_ratchet",
]

_CONTEXT_GLOBS = (
    ".context/features/*/spec.md",
    ".context/features/*/plan.md",
    ".context/features/*/concerns.md",
    ".context/PROJECT.md",
    ".context/architecture/overview.md",
    ".context/conventions/*.md",
)
# Style scope: curated docs plus workspace proposals and audits. session-memory is not linted.
_STYLE_GLOBS = (
    ".context/features/*/spec.md",
    ".context/features/*/plan.md",
    ".context/features/*/concerns.md",
    ".context/features/*/flows/*.md",
    ".context/conventions/*.md",
    ".context/playbooks/*.md",
    ".context/PROJECT.md",
    ".context/architecture/*.md",
    ".context/proposals/*/*.md",
    ".context/audits/**/*.md",
)
# Generated docs: rebuild rewrites them, so they carry no ratchet entry.
_STYLE_EXEMPT_GLOBS = (
    ".context/HOW_TO_USE.md",
    ".context/INDEX.md",
    ".context/conventions/naming.md",
    ".context/equipment/*.md",
)
_SKILLS_DIR = "dummyindex/skills"
_SKILL_NAME = "SKILL.md"
_RULESET_RE = re.compile(r"# ruleset (\d+)")


def measure(path: Path) -> int:
    """Whitespace-separated word count of a UTF-8 file."""
    return len(path.read_text(encoding="utf-8", errors="replace").split())


def is_skill_file(path: Path) -> bool:
    """True only for a file named exactly ``SKILL.md`` (case-sensitive)."""
    return path.name == _SKILL_NAME


def _ceiling(group: BudgetGroup) -> int:
    if group is BudgetGroup.STYLE:
        return STYLE_CEILING
    return SKILLS_CEILING if group is BudgetGroup.SKILLS else CONTEXT_CEILING


def _value(path: Path, group: BudgetGroup) -> int:
    return count_violations(path) if group is BudgetGroup.STYLE else measure(path)


def _style_exempt(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, pat) for pat in _STYLE_EXEMPT_GLOBS)


def scan(root: Path, group: BudgetGroup) -> dict[str, int]:
    """Word counts (style: strict violation counts) for every in-scope doc under ``root``."""
    found: dict[str, int] = {}
    if group is BudgetGroup.SKILLS:
        # Exact-name filter: glob is case-insensitive on Windows (skill.md).
        paths = [p for p in (root / _SKILLS_DIR).rglob("*.md") if is_skill_file(p)]
    elif group is BudgetGroup.STYLE:
        paths = [p for pattern in _STYLE_GLOBS for p in root.glob(pattern)]
    else:
        paths = [p for pattern in _CONTEXT_GLOBS for p in root.glob(pattern)]
    for path in paths:
        rel = path.relative_to(root).as_posix()
        if not path.is_file():
            continue
        if group is BudgetGroup.STYLE and _style_exempt(rel):
            continue
        found[rel] = _value(path, group)
    return dict(sorted(found.items()))


def read_ratchet_ruleset(path: Path) -> int:
    """STE ruleset recorded on a ratchet's ``# ruleset N`` header; 0 when absent."""
    if not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    match = _RULESET_RE.fullmatch(lines[0].strip()) if lines else None
    return int(match.group(1)) if match else 0


def read_ratchet(path: Path) -> dict[str, int]:
    """Parse a ratchet file; a missing file is an empty ratchet. ``#`` lines are headers."""
    if not path.is_file():
        return {}
    entries: dict[str, int] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        name, sep, words = line.rpartition(RATCHET_SEPARATOR)
        try:
            if not sep or not name:
                raise ValueError("missing tab separator")
            entries[name] = int(words)
        except ValueError as exc:
            raise ValueError(
                f"{path}:{lineno}: malformed ratchet line {line!r}: {exc}"
            ) from exc
    return dict(sorted(entries.items()))


def format_ratchet(ratchet: dict[str, int], ruleset: int | None = None) -> str:
    """Sorted `path<TAB>words` lines, LF newlines, trailing newline; optional ruleset header."""
    lines = [f"{p}{RATCHET_SEPARATOR}{w}" for p, w in sorted(ratchet.items())]
    if ruleset is not None:
        lines.insert(0, f"# ruleset {ruleset}")
    return "\n".join(lines) + "\n" if lines else ""


def write_ratchet(
    path: Path, ratchet: dict[str, int], ruleset: int | None = None
) -> None:
    """Atomically write a ratchet file (LF newlines, sorted)."""
    write_text_atomic(path, format_ratchet(ratchet, ruleset))


def check(
    root: Path,
    ratchet: dict[str, int],
    group: BudgetGroup = BudgetGroup.CONTEXT,
) -> tuple[BudgetViolation, ...]:
    """Violations: growth over recorded size, or unrecorded docs over ceiling."""
    ceiling = _ceiling(group)
    out: list[BudgetViolation] = []
    for rel, words in scan(root, group).items():
        recorded = ratchet.get(rel)
        if recorded is None:
            if words > ceiling:
                out.append(BudgetViolation(rel, words, ceiling, None))
        elif words > recorded:
            out.append(BudgetViolation(rel, words, recorded, recorded))
    return tuple(out)


def update_ratchet(
    root: Path,
    ratchet: dict[str, int],
    group: BudgetGroup = BudgetGroup.CONTEXT,
) -> UpdateResult:
    """Lower entries to current size; never raise one.

    Grown docs keep their old entry and are returned in ``refused``. Every
    unrecorded doc is seeded at its current size (the ceiling applies only in
    ``check`` to unrecorded docs). Entries for docs that no longer exist are
    dropped.
    """
    new: dict[str, int] = {}
    lowered: list[str] = []
    refused: list[BudgetViolation] = []
    for rel, words in scan(root, group).items():
        recorded = ratchet.get(rel)
        if recorded is None:
            new[rel] = words
        elif words > recorded:
            new[rel] = recorded
            refused.append(BudgetViolation(rel, words, recorded, recorded))
        else:
            new[rel] = words
            if words < recorded:
                lowered.append(rel)
    return UpdateResult(dict(sorted(new.items())), tuple(lowered), tuple(refused))


def reseed(
    ratchet: dict[str, int],
    root: Path,
    rels: Iterable[str],
    group: BudgetGroup = BudgetGroup.CONTEXT,
) -> dict[str, int]:
    """Copy of ``ratchet`` with each ``rels`` entry set to its current size.

    Unlike :func:`update_ratchet` this may raise an entry. Only deliberate
    re-records call it. A ``rel`` no longer in scope is dropped.
    """
    current = scan(root, group)
    new = dict(ratchet)
    for rel in rels:
        if rel in current:
            new[rel] = current[rel]
        else:
            new.pop(rel, None)
    return dict(sorted(new.items()))


def reseed_stale_style(root: Path, ratchet_path: Path) -> bool:
    """Re-record every in-scope style doc when the ratchet header is older than the ruleset.

    Returns True when it rewrote the file. A missing file or a current header is a no-op.
    """
    if not ratchet_path.is_file():
        return False
    if read_ratchet_ruleset(ratchet_path) >= STE_RULESET_VERSION:
        return False
    current = scan(root, BudgetGroup.STYLE)
    fresh = reseed({}, root, list(current), BudgetGroup.STYLE)
    write_ratchet(ratchet_path, fresh, STE_RULESET_VERSION)
    return True
