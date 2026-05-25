"""PageIndex-style retrieval over `.context/`.

`dummyindex context query "..."` answers: "given this question, which
feature(s) does it touch, and where in the source should I look?"

The implementation is **deterministic — no LLM in the loop.** Same JSON
the agent walks manually, scored by token overlap with feature names,
summaries, file paths, and symbol names. The CLI is just a convenience
wrapper; nothing it returns is unavailable to a tree-walking agent.

Scoring is intentionally simple. Each query token is matched against:

- ``feature.name``       — weight 5
- ``feature.summary``    — weight 3
- ``file`` basenames     — weight 2
- ``symbol.name``        — weight 2
- ``feature_id``         — weight 1 (cheap signal but noisy)

A token matches case-insensitively against either a whole identifier
(``app == App``) or a substring of a multi-word identifier
(``parse`` in ``parse_body``). Multi-token queries sum across tokens.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1

# Common English stopwords — strip from queries so "how does the auth
# work" reduces to ("auth", "work"). Lowercase only; ASCII only.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does",
    "for", "from", "have", "how", "i", "in", "is", "it", "its", "of",
    "on", "or", "so", "that", "the", "this", "to", "was", "what",
    "when", "where", "which", "who", "why", "with", "will", "you",
    "we", "us", "our", "their", "they", "there", "here", "but",
    "if", "then", "into", "out", "up", "down", "about", "can",
})

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def tokenize(text: str) -> tuple[str, ...]:
    """Lowercase alphanumeric tokens with stopwords + 1-char tokens dropped.

    Splits CamelCase into separate tokens (``ParseBody`` → ``parse``,
    ``body``) so a query of ``parse`` hits both ``parse_body`` and
    ``ParseBody``.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_RE.findall(text or ""):
        for piece in _split_camel_and_snake(raw):
            p = piece.lower()
            if len(p) < 2 or p in _STOPWORDS or p in seen:
                continue
            seen.add(p)
            out.append(p)
    return tuple(out)


def _split_camel_and_snake(token: str) -> list[str]:
    """``ParseBodyV2`` → ``[ParseBodyV2, Parse, Body, V2]``. Keeps the
    original alongside the split pieces so an exact match still scores."""
    pieces: list[str] = [token]
    # Snake_case: split on underscores.
    if "_" in token:
        pieces.extend(p for p in token.split("_") if p)
    # CamelCase: split on uppercase-after-lowercase transitions. Capture
    # trailing digits with their preceding letter run so ``ParseBodyV2``
    # yields ``Parse``, ``Body``, ``V2`` rather than dropping the version
    # number on the floor.
    camel_parts = re.findall(
        r"[A-Z][a-z]+\d*|[a-z]+\d*|[A-Z]+\d*(?![a-z])|\d+", token
    )
    pieces.extend(camel_parts)
    return pieces


@dataclass(frozen=True)
class FeatureScore:
    feature_id: str
    name: str
    summary: Optional[str]
    score: int
    matched_tokens: tuple[str, ...]
    files: tuple[str, ...]
    symbol_hits: tuple[str, ...]   # symbol names that matched, ranked by token coverage
    path: str                      # repo-relative path of the feature folder under .context/


@dataclass(frozen=True)
class Citation:
    path: str         # repo-relative
    range: Optional[tuple[int, int]]
    label: Optional[str]


@dataclass(frozen=True)
class QueryMatch:
    feature: FeatureScore
    excerpt: str
    citations: tuple[Citation, ...]
    estimated_tokens: int


@dataclass(frozen=True)
class QueryResult:
    schema_version: int
    query: str
    tokens: tuple[str, ...]
    matches: tuple[QueryMatch, ...]
    total_estimated_tokens: int
    truncated: bool                 # True if budget cap dropped at least one match
    feature_count_considered: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "query": self.query,
            "tokens": list(self.tokens),
            "feature_count_considered": self.feature_count_considered,
            "truncated": self.truncated,
            "total_estimated_tokens": self.total_estimated_tokens,
            "matches": [
                {
                    "feature_id": m.feature.feature_id,
                    "name": m.feature.name,
                    "summary": m.feature.summary,
                    "score": m.feature.score,
                    "matched_tokens": list(m.feature.matched_tokens),
                    "path": m.feature.path,
                    "files": list(m.feature.files),
                    "symbol_hits": list(m.feature.symbol_hits),
                    "citations": [
                        {"path": c.path, "range": list(c.range) if c.range else None, "label": c.label}
                        for c in m.citations
                    ],
                    "excerpt": m.excerpt,
                    "estimated_tokens": m.estimated_tokens,
                }
                for m in self.matches
            ],
        }


