"""`build --next` / `--next-wave` handlers — the dispatch-frontier verbs.

Split out of ``cli/build_loop.py`` (which keeps arg parsing + the
``--check``/``--status`` verbs) to hold the dispatcher under the CLI
file-size guideline. Same wire-only discipline: parse nothing, call the
``buildloop`` domain, print. Both verbs share one JSON schema contract:
every payload carries ``complete`` (bool) and, when work remains, the
equipment mapping per item plus the shared ``grounding`` + ``equipped``
signals. Each item entry also carries ``dispatch`` (``subagent`` |
``main-session``), the structural ``gate``/``via`` markers, and — for
main-session items — an ``instruction`` telling the conductor how to handle
it (a GATE is a human decision, never dispatched; a ``— via <tool>`` tag is
a binding directive, never substituted). The ``group`` key on
``--next-wave`` is the item's **opaque 0-based group id** from
``parse_checklist`` — not the ``N`` in the ``## Wave N`` heading text.

Only Task-dispatchable equipment entries (kind ``agent``) join the mapping
pool: skills/hooks/command plugins are execution adapters the via-tag
mechanism routes, never ``subagent_type`` targets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dummyindex.context.domains.buildloop import (
    ChecklistItem,
    DispatchMode,
    dispatch_mode,
)
from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    EquipmentKind,
    EquipmentSource,
    capabilities_from_text,
)

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
RECONCILE_HINT = "dummyindex context reconcile"

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

# Conductor instruction for a GATE item: a human decision, never a Task unit.
_GATE_INSTRUCTION = (
    "GATE — a human decision item: never dispatch it to a subagent. Resolve "
    "it with the user in the main session, then tick it (or record "
    '`--skip <item> --reason "…"` if it is renegotiated).'
)


def _via_instruction(tool: str) -> str:
    """Conductor instruction for a ``— via <tool>`` item: the tag is binding."""
    return (
        f"run `{tool}` from the main session — the `— via` tag is a binding "
        "directive, not a hint. If the tool is unavailable or fails, leave "
        "the item unticked and report; never substitute hand-written output "
        "for what the tool was supposed to produce."
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


def _dispatchable(manifest: list[dict]) -> list[dict]:
    """Restrict the mapping pool to Task-dispatchable entries.

    Skills/hooks/command plugins (``kind != "agent"``) are execution
    adapters, not ``subagent_type`` targets — a single incidental token must
    never let them win the agent match. A missing ``kind`` is treated as
    ``agent`` (legacy manifests predate the field). Among agent entries,
    prefer the ones that actually name a ``subagent_type``; when none does
    (legacy manifest), keep the agent pool so capability matching still
    works — the entry-level honesty flag reports the downgrade.

    Marketplace/vendored plugins are excluded by SOURCE as well as kind:
    schema-v3 manifests recorded plugins as ``kind=agent`` (the v4 PLUGIN kind
    is newer), so a plugin name could otherwise leak into the dispatch pool and
    be launched as a bogus ``subagent_type``. This mirrors the audit roster's
    guard (``audit/catalog.py``) so both manifest consumers agree.
    """
    agent_kind = EquipmentKind.AGENT.value
    plugin_sources = {EquipmentSource.MARKETPLACE.value, EquipmentSource.VENDORED.value}
    agents = [
        it
        for it in manifest
        if str(it.get("kind") or agent_kind) == agent_kind
        and str(it.get("source") or "") not in plugin_sources
    ]
    typed = [it for it in agents if it.get("subagent_type")]
    return typed or agents


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
    pool: list[dict],
    grounding: tuple[str, ...],
) -> dict[str, Any]:
    """Map one checklist item to its dispatch entry (shared by both verbs).

    ``pool`` is the dispatchable subset of the manifest (see
    ``_dispatchable``). GATE and ``— via <tool>`` items never reach the
    agent matcher: they are main-session items with an explicit conductor
    ``instruction`` instead of an agent mapping.
    """
    from dummyindex.context.domains.buildloop import map_task_to_equipment

    mode = dispatch_mode(item)
    base = {
        "index": item.index,
        "text": item.text,
        "dispatch": mode.value,
        "gate": item.gate,
        "via": item.via,
    }
    if mode is DispatchMode.MAIN_SESSION:
        instruction = (
            _GATE_INSTRUCTION if item.gate else _via_instruction(item.via or "")
        )
        return {
            **base,
            "agent": None,
            "subagent_type": None,
            "fallback": False,
            "instruction": instruction,
        }

    choice = map_task_to_equipment(item.text, pool, grounding=grounding)
    fallback = choice.fallback or not choice.subagent_type
    entry = {
        **base,
        "agent": choice.equipment_name if not choice.fallback else _FALLBACK_AGENT,
        # The dispatch target the build skill launches via the Task tool. The
        # equipment item names it (subagent_type); when it didn't, or nothing
        # matched, fall back to the general-purpose agent — and report that
        # downgrade honestly: a match without a subagent_type is a fallback,
        # never a confident equipped match.
        "subagent_type": choice.subagent_type or _FALLBACK_AGENT,
        "fallback": fallback,
        "instruction": None,
    }
    # Missing-capability signal: when NOTHING in the manifest matched
    # (``choice.fallback`` — not merely a matched agent that lacks a
    # subagent_type) AND the item text implies a *specialist* capability
    # (security/db/perf/docs/search/frontend), name it so the conductor can run
    # `equip discover <cap>` and — on explicit user approval — vendor a skill that
    # fills the gap (discovery auto, install gated). Absent when a specialist is
    # already equipped or none is implied; purely additive to the entry.
    if choice.fallback:
        missing = capabilities_from_text(item.text)
        if missing:
            entry["missing_capability"] = list(missing)
    return entry


def _print_entry(entry: dict[str, Any], *, indent: str) -> None:
    if entry["dispatch"] == DispatchMode.MAIN_SESSION.value:
        print(f"{indent}dispatch: main-session — {entry['instruction']}")
        return
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
        print(
            json.dumps(
                {
                    "proposal": proposal,
                    "item": None,
                    "items": [],
                    "complete": True,
                    "next_step": RECONCILE_HINT,
                },
                indent=2,
            )
        )
        return 0
    print(f"build {verb} [{proposal}]: all items checked.")
    print(
        "close the loop by reconciling the new code into .context/ "
        f"(council/65-reconcile.md):\n  {RECONCILE_HINT}"
    )
    return 0


def do_next(
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
    entry = _entry_for(pending, _dispatchable(manifest), grounding)

    if as_json:
        payload = {
            "proposal": proposal,
            "item": {"index": entry["index"], "text": entry["text"]},
            "agent": entry["agent"],
            "subagent_type": entry["subagent_type"],
            "fallback": entry["fallback"],
            "dispatch": entry["dispatch"],
            "gate": entry["gate"],
            "via": entry["via"],
            "instruction": entry["instruction"],
            "equipped": equipped,
            "grounding": list(grounding),
            "complete": False,
        }
        # Optional missing-capability signal (present only on a true specialist
        # fallback) — surfaced so the conductor can run the gated discover→vendor
        # flow. --next-wave already carries it via the full entry dict.
        if "missing_capability" in entry:
            payload["missing_capability"] = entry["missing_capability"]
        print(json.dumps(payload, indent=2))
        return 0

    if not equipped:
        print(_NOT_EQUIPPED_WARNING, file=sys.stderr)
    print(f"build next [{proposal}]: #{entry['index']} {entry['text']}")
    _print_entry(entry, indent="  ")
    _print_grounding(grounding)
    return 0


def do_next_wave(
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
    pool = _dispatchable(manifest)
    entries = [_entry_for(it, pool, grounding) for it in wave]

    if as_json:
        print(
            json.dumps(
                {
                    "proposal": proposal,
                    "group": wave[0].group,  # opaque 0-based id, not the heading's N
                    "items": entries,
                    "equipped": equipped,
                    "grounding": list(grounding),
                    "complete": False,
                },
                indent=2,
            )
        )
        return 0

    if not equipped:
        print(_NOT_EQUIPPED_WARNING, file=sys.stderr)
    main_session = sum(
        1 for e in entries if e["dispatch"] == DispatchMode.MAIN_SESSION.value
    )
    plural = "s" if len(entries) != 1 else ""
    if main_session:
        # Never tell the conductor to dispatch the whole wave: gates and
        # via-tagged items are main-session work.
        print(
            f"build next-wave [{proposal}]: {len(entries)} item{plural} — "
            f"{len(entries) - main_session} subagent (dispatch concurrently, "
            f"verify each, tick each), {main_session} main-session "
            "(handle in THIS session — never dispatch)"
        )
    else:
        print(
            f"build next-wave [{proposal}]: {len(entries)} parallel item{plural} "
            "(dispatch concurrently, verify each, tick each)"
        )
    for entry in entries:
        print(f"  #{entry['index']} {entry['text']}")
        _print_entry(entry, indent="    ")
    _print_grounding(grounding)
    return 0
