"""`dummyindex context equip <verb>` — the codified, evolving toolkit engine.

Verb surface (spec §9). ``apply`` is an EXPLICIT verb — a bare ``equip`` (a
help/discovery probe) no longer applies; it prints usage and exits 2 so a probe
never mutates the repo. The sole verbless carve-out is the read-only
``equip --dry-run`` preview (writes nothing). The schema version equip records
is :data:`dummyindex.context.domains.equip.SCHEMA_VERSION` (currently v4):

    equip apply [path] [--root DIR] [--dry-run] [--for-proposal S] [--specialist C] [--json]
    equip add-specialist CAPABILITY [--root DIR] [--dry-run] [--json]
    equip discover ["query"] [--repo OWNER/NAME] [--root DIR] [--json]
    equip install <plugin>@<marketplace> [--yes] [--scope project|local|user] [--root DIR]
    equip status   [--root DIR] [--json]
    equip refresh  [--root DIR] [--dry-run]
    equip reset NAME [--root DIR]
    equip remove NAME [--root DIR] [--delete-file] [--keep-wiring]
    equip uninstall [--root DIR] [--dry-run]
    equip patch --item NAME --from-file F [--root DIR]
    equip verify <plugin>@<marketplace>

Wire-only: every handler parses its flags locally, calls the equip domain
(detect → catalog → render | adopt → apply files + settings hooks → manifest,
plus the hash-baselined lifecycle and the patch seam), prints, and returns an
exit code (0 / 2 usage / 1 runtime). All policy lives in
``dummyindex/context/domains/equip/``; this module never decides what to build.
The manifest write MERGES with the prior manifest — records this run does not
re-derive (marketplace/vendored/adopted/stale-generated) carry forward
verbatim, never silently dropped.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from dummyindex.context.claude_settings import MalformedSettingsError
from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    SCHEMA_VERSION,
    Capability,
    CatalogDecision,
    EquipError,
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    EquipVerb,
    ItemState,
    adopt_spec_to_item,
    build_catalog,
    classify_item,
    content_hash,
    detect_stack,
    extract_proposal_capabilities,
    is_evolved,
    is_safe_to_write,
    is_user_owned,
    list_convention_docs,
    profile_has_frontend,
    read_manifest,
    render_generated_set,
    set_frontmatter_version,
    templated_capabilities,
    wire_hooks,
    write_manifest,
)
from dummyindex.context.domains.preflight import PreflightReport

from .common import (
    _GROUNDING_BASE,
    _SETTINGS_REL,
    drop_generated_stems,
    filter_grounding_docs,
    project_slug,
    pull_bool_flag,
    pull_flag_value,
    pull_root_then_positional,
    resolve_root,
    specialist_caps_from_manifest,
)
from .discover import run_discover
from .install import run_install
from .plugin_state import run_verify
from .verbs import (
    run_patch,
    run_refresh,
    run_remove,
    run_reset,
    run_status,
    run_uninstall,
)

# ----- dispatch -------------------------------------------------------------


def run(args: list[str]) -> int:
    """Parse the verb, route to its handler. ``apply`` is now EXPLICIT.

    A verbless invocation no longer silently applies (a help/discovery probe
    must never mutate the repo). The one carve-out is the read-only
    ``--dry-run`` plan, which writes nothing — that keeps working verbless.
    """
    verb, rest = _split_verb(args)
    if verb is None:
        # No verb and not the read-only --dry-run carve-out: refuse to apply.
        if "--dry-run" in rest:
            return run_apply(rest)
        print(_VERB_REQUIRED_MESSAGE, file=sys.stderr)
        return 2
    if verb is EquipVerb.APPLY:
        return run_apply(rest)
    if verb is EquipVerb.ADD_SPECIALIST:
        return run_add_specialist(rest)
    if verb is EquipVerb.STATUS:
        return run_status(rest)
    if verb is EquipVerb.REFRESH:
        return run_refresh(rest)
    if verb is EquipVerb.RESET:
        return run_reset(rest)
    if verb is EquipVerb.REMOVE:
        return run_remove(rest)
    if verb is EquipVerb.UNINSTALL:
        return run_uninstall(rest)
    if verb is EquipVerb.PATCH:
        return run_patch(rest)
    if verb is EquipVerb.DISCOVER:
        return run_discover(rest)
    if verb is EquipVerb.INSTALL:
        return run_install(rest)
    if verb is EquipVerb.VERIFY:
        return run_verify(rest)
    # Unreachable: _split_verb only returns a member or raises via the caller.
    print(f"error: unknown equip verb {verb!r}", file=sys.stderr)  # pragma: no cover
    return 2  # pragma: no cover


_VERB_REQUIRED_MESSAGE = (
    "error: `equip` requires an explicit verb; did you mean `equip apply`?\n"
    "  verbs: apply | add-specialist | status | refresh | reset | remove | "
    "uninstall | patch | discover | install | verify\n"
    "  (verbless `equip --dry-run` still previews; run "
    "`dummyindex context equip --help` for usage)"
)


def _split_verb(args: list[str]) -> tuple[EquipVerb | None, list[str]]:
    """Peel a leading verb token off ``args``.

    The first token is a verb only when it matches an :class:`EquipVerb` member.
    Returns ``None`` for the verb when there is no leading verb (bare ``equip``,
    ``equip <path>``, ``equip --dry-run`` …) — apply is no longer the silent
    default, because a help/discovery probe must never mutate the repo. The
    caller decides what to do with the verbless case (refuse, or honour the
    read-only ``--dry-run`` carve-out).
    """
    if args:
        try:
            return EquipVerb(args[0]), args[1:]
        except ValueError:
            pass
    return None, list(args)


# ----- verb: apply ----------------------------------------------------------


def run_apply(rest: list[str]) -> int:
    dry_run, rest = pull_bool_flag(rest, "dry-run")
    as_json, rest = pull_bool_flag(rest, "json")
    proposal, rest = pull_flag_value(rest, "for-proposal")
    specialist, rest = pull_flag_value(rest, "specialist")
    project_root, leftover = resolve_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip`: {leftover}", file=sys.stderr)
        return 2

    explicit_specialists: tuple[str, ...] = ()
    if specialist is not None:
        if specialist not in templated_capabilities():
            print(_unknown_specialist_message(specialist), file=sys.stderr)
            return 2
        explicit_specialists = (specialist,)

    return _run_apply(
        project_root,
        dry_run=dry_run,
        as_json=as_json,
        proposal=proposal,
        explicit_specialists=explicit_specialists,
    )


def run_add_specialist(rest: list[str]) -> int:
    """``equip add-specialist CAPABILITY`` — generate one grounded specialist.

    Sugar over ``apply --specialist CAPABILITY``: it renders (and lifecycle-tracks)
    a first-class specialist file for ``CAPABILITY``, on top of the existing
    toolkit, leaving every already-applied tool untouched (never-clobber).
    """
    dry_run, rest = pull_bool_flag(rest, "dry-run")
    as_json, rest = pull_bool_flag(rest, "json")
    project_root, (capability, leftover) = pull_root_then_positional(rest)
    if capability is None:
        print(
            "error: `equip add-specialist` requires a CAPABILITY "
            f"({_specialist_list()})",
            file=sys.stderr,
        )
        return 2
    if leftover:
        print(
            f"error: unknown argument(s) for `equip add-specialist`: {leftover}",
            file=sys.stderr,
        )
        return 2
    if capability not in templated_capabilities():
        print(_unknown_specialist_message(capability), file=sys.stderr)
        return 2
    return _run_apply(
        project_root,
        dry_run=dry_run,
        as_json=as_json,
        proposal=None,
        explicit_specialists=(capability,),
    )


def _specialist_list() -> str:
    return ", ".join(sorted(templated_capabilities()))


def _unknown_specialist_message(capability: str) -> str:
    return (
        f"error: no generated-specialist template for {capability!r}. "
        f"Available: {_specialist_list()}. "
        "A capability with no template is still covered by manifest-only adoption "
        "(a project or registry agent) on a `--for-proposal` run."
    )


def _run_apply(
    project_root: Path,
    *,
    dry_run: bool,
    as_json: bool,
    proposal: str | None,
    explicit_specialists: tuple[str, ...],
) -> int:
    """Shared apply pipeline for ``apply`` and ``add-specialist``."""
    context_dir = project_root / ".context"

    # equip renders FROM the .context spine. Writing into an un-indexed repo
    # would half-initialise it (an equipment.json conjured from nothing) — refuse
    # the write and point at ingest. A read-only --dry-run preview is harmless,
    # so it is allowed to proceed (it writes nothing regardless).
    if not dry_run and not context_dir.is_dir():
        print(
            f"error: {context_dir} not found — equip renders from the .context "
            "spine. Run `dummyindex ingest` first, then `equip apply`.",
            file=sys.stderr,
        )
        return 1

    proposal_caps: tuple[str, ...] = ()
    if proposal is not None:
        proposal_dir = context_dir / "proposals" / proposal
        if (
            not (proposal_dir / "plan.md").is_file()
            and not (proposal_dir / "checklist.md").is_file()
        ):
            print(
                f"error: no proposal {proposal!r} under {context_dir / 'proposals'} "
                "(expected plan.md / checklist.md)",
                file=sys.stderr,
            )
            return 2
        proposal_caps = extract_proposal_capabilities(proposal_dir)

    from dummyindex.context.domains.preflight import build_preflight_report

    try:
        prior = read_manifest(context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report: PreflightReport = build_preflight_report(project_root)
    # Equip's own generated/vendored agents must never look like user-authored
    # project agents — re-adopting one would plant a second, conflicting record.
    report = dataclasses.replace(
        report,
        project_agents=drop_generated_stems(project_root, prior, report.project_agents),
    )
    profile = detect_stack(context_dir)
    conventions = list_convention_docs(context_dir)
    grounding = _GROUNDING_BASE + conventions
    proj = project_slug(project_root)

    # Carry forward already-applied specialists so a plain re-apply never drops
    # one; an explicit `--specialist` ask is added on top (deduped, order-stable).
    forced = tuple(
        dict.fromkeys(explicit_specialists + specialist_caps_from_manifest(prior))
    )

    try:
        decision = build_catalog(
            profile=profile,
            conventions=conventions,
            preflight=report,
            proj=proj,
            proposal_capabilities=proposal_caps,
            forced_specialist_capabilities=forced,
        )
        rendered = render_generated_set(
            profile=profile,
            specs=filter_grounding_docs(project_root, decision.generate),
            conventions=conventions,
            grounding=grounding,
            proj=proj,
        )
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not as_json:
        print(f"equip: stack={profile.label} frameworks={list(profile.frameworks)}")
        if (
            Capability.FRONTEND in proposal_caps
            and not profile_has_frontend(profile)
            and not any(Capability.FRONTEND in a.capabilities for a in decision.adopt)
        ):
            # Make the stack-consistency skip visible (audit C7): the plan text
            # asked for frontend, but the repo shows no frontend evidence.
            print(
                "note: proposal mentions frontend work but the stack shows no "
                "frontend — skipped the Frontend Developer adoption (the "
                "generic implementer covers it)"
            )
    if dry_run:
        return _apply_dry_run(rendered, decision, context_dir, as_json=as_json)
    return _apply_write(
        rendered,
        decision,
        prior=prior,
        project_root=project_root,
        context_dir=context_dir,
        as_json=as_json,
    )


def _apply_dry_run(
    rendered: tuple[tuple[EquipmentItem, str, str], ...],
    decision: CatalogDecision,
    context_dir: Path,
    *,
    as_json: bool,
) -> int:
    """Print the plan; write nothing — no files, no settings, no manifest."""
    if as_json:
        payload = {
            "dry_run": True,
            "generate": [{"name": i.name, "path": p} for i, p, _ in rendered],
            "adopt": [
                {"name": a.name, "subagent_type": a.subagent_type}
                for a in decision.adopt
            ],
            "hooks": [{"name": h.name, "event": h.event} for h in decision.hooks],
        }
        print(json.dumps(payload, indent=2))
        return 0
    print("equip plan (--dry-run, nothing written):")
    for item, rel_path, _content in rendered:
        print(f"  write   {item.kind.value:6} {item.name}  ->  {rel_path}")
    for adopt in decision.adopt:
        where = adopt.path or "(registry specialist)"
        print(f"  adopt   agent  {adopt.name}  ->  {where}")
    for hook in decision.hooks:
        print(f"  hook    {hook.name}  ->  {_SETTINGS_REL} ({hook.event})")
    print(f"  manifest ->  {context_dir / EQUIPMENT_REL}")
    return 0


def _apply_write(
    rendered: tuple[tuple[EquipmentItem, str, str], ...],
    decision: CatalogDecision,
    *,
    prior: EquipmentManifest,
    project_root: Path,
    context_dir: Path,
    as_json: bool,
) -> int:
    """Write generated files (USER_MODIFIED-safe), wire hooks, MERGE the manifest.

    ``prior`` is the manifest read once by the caller (so the specialist-carry-
    forward decision and the never-clobber baselines come from the same read).

    The manifest write is a merge, never a rebuild (never-silently-drop): any
    prior record this run does not re-derive — marketplace plugins, vendored
    files, adopted specialists, even a generated record under a stale name —
    is carried forward verbatim. A re-derived adoption or hook record replaces
    its prior same-name record exactly once.
    """
    prior_by_name = {i.name: i for i in prior.items}

    written: list[EquipmentItem] = []
    files_written: list[str] = []
    skipped: list[str] = []
    preserved: list[str] = []
    evolved: list[str] = []

    for item, rel_path, content in rendered:
        target = project_root / rel_path
        prior_item = prior_by_name.get(item.name)
        if prior_item is not None and prior_item.origin_hash is not None:
            # Known generated target: classify against its recorded baseline.
            state = classify_item(project_root, prior_item)
            # User-owned (USER_MODIFIED / CUSTOMIZED / INVARIANT_BROKEN): carry
            # the prior record forward verbatim — never rewrite, never re-baseline
            # (so an INVARIANT_BROKEN alarm is not laundered to PRISTINE here).
            if is_user_owned(state):
                preserved.append(item.name)
                written.append(prior_item)  # carry forward verbatim (skip forever)
                if not as_json:
                    print(
                        f"  keep    {item.name}  ->  {rel_path} "
                        f"({state.value}, preserved)"
                    )
                continue
            if state is ItemState.PRISTINE and is_evolved(prior_item):
                # Sanctioned patch-evolution: content intentionally differs
                # from a fresh render — regenerating would wipe the patches.
                evolved.append(item.name)
                written.append(prior_item)
                if not as_json:
                    print(
                        f"  keep    {item.name}  ->  {rel_path} "
                        f"(evolved v{prior_item.version}, kept)"
                    )
                continue
            # MISSING or PRISTINE(non-evolved): (re)write + (re)baseline,
            # carrying any prior refresh-bumped version forward (the manifest
            # is the version source of truth; the frontmatter mirrors it).
            if prior_item.version and prior_item.version != item.version:
                content = set_frontmatter_version(content, prior_item.version)
                item = dataclasses.replace(
                    item,
                    version=prior_item.version,
                    origin_hash=content_hash(content),
                )
        elif not is_safe_to_write(target):
            # Foreign user file we've never recorded — never clobber, never record.
            skipped.append(item.name)
            if not as_json:
                print(
                    f"  skip    {item.name}  ->  {rel_path} (existing user file, not ours)"
                )
            continue

        if _write_file(target, content) != 0:
            return 1
        written.append(item)
        files_written.append(item.name)
        if not as_json:
            print(f"  write   {item.name}  ->  {rel_path}")

    # Adopted specialists: manifest records only, never written to disk.
    # Dedupe by name against this run's rendered set — a generated item and a
    # re-derived adoption of the same name must never coexist (the generated
    # record wins; the duplicate-frontend-reviewer defect).
    seen = {i.name for i in written}
    adopted: list[str] = []
    for adopt in decision.adopt:
        if adopt.name in seen:
            if not as_json:
                print(
                    f"  skip    {adopt.name}  (already recorded this run; "
                    "adoption not duplicated)"
                )
            continue
        written.append(adopt_spec_to_item(adopt))
        seen.add(adopt.name)
        adopted.append(adopt.name)
        if not as_json:
            where = (
                adopt.path or "(registry specialist; manifest-only, no file written)"
            )
            print(f"  adopt   agent  {adopt.name}  ->  {where}")

    # Settings hooks: write after files so malformed settings never blocks them.
    wired_events: tuple[str, ...] = ()
    if decision.hooks:
        try:
            wired_events = wire_hooks(project_root / _SETTINGS_REL, decision.hooks)
        except MalformedSettingsError as exc:
            print(
                f"warning: settings.json hook skipped ({exc}); files still written",
                file=sys.stderr,
            )
        else:
            written.extend(_hook_items(decision, grounding=_hook_grounding(written)))

    # Merge: carry forward every prior record this run did not re-derive —
    # marketplace/vendored/installed entries and stale-named generated records
    # alike. This run's records (rendered, adopted, hooks) win name collisions.
    seen = {i.name for i in written}
    carried: list[str] = []
    for prior_item in prior.items:
        if prior_item.name in seen:
            continue
        written.append(prior_item)
        seen.add(prior_item.name)
        carried.append(prior_item.name)
        if not as_json:
            if prior_item.source is EquipmentSource.GENERATED:
                print(
                    f"  keep    {prior_item.name}  "
                    "(generated record not re-rendered this run — carried forward)"
                )
            else:
                print(
                    f"  keep    {prior_item.name}  "
                    f"({prior_item.source.value} record carried forward)"
                )

    manifest = EquipmentManifest(schema_version=SCHEMA_VERSION, items=tuple(written))
    try:
        path = write_manifest(context_dir, manifest)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if as_json:
        payload = {
            "written": files_written,
            "adopted": adopted,
            "carried_forward": carried,
            "skipped": skipped,
            "preserved_user_modified": preserved,
            "kept_evolved": evolved,
            "hook_events": list(wired_events),
            "manifest": str(path),
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(
        f"equip: wrote {len(files_written)} file(s), "
        f"adopted {len(adopted)} (manifest-only), "
        f"wired {len(wired_events)} hook event(s), "
        f"kept {len(carried)} prior record(s), skipped {len(skipped)}, "
        f"preserved {len(preserved)} user-modified, "
        f"kept {len(evolved)} evolved -> {path}"
    )
    return 0


def _hook_grounding(written: list[EquipmentItem]) -> tuple[str, ...]:
    """Reuse a generated item's grounding for the hook record, or the base."""
    for item in written:
        if item.grounded_in:
            return item.grounded_in
    return _GROUNDING_BASE


def _hook_items(
    decision: CatalogDecision, *, grounding: tuple[str, ...]
) -> list[EquipmentItem]:
    """One record-only manifest item per wired hook (no file backing)."""
    return [
        EquipmentItem(
            kind=EquipmentKind.HOOK,
            name=hook.name,
            path=_SETTINGS_REL,
            source=EquipmentSource.GENERATED,
            capabilities=(Capability.FORMAT,),
            grounded_in=grounding,
        )
        for hook in decision.hooks
    ]


def _write_file(target: Path, content: str) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        print(f"error: could not write {target}: {exc}", file=sys.stderr)
        return 1
    return 0
