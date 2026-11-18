"""Filesystem-touching pipeline helpers, re-exported here from their submodules.

- ``cache`` — content-hash cache for tree-sitter parses.
- ``detect`` — file-type detection and document extraction (PDF / DOCX / XLSX).
- ``git`` — submodule/worktree-aware git-repo detection.
- ``paths`` — root-confinement and safe-read-target checks.
"""

from __future__ import annotations

from .cache import file_hash, load_cached, save_cached
from .detect import (
    CODE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PAPER_EXTENSIONS,
    _is_ignored,
    _load_dummyindexignore,
    detect,
    docx_to_markdown,
    extract_pdf_text,
    xlsx_to_markdown,
)
from .git import is_git_repo, resolve_git_dir, submodule_paths
from .paths import is_safe_read_target, resolve_under_root

__all__ = [
    "CODE_EXTENSIONS",
    "IMAGE_EXTENSIONS",
    "PAPER_EXTENSIONS",
    "_is_ignored",
    "_load_dummyindexignore",
    "detect",
    "docx_to_markdown",
    "extract_pdf_text",
    "file_hash",
    "is_git_repo",
    "is_safe_read_target",
    "load_cached",
    "resolve_git_dir",
    "resolve_under_root",
    "save_cached",
    "submodule_paths",
    "xlsx_to_markdown",
]
