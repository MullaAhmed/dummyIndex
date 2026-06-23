"""Shared build-lifecycle helpers used by ``runner`` and ``enriched_refresh``.

These are private-to-package (``_``-prefixed) helpers extracted so the
non-destructive refresh path (``enriched_refresh``) can reuse them without
reaching into ``runner``'s private surface. Both modules import from here.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator, Sequence
from pathlib import Path

from dummyindex.context.domains.atomic_io import normalize_eof_newline
from dummyindex.context.domains.source_docs import discover_default_doc_paths
from dummyindex.pipeline.io import cache as cache_module

_DOC_WALK_EXTENSIONS = frozenset(
    {
        ".md",
        ".mdx",
        ".rst",
        ".txt",
        ".pdf",
        ".html",
        ".htm",
        ".docx",
        ".xlsx",
    }
)

# Directory names we never descend into when walking a doc root — even
# when explicitly passed via --docs. These are universally noise.
_DOC_WALK_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".context",
    }
)


def walk_doc_files(root: Path) -> list[Path]:
    """Walk a doc directory for files with doc-like extensions."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _DOC_WALK_SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in _DOC_WALK_EXTENSIONS:
                out.append(p.resolve())
    return out


def collect_doc_paths(
    detection: dict,
    repo_root: Path,
    extra_doc_roots: Sequence[Path],
) -> list[Path]:
    """Gather every doc path the catalog should consider.

    Sources, in order:

    1. Files classified as DOCUMENT or PAPER by ``detect`` (covers
       in-repo markdown, html, txt, pdf, and converted office sidecars).
    2. Default in-repo doc locations missed by detection's hidden-dir
       pruning (e.g. ``.changeset``, hidden ADR folders) — picked up via
       ``discover_default_doc_paths``.
    3. Any ``extra_doc_roots`` passed via ``--docs``, walked for doc-like
       extensions.

    Returns absolute, deduplicated, sorted paths.
    """
    paths: dict[str, Path] = {}

    files_map = detection.get("files", {}) if isinstance(detection, dict) else {}
    for ftype in ("document", "paper"):
        for raw in files_map.get(ftype, []) or []:
            try:
                p = Path(raw).resolve()
            except OSError:
                continue
            paths[str(p)] = p

    for p in discover_default_doc_paths(repo_root):
        if p.is_file():
            paths[str(p)] = p
        elif p.is_dir():
            for sub in walk_doc_files(p):
                paths[str(sub)] = sub

    for raw_root in extra_doc_roots:
        root = Path(raw_root).resolve()
        if root.is_file():
            paths[str(root)] = root
        elif root.is_dir():
            for sub in walk_doc_files(root):
                paths[str(sub)] = sub

    return sorted(paths.values())


def newest_mtime(paths: list[Path]) -> float | None:
    newest: float | None = None
    for p in paths:
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if newest is None or mt > newest:
            newest = mt
    return newest


def normalize_written_eof_newlines(
    context_dir: Path, rel_paths: Sequence[str]
) -> tuple[str, ...]:
    """Post-write hygiene pass: every artifact a build wrote must end with
    exactly one newline (pre-commit's ``end-of-file-fixer`` contract).

    Domain writers own their *content*; the build boundary owns byte-level
    hygiene, so a writer outside this package can never re-introduce a
    lint-failing artifact into the committed tree. Skips paths that don't
    exist (a writer may have failed non-fatally) and binary/empty files
    (handled inside :func:`normalize_eof_newline`). Returns the rel paths
    that were rewritten.
    """
    fixed: list[str] = []
    for rel in rel_paths:
        path = context_dir / rel
        if not path.is_file():
            continue
        if normalize_eof_newline(path):
            fixed.append(rel)
    return tuple(fixed)


@contextlib.contextmanager
def cache_dir_override(target: Path) -> Iterator[None]:
    """Point ``pipeline.io.cache.cache_dir()`` at ``target`` for the block.

    Routes through the **trusted in-process** channel
    (:func:`set_trusted_cache_dir`), NOT the ambient ``DUMMYINDEX_CACHE_DIR``
    env var. ``cache_dir()`` confines the env var to the repo root and would
    silently reject an out-of-repo value; this internal override targets the
    in-repo ``.context/cache/`` and must be honored unconditionally, so it does
    not flow through that confinement path (and never mutates the user's env).
    """
    saved = cache_module._TRUSTED_CACHE_DIR
    cache_module.set_trusted_cache_dir(target.resolve())
    try:
        yield
    finally:
        cache_module.set_trusted_cache_dir(saved)
