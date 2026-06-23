"""Build and read the source-docs catalog under `.context/source-docs/`.

Catalog the markdown / RST / text docs checked into the repo (README,
CHANGELOG, docs/, ADR/, RFC/, ARCHITECTURE.md, SECURITY.md, BRIEF.md,
plus any *.md at the repo root) and grade each one against the current
AST. Drift is flagged via broken-reference ratios — backticked code
references that no longer match any symbol demote the doc's confidence.

Public surface (kept stable for tests, ``context/build/runner.py``,
``context/output/instructions.py`` / ``output/docs.py``, and
``context/domains/features/``):

- ``DocCatalog``, ``DocEntry`` — dataclasses
- ``build_doc_catalog``, ``discover_default_doc_paths``,
  ``harvest_json_keys``
- ``extract_code_refs``, ``find_broken_refs``, ``looks_like_code_ref``
- ``read_catalog``, ``write_catalog``
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
