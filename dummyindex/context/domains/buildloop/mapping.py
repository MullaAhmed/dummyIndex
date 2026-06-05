"""Map one checklist item to the best-fit equipment item.

Deterministic keyword overlap, no LLM. For a checklist item's text we
tokenise it, then score every equipment item by how many of its
``capabilities`` (and ``name``) tokens appear in the item text. The
highest-scoring item wins; ties break on the item's order in the manifest
(stable). When nothing overlaps, the result is a fallback ``Choice`` with
``equipment_name=None`` / ``fallback=True`` — the caller renders the
``general-purpose`` agent at that point.

The equipment manifest is parsed by the CLI (boundary IO) and passed in as
a sequence of plain dicts shaped like Slice B's ``equipment.json`` items
(``{"name": ..., "capabilities": [...]}``). This module never touches the
filesystem.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .models import Choice

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lower-case alnum tokens of length >= 2 (drops noise like 'a'/'-')."""
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= 2}


def _capability_tokens(item: Mapping[str, Any]) -> set[str]:
    """All tokens an equipment item advertises: its capabilities + name."""
    toks: set[str] = set()
    caps = item.get("capabilities") or ()
    if isinstance(caps, (list, tuple)):
        for cap in caps:
            toks |= _tokens(str(cap))
    name = item.get("name")
    if name:
        toks |= _tokens(str(name))
    return toks


def map_task_to_equipment(
    item_text: str,
    manifest: Sequence[Mapping[str, Any]],
    *,
    grounding: tuple[str, ...] = (),
) -> Choice:
    """Pick the equipment item whose capabilities best match ``item_text``.

    Returns a ``Choice``. On no overlap (or empty manifest), returns a
    fallback choice (``equipment_name=None``, ``fallback=True``).
    ``grounding`` is threaded through verbatim — the CLI supplies the
    proposal's spec/plan/conventions paths.
    """
    item_toks = _tokens(item_text)
    best_name: str | None = None
    best_subagent: str | None = None
    best_score = 0
    for entry in manifest:
        if not isinstance(entry, Mapping):
            continue
        score = len(item_toks & _capability_tokens(entry))
        if score > best_score:
            best_score = score
            best_name = entry.get("name")
            sub = entry.get("subagent_type")
            best_subagent = str(sub) if sub else None

    if best_name is None or best_score == 0:
        return Choice(
            item_text=item_text,
            equipment_name=None,
            fallback=True,
            grounding=grounding,
            subagent_type=None,
        )
    return Choice(
        item_text=item_text,
        equipment_name=str(best_name),
        fallback=False,
        grounding=grounding,
        subagent_type=best_subagent,
    )
