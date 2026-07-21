"""In-repo doc discovery: README, CHANGELOG, docs/, ADR/, RFC/, etc."""

from __future__ import annotations

from pathlib import Path

from dummyindex.codex_guidance import (
    is_project_instruction_path,
    project_instruction_paths,
)

# In-repo paths checked when no --docs is given. Names are case-insensitive
# at match time; presence-only check (no globbing of unknown extensions).
_DEFAULT_DOC_FILES: tuple[str, ...] = (
    "README.md",
    "README.rst",
    "README.txt",
    "CHANGELOG.md",
    "CHANGELOG.rst",
    "CHANGELOG.txt",
    "ARCHITECTURE.md",
    "ARCHITECTURE.rst",
    "SECURITY.md",
    "BRIEF.md",
    "CONTRIBUTING.md",
    "ROADMAP.md",
    "DESIGN.md",
)
_DEFAULT_DOC_DIRS: tuple[str, ...] = (
    "docs",
    "doc",
    "documentation",
    "adr",
    "ADR",
    "rfc",
    "RFC",
    "rfcs",
    ".changeset",
    "changes",
)

# Doc-like file extensions tracked in the catalog.
_DOC_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".mdx",
        ".rst",
        ".txt",
        ".pdf",
        ".html",
        ".htm",
        ".docx",
        ".xlsx",  # office files already get converted to .md sidecars upstream
    }
)


def discover_default_doc_paths(repo_root: Path) -> list[Path]:
    """Return absolute paths of in-repo default doc locations that exist.

    Walks the well-known doc file names plus any directory in
    ``_DEFAULT_DOC_DIRS``. Also includes every top-level ``*.md`` file at
    the repo root (catches less-conventional names like ``BRIEF.md``), except
    active Codex project instruction files. The returned list is deduplicated
    and sorted.
    """
    repo_root = repo_root.resolve()
    codex_instruction_paths = project_instruction_paths(repo_root)
    seen: set[Path] = set()
    out: list[Path] = []

    def _take(p: Path) -> None:
        if p.is_file() and is_project_instruction_path(
            p,
            repo_root,
            instruction_paths=codex_instruction_paths,
        ):
            return
        if p.exists() and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p.resolve())

    for name in _DEFAULT_DOC_FILES:
        _take(repo_root / name)

    for d in _DEFAULT_DOC_DIRS:
        _take(repo_root / d)

    # Any markdown at the repo root that we didn't already capture by name.
    try:
        for p in sorted(repo_root.iterdir()):
            if p.is_file() and p.suffix.lower() in (".md", ".rst"):
                _take(p)
    except OSError:
        pass

    out.sort()
    return out
