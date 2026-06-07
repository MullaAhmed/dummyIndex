"""`dummyindex context equip <verb>` — the codified, evolving toolkit engine.

Verb surface (spec §9; default verb ``apply`` for back-compat with bare ``equip``):

    equip [apply] [path] [--root DIR] [--dry-run] [--for-proposal S] [--json]
    equip status   [--root DIR] [--json]
    equip refresh  [--root DIR] [--dry-run]
    equip reset NAME [--root DIR]
    equip uninstall [--root DIR] [--dry-run]
    equip patch --item NAME --from-file F [--root DIR]

Wire-only: every handler parses its flags locally, calls the equip domain
(detect → catalog → render | adopt → apply files + settings hooks → manifest v2,
plus the hash-baselined lifecycle and the patch seam), prints, and returns an
exit code (0 / 2 usage / 1 runtime). All policy lives in
``dummyindex/context/domains/equip/``; this module never decides what to build.
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
    list_convention_docs,
    read_manifest,
    render_generated_set,
    set_frontmatter_version,
    wire_hooks,
    write_manifest,
)
from dummyindex.context.domains.preflight import PreflightReport




# ----- dispatch -------------------------------------------------------------


def _cmd_equip(args: list[str]) -> int:
    """Parse the (optional) verb, route to its handler. Default verb: apply."""
    verb, rest = _split_verb(args)
    if verb is EquipVerb.APPLY:
        return _verb_apply(rest)
    if verb is EquipVerb.STATUS:
        return _verb_status(rest)
    if verb is EquipVerb.REFRESH:
        return _verb_refresh(rest)
    if verb is EquipVerb.RESET:
        return _verb_reset(rest)
    if verb is EquipVerb.UNINSTALL:
        return _verb_uninstall(rest)
    if verb is EquipVerb.PATCH:
        return _verb_patch(rest)
    # Unreachable: _split_verb only returns a member or raises via the caller.
    print(f"error: unknown equip verb {verb!r}", file=sys.stderr)  # pragma: no cover
    return 2  # pragma: no cover


def _split_verb(args: list[str]) -> tuple[EquipVerb, list[str]]:
    """Peel a leading verb token off ``args``; default to ``APPLY``.

    The first token is a verb only when it matches an :class:`EquipVerb` member;
    otherwise it is left in place (a path / flag for the default apply verb), so
    bare ``equip``, ``equip <path>`` and ``equip --dry-run`` all route to apply.
    """
    if args:
        try:
            return EquipVerb(args[0]), args[1:]
        except ValueError:
            pass
    return EquipVerb.APPLY, list(args)

from ._equip_common import (
    _GROUNDING_BASE,
    _SETTINGS_REL,
    _fresh_renders,
    _project_slug,
    _pull_bool_flag,
    _pull_flag_value,
    _resolve_root,
)
from ._equip_verbs import (
    _verb_patch,
    _verb_refresh,
    _verb_reset,
    _verb_status,
    _verb_uninstall,
)

# ----- verb: apply ----------------------------------------------------------


def _verb_apply(rest: list[str]) -> int:
    dry_run, rest = _pull_bool_flag(rest, "dry-run")
    as_json, rest = _pull_bool_flag(rest, "json")
    proposal, rest = _pull_flag_value(rest, "for-proposal")
    project_root, leftover = _resolve_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip`: {leftover}", file=sys.stderr)
        return 2

    context_dir = project_root / ".context"

    proposal_caps: tuple[str, ...] = ()
    if proposal is not None:
        proposal_dir = context_dir / "proposals" / proposal
        if not (proposal_dir / "plan.md").is_file() and not (
            proposal_dir / "checklist.md"
        ).is_file():
            print(
                f"error: no proposal {proposal!r} under {context_dir / 'proposals'} "
                "(expected plan.md / checklist.md)",
                file=sys.stderr,
            )
            return 2
        proposal_caps = extract_proposal_capabilities(proposal_dir)

    from dummyindex.context.domains.preflight import build_preflight_report

    report: PreflightReport = build_preflight_report(project_root)
    profile = detect_stack(context_dir)
    conventions = list_convention_docs(context_dir)
    grounding = _GROUNDING_BASE + conventions
    proj = _project_slug(project_root)

    try:
        decision = build_catalog(
            profile=profile,
            conventions=conventions,
            preflight=report,
            proj=proj,
            proposal_capabilities=proposal_caps,
        )
        rendered = render_generated_set(
            profile=profile,
            specs=decision.generate,
            conventions=conventions,
            grounding=grounding,
            proj=proj,
        )
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not as_json:
        print(f"equip: stack={profile.label} frameworks={list(profile.frameworks)}")
    if dry_run:
        return _apply_dry_run(rendered, decision, context_dir, as_json=as_json)
    return _apply_write(
        rendered,
        decision,
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
            "adopt": [{"name": a.name, "subagent_type": a.subagent_type} for a in decision.adopt],
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
    project_root: Path,
    context_dir: Path,
    as_json: bool,
) -> int:
    """Write generated files (USER_MODIFIED-safe), wire hooks, record manifest v2."""
    try:
        prior = read_manifest(context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prior_by_name = {i.name: i for i in prior.items}

    written: list[EquipmentItem] = []
    skipped: list[str] = []
    preserved: list[str] = []
    evolved: list[str] = []

    for item, rel_path, content in rendered:
        target = project_root / rel_path
        prior_item = prior_by_name.get(item.name)
        if prior_item is not None and prior_item.origin_hash is not None:
            # Known generated target: classify against its recorded baseline.
            state = classify_item(project_root, prior_item)
            if state is ItemState.USER_MODIFIED:
                preserved.append(item.name)
                written.append(prior_item)  # carry forward verbatim (skip forever)
                if not as_json:
                    print(f"  keep    {item.name}  ->  {rel_path} (user-modified, preserved)")
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
                print(f"  skip    {item.name}  ->  {rel_path} (existing user file, not ours)")
            continue

        if _write_file(target, content) != 0:
            return 1
        written.append(item)
        if not as_json:
            print(f"  write   {item.name}  ->  {rel_path}")

    # Adopted specialists: manifest records only, never written to disk.
    for adopt in decision.adopt:
        written.append(adopt_spec_to_item(adopt))

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

    manifest = EquipmentManifest(schema_version=SCHEMA_VERSION, items=tuple(written))
    try:
        path = write_manifest(context_dir, manifest)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if as_json:
        payload = {
            "written": [i.name for i in written],
            "skipped": skipped,
            "preserved_user_modified": preserved,
            "kept_evolved": evolved,
            "hook_events": list(wired_events),
            "manifest": str(path),
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(
        f"equip: wrote {len(written)} item(s), skipped {len(skipped)}, "
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


def _hook_items(decision: CatalogDecision, *, grounding: tuple[str, ...]) -> list[EquipmentItem]:
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
