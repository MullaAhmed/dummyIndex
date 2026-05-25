"""Filesystem-touching pipeline helpers.

- ``cache`` — content-hash cache for tree-sitter parses.
- ``detect`` — file-type detection (code / paper / image) and document
  extraction (PDF / DOCX / XLSX → text).

Re-exported here so callers can say
``from dummyindex.pipeline.io import detect, file_hash, save_cached``
without picking the right submodule.
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
    "load_cached",
    "save_cached",
    "xlsx_to_markdown",
]
