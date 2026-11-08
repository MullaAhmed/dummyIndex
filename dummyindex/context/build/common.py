"""Shared build-lifecycle helpers used by ``runner`` and ``enriched_refresh``.

They live here so the non-destructive refresh can reuse them without reaching into
``runner``'s private surface.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator, Sequence
from pathlib import Path

from dummyindex.codex_guidance import (
    is_project_instruction_path,
    project_instruction_paths,
)
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


def walk_doc_files(root: Path, *, project_root: Path | None = None) -> list[Path]:
    """Walk a doc directory for files with doc-like extensions."""
    out: list[Path] = []
    instruction_root = project_root if project_root is not None else root
    codex_instruction_paths = project_instruction_paths(project_root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _DOC_WALK_SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            p = Path(dirpath) / fname
            if is_project_instruction_path(
                p,
                instruction_root,
                instruction_paths=codex_instruction_paths,
            ):
                continue
            if p.suffix.lower() in _DOC_WALK_EXTENSIONS:
                out.append(p.resolve())
    return out


def collect_doc_paths(
    detection: dict,
    repo_root: Path,
    extra_doc_roots: Sequence[Path],
) -> list[Path]:
    """Gather every doc path the catalog should consider.

    Sources: files ``detect`` classed as DOCUMENT or PAPER; default in-repo doc locations
    that detection's hidden-dir pruning misses (e.g. ``.changeset``, via
    ``discover_default_doc_paths``); and ``extra_doc_roots`` (``--docs``), walked for
    doc-like extensions. Project instruction files are dropped from every source.
    Returns absolute, deduplicated, sorted paths.
    """
    paths: dict[str, Path] = {}
    codex_instruction_paths = project_instruction_paths(repo_root)

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
            for sub in walk_doc_files(p, project_root=repo_root):
                paths[str(sub)] = sub

    for raw_root in extra_doc_roots:
        root = Path(raw_root).resolve()
        if root.is_file():
            paths[str(root)] = root
        elif root.is_dir():
            for sub in walk_doc_files(root, project_root=repo_root):
                paths[str(sub)] = sub

    # Final policy gate covers every input route, including a configured Codex
    # instruction file passed directly as a single-file ``--docs`` root.
    return sorted(
        p
        for p in paths.values()
        if not is_project_instruction_path(
            p,
            repo_root,
            instruction_paths=codex_instruction_paths,
        )
    )


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
    """Post-write hygiene: every artifact a build wrote ends with exactly one newline.

    That is pre-commit's ``end-of-file-fixer`` contract; the build boundary owns it so a
    writer elsewhere can never commit a lint-failing artifact. Skips missing paths (a
    writer may have failed non-fatally) and binary/empty files. Returns the rel paths
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

    Uses the **trusted** in-process channel (:func:`set_trusted_cache_dir`), NOT the
    ``DUMMYINDEX_CACHE_DIR`` env var: ``cache_dir()`` confines that env var to the repo
    root and silently rejects an out-of-repo value, while this internal override must be
    honored unconditionally. It never mutates the user's env.
    """
    saved = cache_module._TRUSTED_CACHE_DIR
    cache_module.set_trusted_cache_dir(target.resolve())
    try:
        yield
    finally:
        cache_module.set_trusted_cache_dir(saved)
