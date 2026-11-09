"""Build and read the source-docs catalog under `.context/source-docs/`.

Catalogs the markdown / RST / text docs checked into the repo (README, CHANGELOG,
docs/, ADR/, RFC/, root ``*.md``, …) and grades each against the current AST:
backticked code references that no longer match any symbol demote the doc's
confidence. ``__all__`` is the stable surface for tests, ``build/runner.py``,
``output/`` and ``domains/features/``.
"""

from __future__ import annotations

from .catalog import build_doc_catalog
from .constants import SCHEMA_VERSION
from .discovery import discover_default_doc_paths
from .keys import harvest_json_keys
from .models import DocCatalog, DocEntry
from .readers import read_catalog
from .refs import extract_code_refs, find_broken_refs, looks_like_code_ref
from .writers import write_catalog

__all__ = [
    "DocCatalog",
    "DocEntry",
    "SCHEMA_VERSION",
    "build_doc_catalog",
    "discover_default_doc_paths",
    "extract_code_refs",
    "find_broken_refs",
    "harvest_json_keys",
    "looks_like_code_ref",
    "read_catalog",
    "write_catalog",
]
