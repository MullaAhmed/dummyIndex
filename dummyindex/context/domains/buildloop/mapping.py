"""Map one checklist item to the best-fit equipment item.

Deterministic keyword overlap, no LLM. A capability is a single abstract
word (``implement``, ``test``, ``review``) — but a real implementation task
describes *what* to build and never says "implement". So we expand each
capability through a **lexicon** of trigger keywords (keyed off the
:class:`Capability` enum, the single-source alphabet) before scoring.

For a checklist item's text we tokenise it, then for every equipment item we
score how many of its lexicon-expanded ``capabilities`` tokens (plus its raw
``name`` tokens) appear in the item text.

Selection is **item-kind aware**: the stack implementer is the default owner
of checklist work. A specialist (non-implement-capable entry) only wins with
a real margin — its score must reach ``_SPECIALIST_MIN_SCORE`` *and* beat
the best implement-capable entry's score — so a single incidental token
("review-ready", "comment added") never re-routes implementation work. The
item's **leading token is its verb**: when it belongs to a specialist's
capability lexicon ("Review …", "Test …") that specialist gets a +1 kind
bonus, which is how genuinely review-/test-kind items reach their
specialist even at low overlap. Ties go to the implementer; among
specialists, manifest order breaks ties (stable).

When nothing scores, we don't immediately fall back: if the manifest carries
an implement-capable item, the work *is* implementation, so we route there
(``fallback=False``). Only when the manifest is empty — or has items but no
implement-capable one — do we return a fallback ``Choice`` (``equipment_name
=None`` / ``fallback=True``), which the caller renders as ``general-purpose``.

The equipment manifest is parsed by the CLI (boundary IO) and passed in as
a sequence of plain dicts shaped like Slice B's ``equipment.json`` items
(``{"name": ..., "capabilities": [...]}``). The CLI also pre-filters the
pool to Task-dispatchable entries (kind ``agent``); this module never
touches the filesystem.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..equip import Capability
from .models import Choice

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A specialist must overlap on at least this many (kind-bonus-weighted)
# tokens before it can out-rank an implement-capable entry: a single
# incidental token is noise, not a routing signal.
_SPECIALIST_MIN_SCORE = 2

# Trigger keywords per capability, keyed off the `Capability` enum so the
# capability alphabet stays single-source (the equip domain owns it). Each set
# expands one abstract capability word into the concrete verbs/nouns a real
# checklist item uses to describe that kind of work. Matching is EXACT per
# token — there is NO stemmer — so include the inflected forms tasks actually
# write (`build` AND `builds`/`constructs`/`registers`), not just the stem.
# Keep generic words (`copy`, `polish`, `tone`) OUT — they'd defeat the
# honest-fallback path. (`comment` was dropped from DOCS: it fires on code
# items — "comment added (reads.py:42)" — far more than on docs work.)
# Stdlib-only, deterministic.
_CAPABILITY_LEXICON: Mapping[Capability, frozenset[str]] = {
    Capability.IMPLEMENT: frozenset({
        "implement", "implements", "build", "builds", "create", "creates",
        "add", "adds", "construct", "constructs", "write", "writes",
        "register", "registers", "wire", "wires", "define", "defines",
        "scaffold", "scaffolds", "modify", "modifies", "update", "updates",
        "refactor", "refactors", "extend", "extends", "expose", "exposes",
        "mount", "mounts", "endpoint", "route", "handler", "module", "class",
        "function", "server", "client", "method", "feature",
    }),
    Capability.TEST: frozenset({
        "test", "tests", "spec", "coverage", "fixture", "fixtures", "pytest",
        "assert", "unit", "integration",
    }),
    Capability.VERIFY: frozenset({
        "verify", "validate", "smoke", "e2e", "check",
    }),
    Capability.REVIEW: frozenset({
        "review", "lint",  # `audit` lives in SECURITY to avoid a tie misroute
    }),
    Capability.FORMAT: frozenset({
        "format", "formatting", "style",
    }),
    Capability.DATABASE: frozenset({
        "database", "db", "migration", "migrations", "sql", "schema", "table",
        "tables", "query", "index", "postgres",
    }),
    Capability.DATA: frozenset({
        "data", "pipeline", "etl", "ingest", "transform", "dataset",
    }),
    Capability.SECURITY: frozenset({
        "security", "secure", "audit", "auth", "authentication", "authorization",
        "validation", "sanitize", "vulnerability", "csrf", "xss", "injection",
        "rls", "tenant", "tenancy", "isolation", "rbac",
    }),
    Capability.FRONTEND: frozenset({
        "frontend", "component", "ui", "react", "css", "page", "tsx", "jsx",
        "vue", "svelte", "html",
    }),
    Capability.PERFORMANCE: frozenset({
        "performance", "perf", "optimize", "optimise", "latency", "throughput",
        "benchmark", "profile", "cache",
    }),
    Capability.DOCS: frozenset({
        "docs", "doc", "documentation", "readme", "changelog", "docstring",
    }),
    Capability.SEARCH: frozenset({
        "search", "embedding", "embeddings", "vector", "rag", "semantic",
        "retrieval", "pgvector", "index",
    }),
}

# Value → keyword-set, so a raw manifest capability string ("implement", and
# also non-enum strings like "migration"/"sql") can be resolved by membership
# without ever calling `Capability(...)` (which raises on a non-member).
_LEXICON_BY_VALUE: Mapping[str, frozenset[str]] = {
    cap.value: keywords for cap, keywords in _CAPABILITY_LEXICON.items()
}


def _tokens(text: str) -> set[str]:
    """Lower-case alnum tokens of length >= 2 (drops noise like 'a'/'-')."""
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2}


def _leading_token(text: str) -> str | None:
    """The item's first meaningful token — its verb, which names its kind."""
    for tok in _TOKEN_RE.findall(text.lower()):
        if len(tok) >= 2:
            return tok
    return None


