"""`build --next` / `--next-wave` handlers: the dispatch-frontier verbs (wire-only).

Every payload carries ``complete``; while work remains each item entry has its equipment
mapping, ``dispatch`` (``subagent`` | ``main-session``), ``gate``/``via``, ``instruction``
and ``upgrade_note``, beside the shared ``grounding``, ``equipped`` and ``routing``.
``--next-wave``'s ``group`` is the opaque 0-based id from ``parse_checklist``, not the
``N`` in ``## Wave N``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dummyindex.context.domains.buildloop import (
    AGENT_VIA_PREFIX,
    BuildLoopError,
    ChecklistItem,
    DispatchMode,
    dispatch_mode,
    resolve_routing,
)
from dummyindex.context.domains.buildloop.checklist_lint import live_items
from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    EquipmentKind,
    EquipmentSource,
    capabilities_from_text,
)
from dummyindex.context.domains.equip.enums import Dimension

# Rendered agent name when no equipment item matches (fallback). The domain
# Choice stores equipment_name=None / fallback=True; this literal is the
# CLI/skill-layer render of that fallback.
_FALLBACK_AGENT = "general-purpose"

# A finished build added code that `rebuild --changed` would leave unassigned to any
# feature, so the loop closes with the skill's reconcile procedure (place + enrich,
# then advance the anchor). `reconcile` is its read-only entry point.
RECONCILE_HINT = "dummyindex context reconcile"

# Printed to stderr by human `--next`/`--next-wave` when equipment.json is absent, empty
# or unparseable (all collapse to []). Distinct from the silent per-item fallback on an
# equipped repo; worded not to assert absence, since a corrupt file lands here too.
_NOT_EQUIPPED_WARNING = (
    "⚠ no usable .context/equipment.json. Continue with native subagents; "
    "`dummyindex context equip apply` prepares shared project capabilities."
)

# Conductor instruction for a GATE item: a human decision, never a Task unit.
_GATE_INSTRUCTION = (
    "GATE — a human decision item: never dispatch it to a subagent. Resolve "
    "it with the user in the main session, then tick it (or record "
    '`--skip <item> --reason "…"` if it is renegotiated).'
)


def resolved_auto_recouncil(context_dir: Path) -> bool:
    """The resolved ``build.auto_recouncil`` policy (config schema v5).

    Default True (recouncil after the final wave) when no config exists or a
    malformed one fails the read — the default-on ruling must survive a bad
    config rather than silently disabling the closing phase.
    """
    from dummyindex.context.domains.config import ConfigError, read_config

    try:
        config = read_config(context_dir)
    except ConfigError:
        return True
    if config is None:
        return True
    return config.build.auto_recouncil


def _via_instruction(tool: str) -> str:
    """Conductor instruction for a ``— via <tool>`` item: the tag is binding."""
    return (
        f"run `{tool}` from the main session — the `— via` tag is a binding "
        "directive, not a hint. If the tool is unavailable or fails, leave "
        "the item unticked and report; never substitute hand-written output "
        "for what the tool was supposed to produce."
    )


# Conductor instruction for an agent-tag that matched no pool entry: the
# safe degradation path (report/escalate), never a bogus Task launch.
_AGENT_TAG_WARNING_INSTRUCTION = (
    "no equipped kind-agent entry matches this tag — handle the item in the "
    "main session or report the equipment gap; never launch the Task tool "
    "with an unequipped agent name."
)


def _pool_agent_names(pool: list[dict]) -> frozenset[str]:
    """Exact names of the dispatchable pool entries — the bare-name match set."""
    return frozenset(str(e["name"]) for e in pool if e.get("name"))


def _find_pool_entry(pool: list[dict], name: str) -> dict | None:
    """The dispatchable pool entry named exactly ``name``, or ``None``."""
    for entry in pool:
        if str(entry.get("name")) == name:
            return entry
    return None


def _load_manifest(context_dir: Path) -> list[dict]:
    """Read ``.context/equipment.json`` → its ``items`` list.

    Absent or unparseable → ``[]`` (everything falls back). Accepts a top-level
    list or an object with an ``items`` array.
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

    Skills/hooks/command plugins (``kind != "agent"``) are execution adapters and must
    never win the agent match; a missing ``kind`` counts as ``agent`` (legacy). Prefer
    entries naming a ``subagent_type``, else keep every agent (``fallback`` reports it).
    Marketplace/vendored plugins are also excluded by source, since schema-v3 manifests
    recorded them as ``kind=agent``; this mirrors ``audit/catalog.py``.
    """
    agent_kind = EquipmentKind.AGENT.value
    plugin_sources = {EquipmentSource.MARKETPLACE.value, EquipmentSource.VENDORED.value}
    agents = [
        it
        for it in manifest
        if str(it.get("kind") or agent_kind) == agent_kind
        and str(it.get("source") or "") not in plugin_sources
        # Domain-dimension agents are read-only knowledge holders: never a
        # build-item dispatch target.
        and str(it.get("dimension") or "") != Dimension.DOMAIN.value
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


def _main_session_entry(
    base: dict[str, Any], *, note: str | None, instruction: str
) -> dict[str, Any]:
    """A main-session unit: conductor ``instruction`` + optional ``note``."""
    return {
        **base,
        "dispatch": DispatchMode.MAIN_SESSION.value,
        "agent": None,
        "subagent_type": None,
        "role_path": None,
        "fallback": False,
        "instruction": instruction,
        "upgrade_note": note,
    }


def _pinned_subagent_entry(
    base: dict[str, Any], pool_entry: dict, note: str
) -> dict[str, Any]:
    """A subagent unit pinned to one named pool entry (scoring bypassed).

    The pin is honest about a legacy entry with no ``subagent_type``:
    ``fallback=True`` + the general-purpose render, never a fabricated
    dispatch target.
    """
    sub = pool_entry.get("subagent_type")
    return {
        **base,
        "dispatch": DispatchMode.SUBAGENT.value,
        "agent": str(pool_entry.get("name")),
        "subagent_type": str(sub) if sub else _FALLBACK_AGENT,
        "role_path": pool_entry.get("path") or None,
        "fallback": not sub,
        "instruction": None,
        "upgrade_note": note,
    }


def _entry_for(
    item: ChecklistItem,
    pool: list[dict],
    grounding: tuple[str, ...],
) -> dict[str, Any]:
    """Map one checklist item to its dispatch entry (shared by both verbs).

    GATE items are main-session. An ``agent:<name>`` tag, or a bare name matching a
    typed pool entry, becomes a pinned subagent unit; unknown agent names and untyped
    bare-name matches stay main-session with an ``upgrade_note``; any other tag binds the
    conductor's own tool. Plain items go through capability scoring.
    """
    from dummyindex.context.domains.buildloop import map_task_to_equipment

    agent_names = _pool_agent_names(pool)
    mode = dispatch_mode(item, agent_names)
    base = {
        "index": item.index,
        "task_id": item.item_id,
        "text": item.text,
        "dispatch": mode.value,
        "gate": item.gate,
        "via": item.via,
    }
    if item.gate:
        return _main_session_entry(base, note=None, instruction=_GATE_INSTRUCTION)

    if item.via is not None:
        if item.via.startswith(AGENT_VIA_PREFIX):
            target = item.via[len(AGENT_VIA_PREFIX) :]
            pinned = _find_pool_entry(pool, target)
            if pinned is None:
                # Unknown agent names fail safe — main-session + warning,
                # never a late Task-tool failure on an unequipped name.
                return _main_session_entry(
                    base,
                    note=(
                        f"warning: no kind-agent equipment entry named "
                        f"{target!r} matches '— via agent:{target}' — kept "
                        "main-session"
                    ),
                    instruction=_AGENT_TAG_WARNING_INSTRUCTION,
                )
            return _pinned_subagent_entry(
                base,
                pinned,
                note=(
                    f"explicit '— via agent:{target}' — pinned to equipment "
                    f"agent {target}; capability scoring bypassed"
                ),
            )
        if item.via in agent_names:
            pinned = _find_pool_entry(pool, item.via)
            if pinned is not None and pinned.get("subagent_type"):
                return _pinned_subagent_entry(
                    base,
                    pinned,
                    note=(
                        f"upgraded: bare '— via {item.via}' exactly names "
                        "equipped agent "
                        f"{item.via} — dispatched as a subagent unit "
                        "(capability scoring bypassed)"
                    ),
                )
            # A bare-name match on an untyped legacy record cannot yield a
            # Task target, so the binding-tag semantics hold instead.
            return _main_session_entry(
                base,
                note=(
                    f"matched equipment agent {item.via!r} carries no "
                    "subagent_type (legacy manifest) — kept main-session"
                ),
                instruction=_via_instruction(item.via),
            )
        return _main_session_entry(
            base, note=None, instruction=_via_instruction(item.via)
        )

    choice = map_task_to_equipment(item.text, pool, grounding=grounding)
    selected = _find_pool_entry(pool, choice.equipment_name or "")
    fallback = choice.fallback or not choice.subagent_type
    entry = {
        **base,
        "agent": choice.equipment_name if not choice.fallback else _FALLBACK_AGENT,
        # The Task-tool target. A match without a subagent_type, or no match, falls
        # back to general-purpose and is reported as `fallback`, never as equipped.
        "subagent_type": choice.subagent_type or _FALLBACK_AGENT,
        "role_path": (selected.get("path") or None) if selected else None,
        "fallback": fallback,
        "instruction": None,
        "upgrade_note": None,
    }
    # Missing-capability signal: only when nothing matched (not a matched agent lacking
    # a subagent_type) and the text implies a specialist (security/db/perf/docs/...), so
    # the conductor can run `equip discover <cap>` and vendor a skill on user approval.
    if choice.fallback:
        missing = capabilities_from_text(item.text)
        if missing:
            entry["missing_capability"] = list(missing)
    return entry


def _print_entry(entry: dict[str, Any], *, indent: str) -> None:
    if entry["dispatch"] == DispatchMode.MAIN_SESSION.value:
        print(f"{indent}dispatch: main-session — {entry['instruction']}")
    else:
        tag = " (fallback)" if entry["fallback"] else ""
        print(f"{indent}agent: {entry['agent']}{tag}")
        print(f"{indent}subagent_type: {entry['subagent_type']}")
        if entry.get("role_path"):
            print(f"{indent}role_path: {entry['role_path']}")
    if entry.get("upgrade_note"):
        print(f"{indent}note: {entry['upgrade_note']}")


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
        "close the loop with the installed dummyindex skill's reconcile "
        f"procedure, starting from:\n  {RECONCILE_HINT}"
    )
    return 0


def _resolve_routing_or_report(
    proposal_dir: Path, route_override: dict[str, str] | None
) -> dict[str, str] | None:
    """Effective routing for a proposal, or ``None`` after reporting an error.

    A hand-edited ``proposal.json`` with an invalid routing block fails
    loudly here — at build start, before any wave is dispatched.
    """
    try:
        return resolve_routing(proposal_dir / "proposal.json", route_override)
    except BuildLoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _refuse_live_items(items: tuple[ChecklistItem, ...]) -> bool:
    """Report live-testing/production checklist items; True when any exist."""
    flagged = live_items(items)
    if not flagged:
        return False
    print(
        "error: checklist has live-testing/production items; move them to "
        "closeout pending_verification or add a `<!-- live-ok: reason -->` "
        "marker for a false positive:",
        file=sys.stderr,
    )
    for it in flagged:
        print(f"  #{it.index} {it.text}", file=sys.stderr)
    return True


def do_next(
    items: tuple[ChecklistItem, ...],
    proposal: str,
    proposal_dir: Path,
    context_dir: Path,
    *,
    as_json: bool,
    route_override: dict[str, str] | None = None,
) -> int:
    """Single-item frontier — the serial fallback verb."""
    pending = next((it for it in items if not it.done), None)
    if pending is None:
        return _print_all_done(proposal, "next", as_json=as_json)

    if _refuse_live_items(items):
        return 2

    routing = _resolve_routing_or_report(proposal_dir, route_override)
    if routing is None:
        return 2

    manifest = _load_manifest(context_dir)
    # Repo-level signal, distinct from per-item `fallback`: "equipped" iff equipment.json
    # parsed to >=1 item. Empty or corrupt JSON yields [] and build warns.
    equipped = bool(manifest)
    grounding = _grounding_paths(proposal_dir, context_dir)
    entry = _entry_for(pending, _dispatchable(manifest), grounding)
    from dummyindex.context.domains.buildloop.envelopes import task_binding

    try:
        handoff = task_binding(entry, context_dir, proposal_dir)
    except (OSError, ValueError) as exc:
        print(f"error: invalid task bindings: {exc}", file=sys.stderr)
        return 2

    if as_json:
        payload = {
            "proposal": proposal,
            "item": {
                "index": entry["index"],
                "task_id": entry["task_id"],
                "text": entry["text"],
            },
            "handoff": handoff,
            "agent": entry["agent"],
            "subagent_type": entry["subagent_type"],
            "role_path": entry["role_path"],
            "fallback": entry["fallback"],
            "dispatch": entry["dispatch"],
            "gate": entry["gate"],
            "via": entry["via"],
            "instruction": entry["instruction"],
            "upgrade_note": entry["upgrade_note"],
            "equipped": equipped,
            "grounding": list(grounding),
            "routing": routing,
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
    route_override: dict[str, str] | None = None,
) -> int:
    """Wave frontier: every unchecked item in the earliest incomplete wave,
    each with its own equipment mapping. The grounding set is shared
    wave-wide (it is proposal-level, not per-item)."""
    from dummyindex.context.domains.buildloop import next_wave

    wave = next_wave(items)
    if not wave:
        return _print_all_done(proposal, "next-wave", as_json=as_json)

    if _refuse_live_items(items):
        return 2

    routing = _resolve_routing_or_report(proposal_dir, route_override)
    if routing is None:
        return 2

    manifest = _load_manifest(context_dir)
    equipped = bool(manifest)
    grounding = _grounding_paths(proposal_dir, context_dir)
    pool = _dispatchable(manifest)
    entries = [_entry_for(it, pool, grounding) for it in wave[:8]]
    from dummyindex.context.domains.buildloop.envelopes import task_binding

    try:
        for entry in entries:
            entry["handoff"] = task_binding(entry, context_dir, proposal_dir)
    except (OSError, ValueError) as exc:
        print(f"error: invalid task bindings: {exc}", file=sys.stderr)
        return 2

    payload = {
        "proposal": proposal,
        "group": wave[0].group,  # opaque 0-based id, not the heading's N
        "items": entries,
        "equipped": equipped,
        "grounding": list(grounding),
        "routing": routing,
        "complete": False,
        "group_total": len(wave),
        "truncated": len(entries) < len(wave),
    }
    while len(json.dumps(payload, indent=2).encode("utf-8")) > 65_536:
        if len(entries) <= 1:
            print(
                "error: dispatch exceeds 65536 bytes; shorten bindings and use artifact references",
                file=sys.stderr,
            )
            return 2
        entries.pop()
        payload["truncated"] = True
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    if not equipped:
        print(_NOT_EQUIPPED_WARNING, file=sys.stderr)
    if payload["truncated"]:
        print(
            f"Showing {len(entries)} of {len(wave)} pending items; request the next batch after completing these."
        )
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
