"""Source-doc catalog with staleness signals.

The deterministic backbone produces a `.context/source-docs/` folder that
catalogs every prose document found in (or linked into) the repo:
README, CHANGELOG, ARCHITECTURE, docs/, ADR/, RFC/, and any extra paths
passed via `--docs PATH`.

The catalog is **explicitly advisory**. Docs drift faster than code, so
every entry carries:

- ``broken_refs`` — backtick-wrapped code identifiers or file paths that
  no longer match the current AST extraction (the strongest staleness
  signal).
- ``age_delta_seconds`` — doc mtime vs. newest code mtime; positive means
  the doc was last touched *before* the newest code change.
- ``confidence`` — derived bucket ``high`` / ``medium`` / ``low`` so the
  enrichment council can weight authoritative prose over rotted prose.

No LLM calls. Everything in this module is deterministic.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

SCHEMA_VERSION = 1

# ----- Discovery ------------------------------------------------------------

# In-repo paths checked when no --docs is given. Names are case-insensitive
# at match time; presence-only check (no globbing of unknown extensions).
_DEFAULT_DOC_FILES: tuple[str, ...] = (
    "README.md", "README.rst", "README.txt",
    "CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG.txt",
    "ARCHITECTURE.md", "ARCHITECTURE.rst",
    "SECURITY.md",
    "BRIEF.md",
    "CONTRIBUTING.md",
    "ROADMAP.md",
    "DESIGN.md",
)
_DEFAULT_DOC_DIRS: tuple[str, ...] = (
    "docs", "doc", "documentation",
    "adr", "ADR",
    "rfc", "RFC", "rfcs",
    ".changeset", "changes",
)

# Doc-like file extensions tracked in the catalog.
_DOC_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".mdx", ".rst", ".txt",
    ".pdf",
    ".html", ".htm",
    ".docx", ".xlsx",  # office files already get converted to .md sidecars upstream
})


def discover_default_doc_paths(repo_root: Path) -> list[Path]:
    """Return absolute paths of in-repo default doc locations that exist.

    Walks the well-known doc file names plus any directory in
    ``_DEFAULT_DOC_DIRS``. Also includes every top-level ``*.md`` file at
    the repo root (catches less-conventional names like ``BRIEF.md``).
    The returned list is deduplicated and sorted.
    """
    repo_root = repo_root.resolve()
    seen: set[Path] = set()
    out: list[Path] = []

    def _take(p: Path) -> None:
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


# ----- Reference extraction -------------------------------------------------

# Backtick-wrapped tokens — `like_this` or `foo.bar()`. We deliberately
# skip triple-backtick code fences (those are full listings; checking
# every token in them would produce noise, not signal).
_INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]{1,160})`(?!`)")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# A reference is "code-like" if it has at least one of these shapes.
_CAMEL_RE = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$")
_FILE_PATH_RE = re.compile(r"^[\w./\-]+\.[A-Za-z0-9]{1,6}$")
_DOTTED_RE = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+(?:\(\))?$")
_SNAKE_CALL_RE = re.compile(r"^[A-Za-z_][\w]*\(\)$")
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")

# Tokens we never treat as code references, even in backticks.
_PROSE_WHITELIST: frozenset[str] = frozenset({
    "true", "false", "null", "none", "todo", "note", "fixme",
    "yes", "no", "ok", "nil",
})


def looks_like_code_ref(token: str) -> bool:
    """Heuristic: does this backtick token name code, not prose?

    Conservative — we'd rather miss some refs than flag English prose
    in backticks as broken. Accepted shapes:

    - file path with extension (``app.py``, ``docs/x.md``)
    - dotted identifier (``foo.bar``, ``App.run()``)
    - function call (``helper()``)
    - snake_case (``make_app``) — multiple-word lowercase identifier
    - CamelCase / TitleCase identifier with at least one lowercase letter
      that starts with uppercase (``App``, ``MyClass``)
    """
    t = token.strip()
    if not t or len(t) > 160 or t.lower() in _PROSE_WHITELIST:
        return False
    if " " in t:  # `let x = 1` style — too noisy to verify, drop.
        return False
    if _FILE_PATH_RE.match(t):
        return True
    if _DOTTED_RE.match(t):
        return True
    if _SNAKE_CALL_RE.match(t):
        return True
    if _SNAKE_RE.match(t):
        return True
    if _CAMEL_RE.match(t):
        return True
    # Capitalized single word (e.g. `App`) — accept if it's >=2 chars,
    # starts uppercase, and has at least one lowercase letter. This
    # catches single-name class references without grabbing every
    # English noun (whitelist + length filter handles edge cases).
    if (
        len(t) >= 2
        and t[0].isupper()
        and any(c.islower() for c in t[1:])
        and all(c.isalnum() or c == "_" for c in t)
    ):
        return True
    return False


def _normalize_symbol(token: str) -> str:
    """Strip ``()`` / leading dot decorations so we can compare to symbol names."""
    t = token.strip()
    if t.endswith("()"):
        t = t[:-2]
    if t.startswith("."):
        t = t[1:]
    return t


def extract_doc_text(path: Path) -> str:
    """Return plain text for a doc file.

    Markdown / rst / txt / html are read directly. PDFs go through
    ``pipeline.detect.extract_pdf_text``. Office files (.docx / .xlsx)
    have already been converted to markdown sidecars upstream — if we're
    handed a raw .docx here, we try the converters but tolerate failure.
    """
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from dummyindex.pipeline.detect import extract_pdf_text
            return extract_pdf_text(path)
        if ext == ".docx":
            from dummyindex.pipeline.detect import docx_to_markdown
            return docx_to_markdown(path)
        if ext == ".xlsx":
            from dummyindex.pipeline.detect import xlsx_to_markdown
            return xlsx_to_markdown(path)
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def extract_title_and_headings(text: str) -> tuple[Optional[str], tuple[str, ...]]:
    """Return ``(title, headings)`` from a markdown-like document.

    Title is the first ``# `` heading; headings is every H1 / H2 in order.
    If the doc has no headings, title falls back to the first non-empty
    paragraph line (truncated).
    """
    headings: list[str] = []
    title: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        m = _HEADING_RE.match(line.lstrip("> "))
        if not m:
            continue
        depth = len(m.group(1))
        text_part = m.group(2).strip()
        if not text_part:
            continue
        if depth in (1, 2):
            headings.append(text_part)
            if title is None and depth == 1:
                title = text_part

    if title is None:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                title = stripped[:120]
                break

    return title, tuple(headings)


def extract_code_refs(text: str) -> tuple[str, ...]:
    """Pull every distinct backticked code-shaped token out of ``text``."""
    # Strip fenced code blocks — they're full listings, not references.
    stripped = _CODE_FENCE_RE.sub("", text)
    refs: list[str] = []
    seen: set[str] = set()
    for m in _INLINE_CODE_RE.finditer(stripped):
        token = m.group(1).strip()
        if not looks_like_code_ref(token):
            continue
        if token in seen:
            continue
        seen.add(token)
        refs.append(token)
    return tuple(refs)


def find_broken_refs(
    refs: Sequence[str],
    *,
    symbol_names: frozenset[str],
    file_paths: frozenset[str],
) -> tuple[str, ...]:
    """Return refs that don't match any current symbol or file path.

    A ref matches a file if it equals any known repo-relative path,
    matches a path's basename, or is a directory prefix of one.
    A ref matches a symbol if its normalized form (without ``()`` or
    leading dot) equals a known symbol name, or if any dotted segment
    matches a symbol name (so ``parser.parse_body`` matches when
    ``parse_body`` exists).
    """
    file_basenames: frozenset[str] = frozenset(
        p.rsplit("/", 1)[-1] for p in file_paths
    )
    broken: list[str] = []
    for ref in refs:
        if _ref_matches(ref, symbol_names, file_paths, file_basenames):
            continue
        broken.append(ref)
    return tuple(broken)


def _ref_matches(
    ref: str,
    symbol_names: frozenset[str],
    file_paths: frozenset[str],
    file_basenames: frozenset[str],
) -> bool:
    if ref in file_paths:
        return True
    if "/" in ref:
        # could be a sub-path prefix — match against any file that contains it.
        if any(fp.endswith(ref) or fp == ref for fp in file_paths):
            return True
    base = ref.rsplit("/", 1)[-1]
    if base in file_basenames:
        return True
    norm = _normalize_symbol(ref)
    if norm in symbol_names:
        return True
    # Dotted name (foo.bar.baz / foo.bar() / Class.method) — accept if the
    # rightmost segment exists; that's the part most likely to be a real
    # symbol the AST extractor captured.
    if "." in norm:
        tail = norm.rsplit(".", 1)[-1]
        if tail in symbol_names:
            return True
    return False


# ----- Catalog data shapes --------------------------------------------------


# Bucket for `age_delta_seconds` → human label and confidence weight.
_AGE_BUCKETS: tuple[tuple[float, str], ...] = (
    (-1, "fresh"),                # negative — doc newer than newest code
    (30 * 86400, "recent"),
    (90 * 86400, "aging"),
    (180 * 86400, "stale"),
    (float("inf"), "old"),
)

_HIGH_BROKEN_RATIO = 0.05    # ≤5% broken refs → still trust the doc
_LOW_BROKEN_RATIO = 0.30     # ≥30% broken refs → don't trust it


@dataclass(frozen=True)
class DocEntry:
    path: str                # repo-relative POSIX path (or absolute for external)
    abs_path: str            # absolute path on disk (audit trail for external docs)
    doc_type: str            # markdown / rst / pdf / html / docx / xlsx / txt
    title: Optional[str]
    headings: tuple[str, ...]
    sha256: str
    size_bytes: int
    mtime: float
    age_delta_seconds: Optional[float]   # mtime(doc) - newest code mtime; None if no code
    age_bucket: str
    referenced_count: int
    broken_refs: tuple[str, ...]
    broken_ratio: float
    confidence: str          # "high" | "medium" | "low"
    is_external: bool        # came from --docs PATH outside the repo
    source_root: str         # POSIX absolute of the discovery root that found this

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "abs_path": self.abs_path,
            "doc_type": self.doc_type,
            "title": self.title,
            "headings": list(self.headings),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "age_delta_seconds": self.age_delta_seconds,
            "age_bucket": self.age_bucket,
            "referenced_count": self.referenced_count,
            "broken_refs": list(self.broken_refs),
            "broken_ratio": round(self.broken_ratio, 4),
            "confidence": self.confidence,
            "is_external": self.is_external,
            "source_root": self.source_root,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocEntry":
        return cls(
            path=str(payload.get("path", "")),
            abs_path=str(payload.get("abs_path", "")),
            doc_type=str(payload.get("doc_type", "markdown")),
            title=payload.get("title"),
            headings=tuple(payload.get("headings", ())),
            sha256=str(payload.get("sha256", "")),
            size_bytes=int(payload.get("size_bytes", 0)),
            mtime=float(payload.get("mtime", 0.0)),
            age_delta_seconds=(
                None if payload.get("age_delta_seconds") is None
                else float(payload["age_delta_seconds"])
            ),
            age_bucket=str(payload.get("age_bucket", "unknown")),
            referenced_count=int(payload.get("referenced_count", 0)),
            broken_refs=tuple(payload.get("broken_refs", ())),
            broken_ratio=float(payload.get("broken_ratio", 0.0)),
            confidence=str(payload.get("confidence", "medium")),
            is_external=bool(payload.get("is_external", False)),
            source_root=str(payload.get("source_root", "")),
        )


@dataclass(frozen=True)
class DocCatalog:
    schema_version: int
    generated_at: str
    repo_root: str
    docs: tuple[DocEntry, ...]
    extra_doc_roots: tuple[str, ...] = ()
    default_discovery_used: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "repo_root": self.repo_root,
            "default_discovery_used": self.default_discovery_used,
            "extra_doc_roots": list(self.extra_doc_roots),
            "doc_count": len(self.docs),
            "by_confidence": _confidence_breakdown(self.docs),
            "docs": [d.to_dict() for d in self.docs],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocCatalog":
        return cls(
            schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
            generated_at=str(payload.get("generated_at", "")),
            repo_root=str(payload.get("repo_root", "")),
            docs=tuple(DocEntry.from_dict(d) for d in payload.get("docs", [])),
            extra_doc_roots=tuple(payload.get("extra_doc_roots", ())),
            default_discovery_used=bool(payload.get("default_discovery_used", True)),
        )


def _confidence_breakdown(docs: Iterable[DocEntry]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for d in docs:
        counts[d.confidence] = counts.get(d.confidence, 0) + 1
    return counts


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


def _classify_confidence(broken_ratio: float, age_bucket: str) -> str:
    if broken_ratio >= _LOW_BROKEN_RATIO:
        return "low"
    if age_bucket in ("stale", "old") and broken_ratio > 0:
        return "low"
    if broken_ratio <= _HIGH_BROKEN_RATIO and age_bucket in ("fresh", "recent"):
        return "high"
    if broken_ratio <= _HIGH_BROKEN_RATIO and age_bucket == "unknown":
        return "high"
    return "medium"


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
    now: Optional[_dt.datetime] = None,
) -> DocCatalog:
    """Compute the catalog for ``doc_paths`` against the current AST state."""
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
            refs, symbol_names=symbol_names, file_paths=file_paths
        )
        broken_ratio = (len(broken) / len(refs)) if refs else 0.0

        age_delta: Optional[float]
        if newest_code_mtime is None:
            age_delta = None
        else:
            age_delta = newest_code_mtime - stat.st_mtime
        age_bucket = _classify_age(age_delta)
        confidence = _classify_confidence(broken_ratio, age_bucket)

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
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    entries.sort(key=lambda e: (confidence_order.get(e.confidence, 3), e.path))

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


# ----- Writers --------------------------------------------------------------


_ADVISORY_BANNER = (
    "> **Advisory — verify before quoting.** This catalog is generated from "
    "prose checked into the repo. Docs drift faster than code. Every entry "
    "carries a `confidence` (high / medium / low) derived from how many of "
    "its backticked code references still match the current AST. Treat "
    "high-confidence docs as hypotheses worth quoting; cross-check "
    "medium-confidence docs against `../map/symbols.json` and `../tree.json`; "
    "treat low-confidence docs as historical context only.\n"
)


def write_catalog(context_dir: Path, catalog: DocCatalog) -> tuple[Path, Path]:
    """Write ``source-docs/INDEX.json`` and ``source-docs/INDEX.md``."""
    out_dir = context_dir / "source-docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "INDEX.json"
    md_path = out_dir / "INDEX.md"

    payload = catalog.to_dict()
    _atomic_write(json_path, json.dumps(payload, indent=2, sort_keys=False) + "\n")
    _atomic_write(md_path, _render_catalog_md(catalog))
    return json_path, md_path


def _render_catalog_md(catalog: DocCatalog) -> str:
    by_conf = _confidence_breakdown(catalog.docs)
    lines: list[str] = []
    lines.append("# Existing documentation (source-docs)")
    lines.append("")
    lines.append(_ADVISORY_BANNER.rstrip())
    lines.append("")
    lines.append(
        f"_{len(catalog.docs)} doc(s) — "
        f"{by_conf.get('high', 0)} high · "
        f"{by_conf.get('medium', 0)} medium · "
        f"{by_conf.get('low', 0)} low._"
    )
    lines.append("")
    if catalog.extra_doc_roots:
        lines.append("**External doc roots (passed via `--docs`):**")
        lines.append("")
        for root in catalog.extra_doc_roots:
            lines.append(f"- `{root}`")
        lines.append("")
    if not catalog.docs:
        lines.append(
            "_No documents discovered. Pass `--docs PATH` (repeatable) to "
            "point dummyindex at doc folders outside the scan root._"
        )
        lines.append("")
        return "\n".join(lines) + "\n"

    lines.append("| Doc | Type | Confidence | Broken refs | Age |")
    lines.append("|---|---|---|---|---|")
    for d in catalog.docs:
        broken = f"{len(d.broken_refs)} / {d.referenced_count}" if d.referenced_count else "—"
        title_part = f" — {d.title}" if d.title else ""
        lines.append(
            f"| [`{d.path}`]({_md_link_target(d)}){title_part} | "
            f"{d.doc_type} | **{d.confidence}** | {broken} | {d.age_bucket} |"
        )
    lines.append("")

    low_conf = [d for d in catalog.docs if d.confidence == "low"]
    if low_conf:
        lines.append("## Low-confidence docs")
        lines.append("")
        lines.append(
            "These have broken references or are significantly older than "
            "the newest code change. Don't quote without verifying against "
            "current source."
        )
        lines.append("")
        for d in low_conf:
            lines.append(f"### `{d.path}`")
            lines.append("")
            if d.broken_refs:
                shown = list(d.broken_refs[:10])
                more = max(0, len(d.broken_refs) - len(shown))
                lines.append("**Broken references** (no longer in the AST):")
                lines.append("")
                for ref in shown:
                    lines.append(f"- `{ref}`")
                if more:
                    lines.append(f"- _… +{more} more_")
                lines.append("")
            if d.age_bucket in ("stale", "old") and d.age_delta_seconds is not None:
                days = int(d.age_delta_seconds // 86400)
                lines.append(
                    f"_Last edited {days} day(s) before the newest code change._"
                )
                lines.append("")
    return "\n".join(lines) + "\n"


def _md_link_target(entry: DocEntry) -> str:
    """Make a relative link from source-docs/INDEX.md back to the doc.

    For in-repo docs, escape up one level (we're in .context/source-docs/).
    For external docs, link via the absolute path (won't render as a click
    target on most viewers, but is at least informative).
    """
    if entry.is_external:
        return entry.abs_path
    return f"../../{entry.path}"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ----- Catalog readers ------------------------------------------------------


def read_catalog(context_dir: Path) -> Optional[DocCatalog]:
    path = context_dir / "source-docs" / "INDEX.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return DocCatalog.from_dict(payload)
