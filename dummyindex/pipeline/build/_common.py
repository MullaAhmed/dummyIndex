"""Path-resolution helpers shared across `pipeline/build/` modules."""
from __future__ import annotations
from pathlib import Path


def _rel_path(source_file: str, root_abs: Path) -> str:
    """Return a forward-slash path relative to root_abs.

    Source paths reach this function in several shapes: absolute (from tree-sitter
    extraction before relativization), cwd-relative (from ``collect_files``), or
    root-relative (after watch.py's relativize step). Try each in turn and take
    the first that lands inside ``root_abs``. Fall back to the raw string as a
    last resort so the node still gets placed somewhere deterministic.
    """
    if not source_file:
        return ""
    raw = Path(source_file)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(Path.cwd() / raw)
        candidates.append(root_abs / raw)
    for candidate in candidates:
        try:
            rel = candidate.resolve().relative_to(root_abs)
        except (ValueError, OSError):
            continue
        return rel.as_posix()
    return raw.as_posix().lstrip("./")
