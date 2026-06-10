"""Path-resolution helpers + ignore lists shared across `pipeline/build/` modules.

`_STRUCTURE_*` constants live here so both `structure.py` and `references.py`
can use them without a circular import.
"""
from __future__ import annotations
from pathlib import Path


# The structure graph includes *every* file under root by default, except
# those matched by an ignore file or by the built-in junk list. Ignore files
# are read by name in priority order (first found wins). Syntax matches
# .dummyindexignore / .gitignore style patterns.
_STRUCTURE_IGNORE_FILES = (".codeindexignore", ".dummyindexignore")

# Directories always skipped, even without any ignore file. Kept in sync with
# pipeline.io.detect._SKIP_DIRS so the two pipelines agree on obvious junk.
_STRUCTURE_SKIP_DIRS = frozenset({
    ".context",  # dummyindex's own output; skip self-generated content
    ".claude",   # Claude Code skills/settings — agent config, not source
    ".cursor", ".aider", ".kiro", ".trae", ".trae-cn",  # other agent configs
    ".github", ".gitlab",
    ".git",
    "node_modules", "__pycache__",
    ".venv", "venv", "env", ".env",
    "dist", "build", "target", "out",
    ".next", ".nuxt", ".svelte-kit",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".eggs",
    "site-packages", "lib64",
    ".idea", ".vscode", ".vs",
})


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