def _is_implement_capable(item: Mapping[str, Any]) -> bool:
    """True iff the item advertises the ``implement`` capability."""
    caps = item.get("capabilities") or ()
    if not isinstance(caps, (list, tuple)):
        return False
    return any(str(cap) == Capability.IMPLEMENT.value for cap in caps)


def _capability_keywords(item: Mapping[str, Any]) -> set[str]:
    """The item's capabilities expanded through the lexicon. A capability
    string that isn't in the lexicon contributes nothing on its own."""
    toks: set[str] = set()
    caps = item.get("capabilities") or ()
    if isinstance(caps, (list, tuple)):
        for cap in caps:
            toks |= _LEXICON_BY_VALUE.get(str(cap), frozenset())
    return toks


def _score(
    item_toks: set[str],
    leading: str | None,
    entry: Mapping[str, Any],
    *,
    kind_bonus: bool,
) -> int:
    """Token overlap (capability lexicon + raw name tokens), plus a +1 kind
    bonus when the item's leading verb belongs to this entry's lexicon.

    The bonus is only granted to specialists (``kind_bonus=True``): it exists
    to let a genuinely review-/test-kind item ("Review …", "Test …") reach
    its specialist — the implementer is the default owner and granting it the
    bonus would only raise the specialists' bar.
    """
    keywords = _capability_keywords(entry)
    match_toks = set(keywords)
    name = entry.get("name")
    if name:
        match_toks |= _tokens(str(name))
    score = len(item_toks & match_toks)
    if kind_bonus and leading is not None and leading in keywords:
        score += 1
    return score


def _choice_for(
    entry: Mapping[str, Any], item_text: str, grounding: tuple[str, ...]
) -> Choice:
    sub = entry.get("subagent_type")
    return Choice(
        item_text=item_text,
        equipment_name=str(entry.get("name")),
        fallback=False,
        grounding=grounding,
        subagent_type=str(sub) if sub else None,
    )


def _fallback_choice(item_text: str, grounding: tuple[str, ...]) -> Choice:
    """The general-purpose fallback: no equipment item owns this work."""
    return Choice(
        item_text=item_text,
        equipment_name=None,
        fallback=True,
        grounding=grounding,
        subagent_type=None,
    )


def map_task_to_equipment(
    item_text: str,
    manifest: Sequence[Mapping[str, Any]],
    *,
    grounding: tuple[str, ...] = (),
) -> Choice:
    """Pick the equipment item whose capabilities best match ``item_text``.

    Returns a ``Choice``. Scoring expands each item's capabilities through the
    capability lexicon (plus its name tokens) and counts the overlap with the
    item text; the item's leading verb adds a +1 kind bonus to entries whose
    lexicon contains it. The best implement-capable entry is the default
    owner: a specialist only wins by scoring >= ``_SPECIALIST_MIN_SCORE``
    *and* strictly outscoring it (ties go to the implementer; specialist ties
    break on manifest order). Without any implement-capable entry the highest
    positive scorer wins; only an empty/never-matching specialist-only
    manifest yields a fallback choice (``equipment_name=None``,
    ``fallback=True``). ``grounding`` is threaded through verbatim — the CLI
    supplies the proposal's spec/plan/conventions paths.
    """
    item_toks = _tokens(item_text)
    leading = _leading_token(item_text)
    best_impl: Mapping[str, Any] | None = None
    impl_score = -1
    best_spec: Mapping[str, Any] | None = None
    spec_score = 0
    for entry in manifest:
        if not isinstance(entry, Mapping):
            continue
        if _is_implement_capable(entry):
            score = _score(item_toks, leading, entry, kind_bonus=False)
            if score > impl_score:
                best_impl, impl_score = entry, score
        else:
            score = _score(item_toks, leading, entry, kind_bonus=True)
            if score > spec_score:
                best_spec, spec_score = entry, score

    if best_impl is not None:
        if (
            best_spec is not None
            and spec_score >= _SPECIALIST_MIN_SCORE
            and spec_score > impl_score
        ):
            return _choice_for(best_spec, item_text, grounding)
        return _choice_for(best_impl, item_text, grounding)

    # No implementer in the manifest: the best-scoring specialist wins.
    if best_spec is not None:
        return _choice_for(best_spec, item_text, grounding)

    # Empty manifest, or items but no match and no implement-capable one.
    return _fallback_choice(item_text, grounding)
