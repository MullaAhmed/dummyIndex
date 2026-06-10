"""`build --next` / `--next-wave` handlers — the dispatch-frontier verbs.

Split out of ``cli/build_loop.py`` (which keeps arg parsing + the
``--check``/``--status`` verbs) to hold the dispatcher under the CLI
file-size guideline. Same wire-only discipline: parse nothing, call the
``buildloop`` domain, print. Both verbs share one JSON schema contract:
every payload carries ``complete`` (bool) and, when work remains, the
equipment mapping per item plus the shared ``grounding`` + ``equipped``
signals. The ``group`` key on ``--next-wave`` is the item's **opaque
0-based group id** from ``parse_checklist`` — not the ``N`` in the
``## Wave N`` heading text.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dummyindex.context.domains.buildloop import ChecklistItem
from dummyindex.context.domains.equip import EQUIPMENT_REL

# Rendered agent name when no equipment item matches (fallback). The domain
# Choice stores equipment_name=None / fallback=True; this literal is the
# CLI/skill-layer render of that fallback.
_FALLBACK_AGENT = "general-purpose"

# A completed build added new code, so a bare `rebuild --changed` would leave
# those files *unassigned* — the deterministic backbone refreshes but no feature
# claims them. The genuine loop-closer is the reconcile procedure: fold the new
# code into the taxonomy (place + enrich), then advance the anchor. `reconcile`
# is the read-only entry that shows what to fold; `council/65-reconcile.md` is
# the procedure the session runs from there.
_RECONCILE_HINT = "dummyindex context reconcile"

# Printed to stderr (human `--next`/`--next-wave`) when the repo has no usable
# equipment manifest — absent, empty, or unparseable, which all collapse to [].
# This is the *not-equipped* signal — distinct from a per-item fallback on an
# equipped repo (where general-purpose is the correct, silent outcome). Worded
# to not assert absence, since a present-but-corrupt file also lands here.
_NOT_EQUIPPED_WARNING = (
    "⚠ no usable .context/equipment.json — this repo isn't equipped. Run "
    "`dummyindex context equip` (or `/dummyindex-equip`) so build can dispatch "
    "project-tuned agents. Falling back to general-purpose."
)


def _load_manifest(context_dir: Path) -> list[dict]:
    """Read ``.context/equipment.json`` → its ``items`` list.

    Tolerates absence (returns ``[]`` → everything falls back). Accepts
    either a top-level list or an object with an ``items`` array, matching
    Slice B's manifest shape loosely so a schema tweak doesn't break us.
    """
    path = context_dir / EQUIPMENT_REL
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or []
    else:
        items = []
    return [it for it in items if isinstance(it, dict)]


def _grounding_paths(proposal_dir: Path, context_dir: Path) -> tuple[str, ...]:
    """Fixed grounding set for a proposal: its spec + plan, plus the repo's
    conventions dir when present. No relevance ranking — just the anchors
    the agent must read before acting."""
    paths: list[str] = []
    for name in ("spec.md", "plan.md"):
        p = proposal_dir / name
        if p.is_file():
            paths.append(str(p))
    conventions = context_dir / "conventions"
    if conventions.is_dir():
        paths.append(str(conventions))
    return tuple(paths)


def _entry_for(
    item: ChecklistItem,
    manifest: list[dict],
    grounding: tuple[str, ...],
) -> dict[str, Any]:
    """Map one checklist item to its dispatch entry (shared by both verbs)."""
    from dummyindex.context.domains.buildloop import map_task_to_equipment

    choice = map_task_to_equipment(item.text, manifest, grounding=grounding)
    return {
        "index": item.index,
        "text": item.text,
        "agent": choice.equipment_name if not choice.fallback else _FALLBACK_AGENT,
        # The dispatch target the build skill launches via the Task tool. The
        # equipment item names it (subagent_type); when it didn't, or nothing
        # matched, fall back to the general-purpose agent.
        "subagent_type": choice.subagent_type or _FALLBACK_AGENT,
        "fallback": choice.fallback,
    }


def _print_entry(entry: dict[str, Any], *, indent: str) -> None:
    tag = " (fallback)" if entry["fallback"] else ""
    print(f"{indent}agent: {entry['agent']}{tag}")
    print(f"{indent}subagent_type: {entry['subagent_type']}")


def _print_grounding(grounding: tuple[str, ...]) -> None:
    if grounding:
        print("  grounding:")
        for g in grounding:
            print(f"    - {g}")
    else:
        print("  grounding: (none found — read spec.md/plan.md if present)")


def _print_all_done(proposal: str, verb: str, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({
            "proposal": proposal,
            "item": None,
            "items": [],
            "complete": True,
            "next_step": _RECONCILE_HINT,
        }, indent=2))
        return 0
    print(f"build {verb} [{proposal}]: all items checked.")
    print(
        "close the loop by reconciling the new code into .context/ "
        f"(council/65-reconcile.md):\n  {_RECONCILE_HINT}"
    )
    return 0


def _do_next(
    items: tuple[ChecklistItem, ...],
    proposal: str,
    proposal_dir: Path,
    context_dir: Path,
    *,
    as_json: bool,
) -> int:
    """Single-item frontier — the serial fallback verb."""
    pending = next((it for it in items if not it.done), None)
    if pending is None:
        return _print_all_done(proposal, "next", as_json=as_json)

    manifest = _load_manifest(context_dir)
    # Boundary signal, not a mapping signal: the repo is "equipped" iff an
    # equipment.json exists and parsed to a manifest with >=1 item. This is
    # distinct from per-item `fallback` (this item matched no specialist).
    # Empty or corrupt JSON parses to [] → not equipped → build should warn.
    equipped = bool(manifest)
    grounding = _grounding_paths(proposal_dir, context_dir)
    entry = _entry_for(pending, manifest, grounding)

    if as_json:
        print(json.dumps({
            "proposal": proposal,
            "item": {"index": entry["index"], "text": entry["text"]},
            "agent": entry["agent"],
            "subagent_type": entry["subagent_type"],
            "fallback": entry["fallback"],
            "equipped": equipped,
            "grounding": list(grounding),
            "complete": False,
        }, indent=2))
        return 0

    if not equipped:
        print(_NOT_EQUIPPED_WARNING, file=sys.stderr)
    print(f"build next [{proposal}]: #{entry['index']} {entry['text']}")
    _print_entry(entry, indent="  ")
    _print_grounding(grounding)
    return 0


def _do_next_wave(
    items: tuple[ChecklistItem, ...],
    proposal: str,
    proposal_dir: Path,
    context_dir: Path,
    *,
    as_json: bool,
) -> int:
    """Wave frontier: every unchecked item in the earliest incomplete wave,
    each with its own equipment mapping. The grounding set is shared
    wave-wide (it is proposal-level, not per-item)."""
    from dummyindex.context.domains.buildloop import next_wave

    wave = next_wave(items)
    if not wave:
        return _print_all_done(proposal, "next-wave", as_json=as_json)

    manifest = _load_manifest(context_dir)
    equipped = bool(manifest)
    grounding = _grounding_paths(proposal_dir, context_dir)
    entries = [_entry_for(it, manifest, grounding) for it in wave]

    if as_json:
        print(json.dumps({
            "proposal": proposal,
            "group": wave[0].group,  # opaque 0-based id, not the heading's N
            "items": entries,
            "equipped": equipped,
            "grounding": list(grounding),
            "complete": False,
        }, indent=2))
        return 0

    if not equipped:
        print(_NOT_EQUIPPED_WARNING, file=sys.stderr)
    plural = "s" if len(entries) != 1 else ""
    print(
        f"build next-wave [{proposal}]: {len(entries)} parallel item{plural} "
        "(dispatch concurrently, verify each, tick each)"
    )
    for entry in entries:
        print(f"  #{entry['index']} {entry['text']}")
        _print_entry(entry, indent="    ")
    _print_grounding(grounding)
    return 0
