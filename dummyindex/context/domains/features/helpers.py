"""Package-private helpers used across `context.features` modules.

Path / range / unique-paths helpers for graph-driven scaffolding; small
file-write helpers (atomic JSON / text writers); slug validation and
recursive removal for ops; primary-reason classifier for docs-link
ranking.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .constants import _MERGE_BEGIN, _MERGE_END
from .errors import FeatureRenameError

_SLUG_RE_OK = "abcdefghijklmnopqrstuvwxyz0123456789-_"


def _validate_feature_id(value: str) -> str:
    """Reject feature_ids that aren't safe as folder names."""
    if not value:
        raise FeatureRenameError("feature id must not be empty")
    lowered = value.strip().lower()
    if any(ch not in _SLUG_RE_OK for ch in lowered):
        raise FeatureRenameError(
            f"feature id {value!r} must be lowercase letters, digits, '-', '_'"
        )
    if lowered.startswith("-") or lowered.endswith("-"):
        raise FeatureRenameError(f"feature id {value!r} must not start/end with '-'")
    return lowered


def _format_merge_block(
    from_id: str,
    src_feature_payload: dict[str, Any],
    src_readme: str,
) -> str:
    """Render the markdown block that documents a merged-in trivial feature."""
    lines: list[str] = []
    lines.append(_MERGE_BEGIN)
    lines.append(f"### Merged from `{from_id}`")
    lines.append("")
    name = src_feature_payload.get("name") or from_id
    if name != from_id:
        lines.append(f"_Originally extracted as feature `{name}`._")
        lines.append("")
    files = src_feature_payload.get("files") or []
    if files:
        lines.append("**Files involved:**")
        lines.append("")
        for fp in files:
            lines.append(f"- `{fp}`")
        lines.append("")
    if src_readme.strip():
        lines.append("**Original notes:**")
        lines.append("")
        lines.append(src_readme.strip())
        lines.append("")
    lines.append(_MERGE_END)
    return "\n".join(lines) + "\n"


def _append_section(target: Path, section: str, block: str) -> None:
    """Append ``block`` to ``target``, creating the file with a header if
    it doesn't yet exist. Atomic via tmp-rename."""
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        new_content = existing.rstrip() + "\n\n" + block
    else:
        header = f"# {section.replace('-', ' ').title()}\n\n"
        new_content = header + block
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    tmp.replace(target)


def _rmtree(path: Path) -> None:
    """Recursive delete — `Path.rmdir()` would fail on non-empty dirs."""
    import shutil as _sh

    _sh.rmtree(path)


# ----- flow tracing ---------------------------------------------------------
def _rel(p: Any, root_abs: Path | None) -> str | None:
    """Coerce a `source_file` value to a repo-relative POSIX path.

    Returns the raw value if it doesn't look like a string or if it's
    already outside `root_abs`. None if not a string.
    """
    if not isinstance(p, str) or not p:
        return None
    if root_abs is None:
        return p
    try:
        return Path(p).resolve().relative_to(root_abs).as_posix()
    except ValueError:
        return p


def _range_from_location(loc: Any) -> list[int] | None:
    """Parse a source_location like 'L13' or 'L13-L17' into [start, end]."""
    if not isinstance(loc, str):
        return None
    s = loc.strip().lstrip("L")
    if "-" in s:
        a, b = s.split("-", 1)
        try:
            return [int(a.lstrip("L")), int(b.lstrip("L"))]
        except ValueError:
            return None
    try:
        n = int(s)
        return [n, n]
    except ValueError:
        return None


def _unique_paths(paths: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if not isinstance(p, str) or not p:
            continue
        if p not in seen:
            seen.add(p)
            out.append(p)
    return tuple(sorted(out))


# ----- writers --------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, body: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


# ----- markdown / json templates --------------------------------------------


def _primary_reason_kind(reason: str) -> str:
    """Pull the first reason kind off the comma-joined reason string."""
    if not reason:
        return ""
    first = reason.split(",", 1)[0].strip()
    return first.split(":", 1)[0]
