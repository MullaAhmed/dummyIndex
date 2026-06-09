"""Map one checklist item to the best-fit equipment item.

Deterministic keyword overlap, no LLM. A capability is a single abstract
word (``implement``, ``test``, ``review``) — but a real implementation task
describes *what* to build and never says "implement". So we expand each
capability through a **lexicon** of trigger keywords (keyed off the
:class:`Capability` enum, the single-source alphabet) before scoring.

For a checklist item's text we tokenise it, then for every equipment item we
score how many of its lexicon-expanded ``capabilities`` tokens (plus its raw
``name`` tokens) appear in the item text. The highest-scoring item wins;
ties break on the item's order in the manifest (stable).

When nothing scores, we don't immediately fall back: if the manifest carries
an implement-capable item, the work *is* implementation, so we route there
(``fallback=False``). Only when the manifest is empty — or has items but no
implement-capable one — do we return a fallback ``Choice`` (``equipment_name
=None`` / ``fallback=True``), which the caller renders as ``general-purpose``.

The equipment manifest is parsed by the CLI (boundary IO) and passed in as
a sequence of plain dicts shaped like Slice B's ``equipment.json`` items
(``{"name": ..., "capabilities": [...]}``). This module never touches the
filesystem.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..equip import Capability
from .models import Choice

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Trigger keywords per capability, keyed off the `Capability` enum so the
# capability alphabet stays single-source (the equip domain owns it). Each set
# expands one abstract capability word into the concrete verbs/nouns a real
# checklist item uses to describe that kind of work. Matching is EXACT per
# token — there is NO stemmer — so include the inflected forms tasks actually
# write (`build` AND `builds`/`constructs`/`registers`), not just the stem.
# Keep generic words (`copy`, `polish`, `tone`) OUT — they'd defeat the
# honest-fallback path. Stdlib-only, deterministic.
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
        "docs", "doc", "documentation", "readme", "changelog", "comment",
        "docstring",
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


def _is_implement_capable(item: Mapping[str, Any]) -> bool:
    """True iff the item advertises the ``implement`` capability."""
    caps = item.get("capabilities") or ()
    if not isinstance(caps, (list, tuple)):
        return False
    return any(str(cap) == Capability.IMPLEMENT.value for cap in caps)


def _match_tokens(item: Mapping[str, Any]) -> set[str]:
    """All tokens this item matches on: its capabilities expanded through the
    lexicon, plus its raw ``name`` tokens. A capability string that isn't in
    the lexicon contributes nothing on its own (its name tokens still count)."""
    toks: set[str] = set()
    caps = item.get("capabilities") or ()
    if isinstance(caps, (list, tuple)):
        for cap in caps:
            toks |= _LEXICON_BY_VALUE.get(str(cap), frozenset())
    name = item.get("name")
    if name:
        toks |= _tokens(str(name))
    return toks


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
    item text; highest score wins, ties break on manifest order. When nothing
    scores, route to the manifest's implement-capable item if one exists (the
    work is implementation); only an empty manifest — or one with no
    implement-capable item — yields a fallback choice (``equipment_name=None``,
    ``fallback=True``). ``grounding`` is threaded through verbatim — the CLI
    supplies the proposal's spec/plan/conventions paths.
    """
    item_toks = _tokens(item_text)
    best_name: str | None = None
    best_subagent: str | None = None
    best_score = 0
    implementer: Mapping[str, Any] | None = None
    for entry in manifest:
        if not isinstance(entry, Mapping):
            continue
        if implementer is None and _is_implement_capable(entry):
            implementer = entry
        score = len(item_toks & _match_tokens(entry))
        if score > best_score:
            best_score = score
            best_name = entry.get("name")
            sub = entry.get("subagent_type")
            best_subagent = str(sub) if sub else None

    if best_name is not None and best_score > 0:
        return Choice(
            item_text=item_text,
            equipment_name=str(best_name),
            fallback=False,
            grounding=grounding,
            subagent_type=best_subagent,
        )

    # Nothing matched. If the repo is equipped with an implementer, the work is
    # implementation — route there rather than general-purpose.
    if implementer is not None:
        sub = implementer.get("subagent_type")
        return Choice(
            item_text=item_text,
            equipment_name=str(implementer.get("name")),
            fallback=False,
            grounding=grounding,
            subagent_type=str(sub) if sub else None,
        )

    # Empty manifest, or items but no implement-capable one: honest fallback.
    return _fallback_choice(item_text, grounding)
