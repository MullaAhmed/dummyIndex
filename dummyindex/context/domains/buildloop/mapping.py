"""Map one checklist item to the best-fit equipment item.

Deterministic keyword overlap, no LLM. Real tasks say what to build, never
"implement", so each capability expands through a lexicon of trigger words; an
entry scores the overlap of those words and its name tokens with the item text
(selection rules: ``map_task_to_equipment``). The CLI passes in the parsed,
``agent``-only ``equipment.json`` entries; this module never touches the filesystem.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from ..equip import Capability
from .models import Choice

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A specialist must overlap on at least this many (kind-bonus-weighted)
# tokens before it can out-rank an implement-capable entry: a single
# incidental token is noise, not a routing signal.
_SPECIALIST_MIN_SCORE = 2

# Trigger keywords per capability, keyed off the equip-owned `Capability` enum.
# Matching is EXACT per token (no stemmer), so list the inflected forms tasks
# write (`build`, `builds`). Keep generic words (`copy`, `polish`, `tone`, and
# `comment`, which fires on code items) OUT: they defeat the honest fallback.
_CAPABILITY_LEXICON: Mapping[Capability, frozenset[str]] = {
    Capability.IMPLEMENT: frozenset(
        {
            "implement",
            "implements",
            "build",
            "builds",
            "create",
            "creates",
            "add",
            "adds",
            "construct",
            "constructs",
            "write",
            "writes",
            "register",
            "registers",
            "wire",
            "wires",
            "define",
            "defines",
            "scaffold",
            "scaffolds",
            "modify",
            "modifies",
            "update",
            "updates",
            "refactor",
            "refactors",
            "extend",
            "extends",
            "expose",
            "exposes",
            "mount",
            "mounts",
            "endpoint",
            "route",
            "handler",
            "module",
            "class",
            "function",
            "server",
            "client",
            "method",
            "feature",
        }
    ),
    Capability.TEST: frozenset(
        {
            "test",
            "tests",
            "spec",
            "coverage",
            "fixture",
            "fixtures",
            "pytest",
            "assert",
            "unit",
            "integration",
        }
    ),
    Capability.VERIFY: frozenset(
        {
            "verify",
            "validate",
            "smoke",
            "e2e",
            "check",
        }
    ),
    Capability.REVIEW: frozenset(
        {
            "review",
            "lint",  # `audit` lives in SECURITY to avoid a tie misroute
        }
    ),
    Capability.FORMAT: frozenset(
        {
            "format",
            "formatting",
            "style",
        }
    ),
    Capability.DATABASE: frozenset(
        {
            "database",
            "db",
            "migration",
            "migrations",
            "sql",
            "schema",
            "table",
            "tables",
            "query",
            "index",
            "postgres",
        }
    ),
    Capability.DATA: frozenset(
        {
            "data",
            "pipeline",
            "etl",
            "ingest",
            "transform",
            "dataset",
        }
    ),
    Capability.SECURITY: frozenset(
        {
            "security",
            "secure",
            "audit",
            "auth",
            "authentication",
            "authorization",
            "validation",
            "sanitize",
            "vulnerability",
            "csrf",
            "xss",
            "injection",
            "rls",
            "tenant",
            "tenancy",
            "isolation",
            "rbac",
        }
    ),
    Capability.FRONTEND: frozenset(
        {
            "frontend",
            "component",
            "ui",
            "react",
            "css",
            "page",
            "tsx",
            "jsx",
            "vue",
            "svelte",
            "html",
        }
    ),
    Capability.PERFORMANCE: frozenset(
        {
            "performance",
            "perf",
            "optimize",
            "optimise",
            "latency",
            "throughput",
            "benchmark",
            "profile",
            "cache",
        }
    ),
    Capability.DOCS: frozenset(
        {
            "docs",
            "doc",
            "documentation",
            "readme",
            "changelog",
            "docstring",
        }
    ),
    Capability.SEARCH: frozenset(
        {
            "search",
            "embedding",
            "embeddings",
            "vector",
            "rag",
            "semantic",
            "retrieval",
            "pgvector",
            "index",
        }
    ),
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

    Only specialists get the bonus (``kind_bonus=True``): the implementer is the
    default owner, and boosting it would only raise the specialists' bar.
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

    The best implement-capable entry wins, even at score 0, unless a specialist
    scores >= ``_SPECIALIST_MIN_SCORE`` and strictly more (ties go to the
    implementer; equal specialists keep manifest order). With no implementer the
    best positive scorer wins, else a fallback ``Choice`` (``equipment_name=None``,
    ``fallback=True``). ``grounding`` is passed through verbatim.
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
