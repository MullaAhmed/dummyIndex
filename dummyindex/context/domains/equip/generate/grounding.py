"""CLI-owned grounding sidecar: a bounded digest of the project's ``.context/``.

Templates point agents at ``.context/equipment/grounding/<name>.md`` instead of
embedding ``.context/`` text, so a body's bytes never change when a feature doc
does. Output is a pure function of the ``.context/`` bytes: CRLF and LF inputs
match, and no absolute paths appear.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from dummyindex.shared.atomic_io import write_text_atomic

from ...query import query
from ..enums import EquipmentKind, EquipmentSource
from ..models import EquipmentItem

GROUNDING_HEADER = "<!-- dummyindex:generated-grounding — do not edit -->"
GENERIC_FOCUS_QUERY = "architecture overview"

_SUMMARY_CHARS = 300
_TOP_FEATURES = 5
_ENTRY_FILES = 3
_MAX_RISKS = 5
_EMPHASIS_ONLY = re.compile(r"^(_[^_]+_|\*[^*]+\*)$")

# Keys are capability values from ``equip.enums.Capability``. Roles without an
# entry (implement, test, review, verify) rank features by member count instead.
_FOCUS_QUERIES: dict[str, str] = {
    "database": "database schema data access queries",
    "data": "data access persistence storage",
    "security": "authentication authorization secrets input validation",
    "performance": "performance latency caching hot path",
    "docs": "documentation readme guides",
    "search": "search index ranking query",
    "frontend": "frontend ui components rendering",
    "api": "api endpoints routes handlers",
    "migration": "migration schema upgrade",
    "ci": "ci pipeline build workflow",
}


def grounding_path(name: str) -> str:
    return f".context/equipment/grounding/{name}.md"


# Equipment may write only under these project-relative roots; anything else is refused.
EQUIPMENT_WRITE_ROOTS = (
    Path(".context/equipment"),
    Path(".claude/agents"),
    Path(".claude/skills"),
)


def contained_path(root: Path, rel: str) -> Path | None:
    """The resolved path when ``rel`` lies strictly inside an allowed root, else None.

    The bases are compared unresolved: a base that is itself a symlink out of the
    repo must not count as contained.
    """
    if not rel or Path(rel).is_absolute():
        return None
    base_root = root.resolve()
    target = (base_root / rel).resolve()
    for base in EQUIPMENT_WRITE_ROOTS:
        if base_root / base in target.parents:
            return target
    return None


def write_grounding_sidecars(
    root: Path,
    context_dir: Path,
    items: list[EquipmentItem] | tuple[EquipmentItem, ...],
) -> tuple[bool, tuple[str, ...]]:
    """Write ``.context/equipment/grounding/<name>.md`` for each generated agent and skill.

    Whole-file atomic rewrite; a byte-identical file is left alone. Returns
    ``(changed, skipped)`` where ``skipped`` lists sidecars refused by containment.
    """
    changed = False
    skipped: list[str] = []
    for item in items:
        if item.source is not EquipmentSource.GENERATED or item.kind not in (
            EquipmentKind.AGENT,
            EquipmentKind.SKILL,
        ):
            continue
        rel = grounding_path(item.name)
        target = contained_path(root, rel)
        if target is None:
            skipped.append(rel)
            continue
        capability = item.capabilities[0] if item.capabilities else item.name
        text = render_grounding(context_dir, capability=capability)
        if _read_text(target) == text:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(target, text)
        changed = True
    return changed, tuple(skipped)


def focus_query(capability: str) -> str:
    return _FOCUS_QUERIES.get(capability, GENERIC_FOCUS_QUERY)


def render_grounding(context_dir: Path, *, capability: str, budget: int = 6000) -> str:
    """Return the sidecar text, cut to at most ``budget`` UTF-8 bytes.

    Never raises on missing or unreadable ``.context/`` files; each absent
    source only shortens the output.
    """
    lines = [GROUNDING_HEADER]
    summary = _project_summary(context_dir)
    if summary:
        lines += ["", summary]

    features = _focus_features(context_dir, capability)
    if features:
        lines += ["", "## Focus features"]
        lines += [
            _feature_line(context_dir, fid, text, files)
            for fid, text, files in features
        ]
        risks = _risks(context_dir, [fid for fid, _, _ in features])
        if risks:
            lines += ["", "## Recorded risks"] + risks

    return _within_budget(lines, budget)


def _within_budget(lines: list[str], budget: int) -> str:
    out = ""
    for line in lines:
        candidate = f"{out}{line}\n"
        if len(candidate.encode("utf-8")) > budget:
            break
        out = candidate
    return out


def _read_text(path: Path) -> str | None:
    try:
        # read_text uses universal newlines, so CRLF input matches LF input.
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _project_summary(context_dir: Path) -> str:
    text = _read_text(context_dir / "PROJECT.md")
    if text is None:
        return ""
    for paragraph in _paragraphs(text):
        # A whole-paragraph emphasis line (e.g. a version stamp) is metadata, not a summary.
        if _EMPHASIS_ONLY.match(paragraph):
            continue
        return paragraph[:_SUMMARY_CHARS]
    return ""


def _paragraphs(text: str) -> list[str]:
    """Body paragraphs as single lines; headings and blank lines separate them."""
    out: list[str] = []
    current: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            if current:
                out.append(" ".join(current))
                current = []
            continue
        current.append(line)
    if current:
        out.append(" ".join(current))
    return out


def _load_index(context_dir: Path) -> list[dict] | None:
    text = _read_text(context_dir / "features" / "INDEX.json")
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return None
    return [
        f
        for f in features
        if isinstance(f, dict) and isinstance(f.get("feature_id"), str)
    ]


def _focus_features(
    context_dir: Path, capability: str
) -> list[tuple[str, str, list[str]]]:
    """Top features as ``(feature_id, summary, files)``, ties broken by id."""
    index = _load_index(context_dir)
    if index is None:
        return []
    summaries = {f["feature_id"]: str(f.get("summary") or "") for f in index}

    query_ids: list[str] = []
    if capability in _FOCUS_QUERIES:
        query_ids = _query_top(context_dir, _FOCUS_QUERIES[capability])
    # Query hits first; the query can return fewer than five (budget cut, or no hit),
    # so top up with the largest features.
    ordered = sorted(
        index,
        key=lambda f: (-int(f.get("member_count") or 0), f["feature_id"]),
    )
    chosen = _top_unique(query_ids + [f["feature_id"] for f in ordered])

    return [
        (fid, summaries.get(fid, ""), _entry_files(context_dir, fid)) for fid in chosen
    ]


def _top_unique(ids: list[str]) -> list[str]:
    # INDEX.json can list one id twice; dedupe before the cut so five distinct features remain.
    return list(dict.fromkeys(ids))[:_TOP_FEATURES]


def _query_top(context_dir: Path, text: str) -> list[str]:
    try:
        result = query(context_dir, text, top_k=_TOP_FEATURES)
    except (FileNotFoundError, ValueError):
        return []
    ranked = sorted(
        result.matches,
        key=lambda m: (-m.feature.score, m.feature.feature_id),
    )
    return _top_unique([m.feature.feature_id for m in ranked])


def _entry_files(context_dir: Path, feature_id: str) -> list[str]:
    text = _read_text(context_dir / "features" / feature_id / "feature.json")
    if text is None:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        return []
    return [f for f in files if isinstance(f, str)][:_ENTRY_FILES]


def _feature_line(
    context_dir: Path, feature_id: str, summary: str, files: list[str]
) -> str:
    line = f"- `{feature_id}` — {_one_line(summary)}"
    if files:
        line += " (files: " + ", ".join(f"`{f}`" for f in files) + ")"
    return line


def _risks(context_dir: Path, feature_ids: list[str]) -> list[str]:
    out: list[str] = []
    for fid in feature_ids:
        text = _read_text(context_dir / "features" / fid / "concerns.md")
        if text is None:
            continue
        rel = f"{context_dir.name}/features/{fid}/concerns.md"
        for number, line in enumerate(text.split("\n"), start=1):
            if not line.startswith("- "):
                continue
            out.append(f"- {_one_line(line[2:])} (`{rel}:{number}`)")
            if len(out) == _MAX_RISKS:
                return out
    return out
