"""`build_doc_catalog` — walk discovered docs, extract refs, classify confidence."""
from __future__ import annotations
import datetime as _dt
import hashlib
from pathlib import Path
from typing import Iterable, Optional, Sequence

from dummyindex.context.enums import DOC_CONFIDENCE_ORDER, DocConfidence

from .constants import (
    SCHEMA_VERSION,
    _HIGH_BROKEN_RATIO,
    _LOW_BROKEN_RATIO,
    _MIN_BROKEN_FOR_LOW,
)
from .discovery import _DOC_EXTENSIONS
from .models import DocCatalog, DocEntry
from .refs import (
    extract_code_refs,
    extract_doc_text,
    extract_title_and_headings,
    find_broken_refs,
)


_AGE_BUCKETS: tuple[tuple[float, str], ...] = (
    (-1, "fresh"),                # negative — doc newer than newest code
    (30 * 86400, "recent"),
    (90 * 86400, "aging"),
    (180 * 86400, "stale"),
    (float("inf"), "old"),
)


# ----- Catalog construction -------------------------------------------------


_DOC_TYPE_BY_EXT: dict[str, str] = {
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".docx": "docx",
    ".xlsx": "xlsx",
}


def _doc_type(path: Path) -> str:
    return _DOC_TYPE_BY_EXT.get(path.suffix.lower(), "other")


def _classify_age(age_delta: Optional[float]) -> str:
    if age_delta is None:
        return "unknown"
    for limit, label in _AGE_BUCKETS:
        if age_delta <= limit:
            return label
    return "old"


def _classify_confidence(
    broken_ratio: float,
    age_bucket: str,
    broken_count: int = 0,
) -> str:
    """Map (broken_ratio, age, broken_count) → high / medium / low.

    The ``broken_count`` floor protects tiny docs: a 1-ref doc with that
    one ref broken still scores `medium`, not `low`. Without this, a
    one-sentence ADR that mentions a feature by an example name (e.g.
    ``Authentication``) drops to `low` despite being mostly correct.
    """
    if broken_ratio >= _LOW_BROKEN_RATIO and broken_count >= _MIN_BROKEN_FOR_LOW:
        return DocConfidence.LOW
    if (
        age_bucket in ("stale", "old")
        and broken_ratio > 0
        and broken_count >= _MIN_BROKEN_FOR_LOW
    ):
        return DocConfidence.LOW
    if broken_ratio <= _HIGH_BROKEN_RATIO and age_bucket in ("fresh", "recent"):
        return DocConfidence.HIGH
    if broken_ratio <= _HIGH_BROKEN_RATIO and age_bucket == "unknown":
        return DocConfidence.HIGH
    return DocConfidence.MEDIUM


def _relpath_or_abs(path: Path, repo_root: Path) -> tuple[str, bool]:
    try:
        return path.resolve().relative_to(repo_root).as_posix(), False
    except ValueError:
        return path.resolve().as_posix(), True


def build_doc_catalog(
    doc_paths: Iterable[Path],
    *,
    repo_root: Path,
    symbol_names: frozenset[str],
    file_paths: frozenset[str],
    newest_code_mtime: Optional[float],
    extra_doc_roots: Sequence[Path] = (),
    default_discovery_used: bool = True,
    extra_names: frozenset[str] = frozenset(),
    now: Optional[_dt.datetime] = None,
) -> DocCatalog:
    """Compute the catalog for ``doc_paths`` against the current AST state.

    ``file_paths`` should be the *full* set of repo-relative paths the
    detection step found (code + docs + papers + ...), not just code
    files. Prose docs reference more than code: README.md, schema JSON,
    config files, generated artifacts. A path-set restricted to code
    drives false-positive `broken_refs` reports.

    ``extra_names`` is a superset of identifiers the caller already
    knows are legitimate even when they're not in the AST — typically
    JSON schema keys harvested from ``*.json`` files in the repo. The
    catalog also bakes in a small ``_FRAMEWORK_WHITELIST`` for Claude
    Code tools and hook events.
    """
    repo_root = repo_root.resolve()
    seen: set[Path] = set()
    entries: list[DocEntry] = []

    for raw in doc_paths:
        p = raw.resolve()
        if p in seen or not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in _DOC_EXTENSIONS:
            continue
        seen.add(p)

        try:
            data = p.read_bytes()
            stat = p.stat()
        except OSError:
            continue

        text = extract_doc_text(p)
        title, headings = extract_title_and_headings(text)
        refs = extract_code_refs(text)
        broken = find_broken_refs(
            refs,
            symbol_names=symbol_names,
            file_paths=file_paths,
            extra_names=extra_names,
        )
        broken_ratio = (len(broken) / len(refs)) if refs else 0.0

        age_delta: Optional[float]
        if newest_code_mtime is None:
            age_delta = None
        else:
            age_delta = newest_code_mtime - stat.st_mtime
        age_bucket = _classify_age(age_delta)
        confidence = _classify_confidence(
            broken_ratio, age_bucket, broken_count=len(broken)
        )

        rel, is_external = _relpath_or_abs(p, repo_root)
        # Find the discovery root this file came from (best-effort).
        source_root = _attribute_source_root(p, repo_root, extra_doc_roots)

        entries.append(
            DocEntry(
                path=rel,
                abs_path=str(p),
                doc_type=_doc_type(p),
                title=title,
                headings=headings,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=stat.st_size,
                mtime=stat.st_mtime,
                age_delta_seconds=age_delta,
                age_bucket=age_bucket,
                referenced_count=len(refs),
                broken_refs=broken,
                broken_ratio=broken_ratio,
                confidence=confidence,
                is_external=is_external,
                source_root=source_root,
            )
        )

    # Sort: confidence (high → low), then by path. Stable so re-running on
    # the same inputs yields identical JSON.
    entries.sort(key=lambda e: (DOC_CONFIDENCE_ORDER.get(e.confidence, 3), e.path))

    return DocCatalog(
        schema_version=SCHEMA_VERSION,
        generated_at=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(timespec="seconds"),
        repo_root=str(repo_root),
        docs=tuple(entries),
        extra_doc_roots=tuple(str(Path(r).resolve()) for r in extra_doc_roots),
        default_discovery_used=default_discovery_used,
    )


def _attribute_source_root(
    doc_path: Path,
    repo_root: Path,
    extra_doc_roots: Sequence[Path],
) -> str:
    """Best-effort: which discovery root does this doc belong to?"""
    for root in extra_doc_roots:
        try:
            doc_path.relative_to(root.resolve())
            return str(root.resolve())
        except ValueError:
            continue
    try:
        doc_path.relative_to(repo_root)
        return str(repo_root)
    except ValueError:
        return ""


