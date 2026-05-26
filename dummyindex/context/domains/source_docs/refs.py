"""Reference extraction from doc prose.

`extract_code_refs` pulls backticked snippets that look like code refs;
`find_broken_refs` cross-checks them against the AST symbol set;
`extract_title_and_headings` pulls Markdown headings for indexing.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Sequence


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

# Identifiers from frameworks the project consumes but doesn't define.
# These will never appear in the project's AST yet they're legitimate
# references in docs — don't flag them broken.
_FRAMEWORK_WHITELIST: frozenset[str] = frozenset({
    # Claude Code tool names.
    "Task", "Read", "Write", "Edit", "Bash", "Grep", "Glob",
    "WebFetch", "WebSearch", "MultiEdit", "NotebookEdit",
    # Claude Code hook event names.
    "PreToolUse", "PostToolUse", "SessionStart", "Stop",
    "Notification", "SubagentStop", "UserPromptSubmit",
    # Common skill / config keys.
    "subagent_type", "subagent_types",
    # Misc tools / commands users will reference in prose.
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList",
    # dummyindex's own .context/ schema — generated artifacts that
    # don't appear in any project AST, but are real and stable.
    # Filenames + JSON field names users reference when documenting
    # how dummyindex builds .context/.
    "tree.json", "meta.json", "feature.json", "graph.json", "graph.html",
    "symbol-graph.json", "manifest.json", "INDEX.json", "INDEX.md",
    "naming.json", "naming.md", "files.json", "symbols.json",
    "PROJECT.md", "HOW_TO_USE.md", "HOW_TO_NAVIGATE.md",
    "COMMUNITIES.md", "CLAUDE.md", "ARCHITECTURE.md", "SECURITY.md",
    "BRIEF.md", "CHANGELOG.md",
    "_council-log.json", "_review-key.json", "_enrich_plan.json",
    "_structural-plan.json", "_structural-log.json",
    # Per-feature council outputs (Stage 1 audit trail).
    "01-architect.md", "02-senior-developer.md", "03-database-engineer.md",
    "04-security-analyst.md", "05-product-manager.md",
    "10-reviews.md", "20-chairman.md",
    # Per-feature synthesized docs the chairman writes.
    "spec.md", "plan.md", "concerns.md",
    "architecture.md", "implementation.md", "data-model.md",
    "security.md", "product.md",
    # docs.md is dummyindex's own per-feature doc pointer file.
    "docs.md", "supporting.md",
    # dummyindex schema field names.
    "schema_version", "node_id", "feature_id", "flow_id", "flow_ids",
    "broken_refs", "broken_ratio", "confidence", "age_bucket",
    "age_delta_seconds", "referenced_count", "is_external",
    "source_root", "by_confidence", "extra_doc_roots",
    "default_discovery_used", "doc_count", "doc_type",
    "member_count", "file_count", "entry_point_count", "flow_count",
    "step_count", "parent_id", "size_bytes",
    "entry_point", "entry_point_label", "entry_point_path",
    "EXTRACTED", "INFERRED",
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
            from dummyindex.pipeline.io.detect import extract_pdf_text
            return extract_pdf_text(path)
        if ext == ".docx":
            from dummyindex.pipeline.io.detect import docx_to_markdown
            return docx_to_markdown(path)
        if ext == ".xlsx":
            from dummyindex.pipeline.io.detect import xlsx_to_markdown
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
    extra_names: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Return refs that don't match any current symbol, file, or known name.

    Match precedence:

    1. Exact-path match against ``file_paths``.
    2. Sub-path-suffix match (``api/users.py`` matches
       ``src/api/users.py``).
    3. Basename match (``runner.py`` matches ``foo/runner.py``).
    4. Normalized-symbol match against ``symbol_names`` (strips ``()`` and
       leading ``.``).
    5. Dotted-tail match (``parser.parse_body`` matches when
       ``parse_body`` is a known symbol).
    6. ``_FRAMEWORK_WHITELIST`` — Claude Code tools, hook events, etc.
    7. ``extra_names`` — caller-supplied superset (e.g. JSON keys harvested
       from repo .json files, words from doc titles, etc.). This is the
       hook for projects whose docs cite schema field names that aren't
       Python/JS symbols.
    """
    file_basenames: frozenset[str] = frozenset(
        p.rsplit("/", 1)[-1] for p in file_paths
    )
    broken: list[str] = []
    for ref in refs:
        if _ref_matches(
            ref, symbol_names, file_paths, file_basenames, extra_names
        ):
            continue
        broken.append(ref)
    return tuple(broken)


def _ref_matches(
    ref: str,
    symbol_names: frozenset[str],
    file_paths: frozenset[str],
    file_basenames: frozenset[str],
    extra_names: frozenset[str],
) -> bool:
    if ref in _FRAMEWORK_WHITELIST:
        return True
    if ref in file_paths:
        return True
    if "/" in ref:
        # could be a sub-path prefix — match against any file that contains it.
        if any(fp.endswith(ref) or fp == ref for fp in file_paths):
            return True
    base = ref.rsplit("/", 1)[-1]
    if base in file_basenames:
        return True
    if base in _FRAMEWORK_WHITELIST:
        # Whitelist hit via the basename — `map/files.json` resolves
        # because `files.json` is whitelisted, even when the path-set
        # doesn't include the file (e.g. .context/ artifacts on first
        # build).
        return True
    norm = _normalize_symbol(ref)
    if norm in symbol_names or norm in extra_names:
        return True
    if norm in _FRAMEWORK_WHITELIST:
        return True
    # Dotted name (foo.bar.baz / foo.bar() / Class.method) — accept if the
    # rightmost segment exists; that's the part most likely to be a real
    # symbol the AST extractor captured.
    if "." in norm:
        tail = norm.rsplit(".", 1)[-1]
        if tail in symbol_names or tail in extra_names:
            return True
        if tail in _FRAMEWORK_WHITELIST:
            return True
    return False

