"""`build --next` / `--next-wave` handlers — the dispatch-frontier verbs.

Split out of ``cli/build_loop.py`` (which keeps arg parsing + the
``--check``/``--status`` verbs) to hold the dispatcher under the CLI
file-size guideline. Same wire-only discipline: parse nothing, call the
``buildloop`` domain, print. Both verbs share one JSON schema contract:
every payload carries ``complete`` (bool) and, when work remains, the
equipment mapping per item plus the shared ``grounding`` + ``equipped``
signals. Each item entry also carries ``dispatch`` (``subagent`` |
``main-session``), the structural ``gate``/``via`` markers, a conductor
``instruction`` for main-session items (a GATE is a human decision, never
dispatched; a ``— via <tool>`` tag is a binding directive, never
substituted), and an ``upgrade_note`` — set when the mapper reclassified
a via tag against the agent pool, ``None`` otherwise. Payloads also carry
the resolved model ``routing`` map (proposal data + ``--route``
override; see ``buildloop.routing``). The ``group`` key on
``--next-wave`` is the item's **opaque 0-based group id** from
``parse_checklist`` — not the ``N`` in the ``## Wave N`` heading text.

Only Task-dispatchable equipment entries (kind ``agent``) join the mapping
pool: skills/hooks/command plugins are execution adapters the via-tag
mechanism routes, never ``subagent_type`` targets. Via tags naming agents
fan out instead of serializing: an explicit ``— via agent:<name>`` or a
bare name exactly matching a pool entry upgrades the item to a subagent
unit — pinned to that entry when it carries a ``subagent_type``
(capability scoring bypassed). Unknown agent names and untyped legacy
matches fail safe as main-session items carrying a warning
``upgrade_note``, never a late Task-tool failure.
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
# is the read-only entry that shows what to fold; the installed dummyindex
# skill carries the procedure the session runs from there.
RECONCILE_HINT = "dummyindex context reconcile"

# Printed to stderr (human `--next`/`--next-wave`) when the repo has no usable
# equipment manifest — absent, empty, or unparseable, which all collapse to [].
# This is the *not-equipped* signal — distinct from a per-item fallback on an
# equipped repo (where general-purpose is the correct, silent outcome). Worded
# to not assert absence, since a present-but-corrupt file also lands here.
_NOT_EQUIPPED_WARNING = (
    "⚠ no usable .context/equipment.json. On Claude, run `dummyindex context "
    "equip` (or `/dummyindex-equip`) to create project-tuned agents. Codex "
    "needs no equipment manifest and maps this fallback through its native "
    "subagents. Returning host-neutral general-purpose fallback metadata."
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


def _main_session_entry(
    base: dict[str, Any], *, note: str | None, instruction: str
) -> dict[str, Any]:
    """A main-session unit: conductor ``instruction`` + optional ``note``."""
    return {
        **base,
        "dispatch": DispatchMode.MAIN_SESSION.value,
        "agent": None,
        "subagent_type": None,
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

    ``pool`` is the dispatchable subset of the manifest (see
    ``_dispatchable``). GATE items are always main-session. Via tags are
    three-way: an explicit ``agent:<name>`` or a bare name matching a pool
    entry fans out as a pinned subagent unit; unknown agent names and
    untyped legacy matches degrade to main-session with a warning
    ``upgrade_note``; any other tag binds the conductor's own tool/skill.
    Plain items go through capability scoring.
    """
    from dummyindex.context.domains.buildloop import map_task_to_equipment

    agent_names = _pool_agent_names(pool)
    mode = dispatch_mode(item, agent_names)
    base = {
        "index": item.index,
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
        "upgrade_note": None,
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
    else:
        tag = " (fallback)" if entry["fallback"] else ""
        print(f"{indent}agent: {entry['agent']}{tag}")
        print(f"{indent}subagent_type: {entry['subagent_type']}")
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

    routing = _resolve_routing_or_report(proposal_dir, route_override)
    if routing is None:
        return 2

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

    routing = _resolve_routing_or_report(proposal_dir, route_override)
    if routing is None:
        return 2

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
                    "routing": routing,
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