# Tunables. Conservative defaults; CLI exposes overrides.
_DEFAULT_TOP_K = 3
_DEFAULT_BUDGET_TOKENS = 2000
_CHARS_PER_TOKEN = 4              # rough OpenAI-ish heuristic
_NAME_WEIGHT = 5
_SUMMARY_WEIGHT = 3
_FILE_WEIGHT = 2
_SYMBOL_WEIGHT = 2
_FEATURE_ID_WEIGHT = 1
_MAX_SYMBOL_HITS_KEPT = 8         # how many matching symbols per feature to surface


def estimate_tokens(text: str) -> int:
    """Rough token estimate — char-count / 4 with a floor of 1."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def query(
    context_dir: Path,
    query_text: str,
    *,
    top_k: int = _DEFAULT_TOP_K,
    budget_tokens: int = _DEFAULT_BUDGET_TOKENS,
) -> QueryResult:
    """Score every feature against ``query_text``, return the best matches.

    Raises ``FileNotFoundError`` if ``.context/features/INDEX.json``
    doesn't exist — the caller is expected to run ``ingest`` first.
    """
    context_dir = context_dir.resolve()
    features_index = context_dir / "features" / "INDEX.json"
    if not features_index.exists():
        raise FileNotFoundError(features_index)

    tokens = tokenize(query_text)
    if not tokens:
        return QueryResult(
            schema_version=SCHEMA_VERSION,
            query=query_text,
            tokens=(),
            matches=(),
            total_estimated_tokens=0,
            truncated=False,
            feature_count_considered=0,
        )

    payload = json.loads(features_index.read_text(encoding="utf-8"))
    feature_entries = payload.get("features", []) or []
    if not feature_entries:
        return QueryResult(
            schema_version=SCHEMA_VERSION,
            query=query_text,
            tokens=tokens,
            matches=(),
            total_estimated_tokens=0,
            truncated=False,
            feature_count_considered=0,
        )

    symbols_by_feature = _index_symbols_by_feature(context_dir, feature_entries)

    scored: list[FeatureScore] = []
    for entry in feature_entries:
        score = _score_feature(
            entry, tokens,
            symbols_for_feature=symbols_by_feature.get(entry.get("feature_id", ""), ()),
        )
        if score is not None:
            scored.append(score)
    scored.sort(key=lambda s: (-s.score, s.feature_id))

    matches: list[QueryMatch] = []
    used = 0
    truncated = False
    for fs in scored[:top_k]:
        remaining = max(0, budget_tokens - used)
        if remaining < 80:   # not enough room for a useful block
            truncated = True
            break
        match = _build_match(context_dir, fs, tokens, budget=remaining)
        if match is None:
            continue
        matches.append(match)
        used += match.estimated_tokens
        if used >= budget_tokens:
            truncated = (len(matches) < len(scored[:top_k]))
            break

    return QueryResult(
        schema_version=SCHEMA_VERSION,
        query=query_text,
        tokens=tokens,
        matches=tuple(matches),
        total_estimated_tokens=used,
        truncated=truncated,
        feature_count_considered=len(feature_entries),
    )


def _score_feature(
    entry: dict[str, Any],
    tokens: tuple[str, ...],
    *,
    symbols_for_feature: tuple[tuple[str, str], ...],
) -> Optional[FeatureScore]:
    """Score one feature against the query tokens. Returns None when zero."""
    feature_id = str(entry.get("feature_id", "") or "")
    name = str(entry.get("name", feature_id) or "")
    summary = entry.get("summary")
    path = str(entry.get("path", f"features/{feature_id}/") or "")
    fid_l = feature_id.lower()
    name_l = name.lower()
    summary_l = (summary or "").lower()

    matched: list[str] = []
    score = 0
    for tok in tokens:
        token_hit = False
        if tok in fid_l:
            score += _FEATURE_ID_WEIGHT
            token_hit = True
        if tok in name_l:
            score += _NAME_WEIGHT
            token_hit = True
        if tok in summary_l:
            score += _SUMMARY_WEIGHT
            token_hit = True
        if token_hit:
            matched.append(tok)

    # File-basename hits.
    files = entry.get("files") or []
    if not isinstance(files, list):
        files = []
    for fp in files:
        if not isinstance(fp, str):
            continue
        basename = fp.rsplit("/", 1)[-1].lower()
        for tok in tokens:
            if tok in basename:
                score += _FILE_WEIGHT
                if tok not in matched:
                    matched.append(tok)

    # Symbol hits.
    symbol_hits: list[tuple[str, int]] = []
    for sym_name, _sym_path in symbols_for_feature:
        sym_l = sym_name.lower()
        tok_count = sum(1 for tok in tokens if tok in sym_l)
        if tok_count:
            score += _SYMBOL_WEIGHT * tok_count
            symbol_hits.append((sym_name, tok_count))
            for tok in tokens:
                if tok in sym_l and tok not in matched:
                    matched.append(tok)

    if score == 0:
        return None

    symbol_hits.sort(key=lambda kv: (-kv[1], kv[0]))
    top_symbols = tuple(s for s, _ in symbol_hits[:_MAX_SYMBOL_HITS_KEPT])

    # Files cap — feature.json can carry hundreds; the score block only
    # needs enough to be navigable.
    files_kept = tuple(f for f in files if isinstance(f, str))[:20]

    return FeatureScore(
        feature_id=feature_id,
        name=name,
        summary=summary if isinstance(summary, str) else None,
        score=score,
        matched_tokens=tuple(matched),
        files=files_kept,
        symbol_hits=top_symbols,
        path=path,
    )


def _index_symbols_by_feature(
    context_dir: Path, feature_entries: list[dict[str, Any]]
) -> dict[str, tuple[tuple[str, str], ...]]:
    """Group symbols by the feature that owns them.

    Reads `feature.json` per feature for the `members` list, then joins
    against `map/symbols.json` to get readable names + paths. We don't
    walk every JSON file in features/<id>/ — only feature.json.
    """
    by_member: dict[str, tuple[str, str]] = {}
    symbols_json = context_dir / "map" / "symbols.json"
    if symbols_json.exists():
        try:
            payload = json.loads(symbols_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for s in payload.get("symbols", []) or []:
            sid = s.get("symbol_id") or s.get("node_id")
            name = s.get("name")
            path = s.get("path") or ""
            if isinstance(sid, str) and isinstance(name, str):
                by_member[sid] = (name, path if isinstance(path, str) else "")

    out: dict[str, tuple[tuple[str, str], ...]] = {}
    for entry in feature_entries:
        fid = entry.get("feature_id")
        if not isinstance(fid, str):
            continue
        feature_json = context_dir / "features" / fid / "feature.json"
        if not feature_json.exists():
            continue
        try:
            payload = json.loads(feature_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        members = payload.get("members") or []
        pairs: list[tuple[str, str]] = []
        for m in members:
            if isinstance(m, str) and m in by_member:
                pairs.append(by_member[m])
        out[fid] = tuple(pairs)
    return out


def _build_match(
    context_dir: Path,
    fs: FeatureScore,
    tokens: tuple[str, ...],
    *,
    budget: int,
) -> Optional[QueryMatch]:
    """Render an excerpt + citations for one scored feature."""
    feat_dir = context_dir / "features" / fs.feature_id
    citations: list[Citation] = []

    # Citations from symbol hits — they carry a real path; ranges
    # come from map/symbols.json if available.
    sym_paths = _symbol_paths(context_dir, fs.feature_id)
    for sym_name in fs.symbol_hits:
        loc = sym_paths.get(sym_name)
        if loc is None:
            continue
        path, rng = loc
        citations.append(Citation(path=path, range=rng, label=sym_name))
    # Files without specific symbol hits become bare-path citations.
    seen_paths = {c.path for c in citations}
    for fp in fs.files[:5]:
        if fp in seen_paths:
            continue
        citations.append(Citation(path=fp, range=None, label=None))
        seen_paths.add(fp)

    excerpt = _excerpt_from_feature(feat_dir, tokens, budget=budget)
    text_for_estimate = (
        f"## {fs.name}\n{fs.summary or ''}\n{excerpt}\n"
        + "\n".join(f"- {c.path}{':' + str(c.range[0]) if c.range else ''}" for c in citations)
    )
    estimated = estimate_tokens(text_for_estimate)
    if estimated > budget:
        # Shrink the excerpt — citations + header are non-negotiable.
        excerpt = _shrink_excerpt(excerpt, target_tokens=max(40, budget // 2))
        text_for_estimate = (
            f"## {fs.name}\n{fs.summary or ''}\n{excerpt}\n"
            + "\n".join(f"- {c.path}" for c in citations)
        )
        estimated = estimate_tokens(text_for_estimate)

    return QueryMatch(
        feature=fs,
        excerpt=excerpt,
        citations=tuple(citations),
        estimated_tokens=estimated,
    )


def _symbol_paths(
    context_dir: Path, feature_id: str
) -> dict[str, tuple[str, Optional[tuple[int, int]]]]:
    """Map ``symbol_name -> (file_path, range)`` for symbols owned by feature_id.

    Cheap to recompute per match; the alternative (memoizing across
    matches) would require threading state through the query() call
    chain and the wins are small at K=3.
    """
    out: dict[str, tuple[str, Optional[tuple[int, int]]]] = {}
    feature_json = context_dir / "features" / feature_id / "feature.json"
    if not feature_json.exists():
        return out
    try:
        feature_payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    member_ids = {m for m in feature_payload.get("members", []) if isinstance(m, str)}
    if not member_ids:
        return out
    symbols_json = context_dir / "map" / "symbols.json"
    if not symbols_json.exists():
        return out
    try:
        sym_payload = json.loads(symbols_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for s in sym_payload.get("symbols", []) or []:
        sid = s.get("symbol_id") or s.get("node_id")
        if sid not in member_ids:
            continue
        name = s.get("name")
        path = s.get("path") or ""
        rng = s.get("range")
        if isinstance(name, str) and isinstance(path, str):
            range_tuple: Optional[tuple[int, int]] = None
            if isinstance(rng, list) and len(rng) == 2:
                try:
                    range_tuple = (int(rng[0]), int(rng[1]))
                except (TypeError, ValueError):
                    range_tuple = None
            out[name] = (path, range_tuple)
    return out


def _excerpt_from_feature(
    feat_dir: Path, tokens: tuple[str, ...], *, budget: int
) -> str:
    """Pick the most query-relevant paragraph from the feature's markdowns.

    Read order: README.md → architecture.md → implementation.md → product.md.
    Within each, find the first paragraph whose lower-cased text contains
    one of the query tokens. Returns the first hit truncated to budget.
    """
    candidates = ("README.md", "architecture.md", "implementation.md", "product.md")
    char_budget = max(80, budget * _CHARS_PER_TOKEN)
    for name in candidates:
        path = feat_dir / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        para = _best_paragraph(text, tokens)
        if para:
            if len(para) > char_budget:
                return para[: char_budget - 1].rstrip() + "…"
            return para
    return ""


_PARA_BREAK = re.compile(r"\n\s*\n")


def _best_paragraph(text: str, tokens: tuple[str, ...]) -> str:
    """First non-heading paragraph that mentions a query token."""
    if not text:
        return ""
    for raw in _PARA_BREAK.split(text):
        para = raw.strip()
        if not para or para.startswith("#") or para.startswith("```"):
            continue
        lower = para.lower()
        if any(tok in lower for tok in tokens):
            return para
    return ""


def _shrink_excerpt(text: str, *, target_tokens: int) -> str:
    if not text:
        return text
    char_target = max(40, target_tokens * _CHARS_PER_TOKEN)
    if len(text) <= char_target:
        return text
    return text[: char_target - 1].rstrip() + "…"


# ----- Markdown renderer (for `dummyindex context query` CLI) ---------------


def render_markdown(result: QueryResult) -> str:
    """Render a QueryResult as the markdown the CLI prints by default."""
    if not result.matches:
        if not result.tokens:
            return (
                "# query\n\n"
                "_(query reduced to zero tokens after stopword filtering — "
                "nothing to look up.)_\n"
            )
        return (
            f"# query: {result.query!r}\n\n"
            f"_No feature matched the query tokens "
            f"{list(result.tokens)} across "
            f"{result.feature_count_considered} feature(s)._\n"
        )
    lines: list[str] = [f"# query: {result.query!r}", ""]
    lines.append(
        f"_{len(result.matches)} match(es), "
        f"~{result.total_estimated_tokens} tokens"
        f"{' (truncated by budget)' if result.truncated else ''}._"
    )
    lines.append("")
    for m in result.matches:
        lines.append(f"## {m.feature.name}  ·  `{m.feature.feature_id}` (score {m.feature.score})")
        lines.append("")
        if m.feature.summary:
            lines.append(m.feature.summary)
            lines.append("")
        if m.feature.matched_tokens:
            lines.append(
                "**Matched tokens:** "
                + ", ".join(f"`{t}`" for t in m.feature.matched_tokens)
            )
            lines.append("")
        if m.excerpt:
            lines.append(m.excerpt)
            lines.append("")
        if m.citations:
            lines.append("**Citations:**")
            lines.append("")
            for c in m.citations:
                loc = f":{c.range[0]}" if c.range else ""
                label = f" — `{c.label}`" if c.label else ""
                lines.append(f"- `{c.path}{loc}`{label}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(result: QueryResult) -> str:
    return json.dumps(result.to_dict(), indent=2) + "\n"
