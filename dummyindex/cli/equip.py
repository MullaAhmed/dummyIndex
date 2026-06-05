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

import json
import sys
from pathlib import Path

from dummyindex.context.claude_settings import MalformedSettingsError
from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    SCHEMA_VERSION,
    CatalogDecision,
    EquipError,
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    EquipVerb,
    ItemState,
    PatchError,
    ResetError,
    apply_patch,
    build_catalog,
    classify_item,
    detect_stack,
    extract_proposal_capabilities,
    is_safe_to_write,
    list_convention_docs,
    read_manifest,
    refresh,
    render_generated_set,
    reset,
    status,
    uninstall,
    wire_hooks,
    write_manifest,
)
from dummyindex.context.domains.preflight import PreflightReport

from ._common import _resolve_context_root

# Grounding cited by every rendered tool (in addition to the conventions list).
_GROUNDING_BASE: tuple[str, ...] = (".context/HOW_TO_USE.md",)
_SETTINGS_REL = ".claude/settings.json"


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


# ----- flag parsing (local; never the shared _parse_path_and_root) ----------


def _pull_flag_value(rest: list[str], name: str) -> tuple[str | None, list[str]]:
    """Strip a single ``--name VALUE`` / ``--name=VALUE`` out of ``rest``.

    Mirrors ``cli.build_loop._pull_flag_value`` — local so we never route equip
    through the shared ``_parse_path_and_root`` (whose ``_FLAGS_TAKING_VALUE``
    table would mis-handle equip's own ``--status``-class flags).
    """
    value: str | None = None
    out: list[str] = []
    i = 0
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    while i < len(rest):
        a = rest[i]
        if a == long_flag and i + 1 < len(rest):
            value = rest[i + 1]
            i += 2
        elif a.startswith(eq_prefix):
            value = a.split("=", 1)[1]
            i += 1
        else:
            out.append(a)
            i += 1
    return value, out


def _pull_bool_flag(rest: list[str], name: str) -> tuple[bool, list[str]]:
    """Strip every ``--name`` occurrence; return (present?, remaining)."""
    flag = f"--{name}"
    present = flag in rest
    return present, [a for a in rest if a != flag]


def _pull_root(rest: list[str]) -> tuple[Path | None, list[str]]:
    value, rest = _pull_flag_value(rest, "root")
    return (Path(value) if value else None), rest


def _resolve_root(rest: list[str]) -> tuple[Path, list[str]]:
    """Pull ``--root`` and a single optional positional path; resolve the root."""
    explicit_root, rest = _pull_root(rest)
    scope = Path(".")
    leftover: list[str] = []
    saw_scope = False
    for a in rest:
        if not a.startswith("--") and not saw_scope:
            scope = Path(a)
            saw_scope = True
        else:
            leftover.append(a)
    return _resolve_context_root(scope, explicit_root=explicit_root), leftover


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
        )
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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

    for item, rel_path, content in rendered:
        target = project_root / rel_path
        prior_item = prior_by_name.get(item.name)
        if prior_item is not None and prior_item.origin_hash is not None:
            # Known generated target: classify against its recorded baseline.
            state = classify_item(project_root, prior_item)
            if state is ItemState.USER_MODIFIED:
                preserved.append(item.name)
                written.append(prior_item)  # carry forward verbatim (skip forever)
                print(f"  keep    {item.name}  ->  {rel_path} (user-modified, preserved)")
                continue
            # MISSING or PRISTINE: (re)write + (re)baseline.
        elif not is_safe_to_write(target, None):
            # Foreign user file we've never recorded — never clobber, never record.
            skipped.append(item.name)
            print(f"  skip    {item.name}  ->  {rel_path} (existing user file, not ours)")
            continue

        if _write_file(target, content) != 0:
            return 1
        written.append(item)
        print(f"  write   {item.name}  ->  {rel_path}")

    # Adopted specialists: manifest records only, never written to disk.
    for adopt in decision.adopt:
        written.append(adopt.to_item())

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
            "hook_events": list(wired_events),
            "manifest": str(path),
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(
        f"equip: wrote {len(written)} item(s), skipped {len(skipped)}, "
        f"preserved {len(preserved)} user-modified -> {path}"
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
            capabilities=("format",),
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


# ----- verb: status ---------------------------------------------------------


def _verb_status(rest: list[str]) -> int:
    as_json, rest = _pull_bool_flag(rest, "json")
    project_root, leftover = _resolve_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip status`: {leftover}", file=sys.stderr)
        return 2
    context_dir = project_root / ".context"
    try:
        manifest = read_manifest(context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = status(project_root, manifest)

    if as_json:
        payload = {
            "items": [
                {"name": name, "state": state.value, "version": version}
                for name, state, version in report.items
            ]
        }
        print(json.dumps(payload, indent=2))
        return 0
    if not report.items:
        print("equip status: no generated items (run `equip` first).")
        return 0
    print("equip status:")
    for name, state, version in report.items:
        ver = version or "-"
        print(f"  {state.value:13} {name}  (v{ver})")
    return 0


# ----- verb: refresh --------------------------------------------------------


def _verb_refresh(rest: list[str]) -> int:
    dry_run, rest = _pull_bool_flag(rest, "dry-run")
    project_root, leftover = _resolve_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip refresh`: {leftover}", file=sys.stderr)
        return 2
    context_dir = project_root / ".context"
    try:
        fresh = _fresh_renders(project_root, context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report = refresh(project_root, fresh_renders=fresh, dry_run=dry_run)
    prefix = "equip refresh (--dry-run)" if dry_run else "equip refresh"
    print(
        f"{prefix}: refreshed {len(report.refreshed)}, "
        f"unchanged {len(report.unchanged)}, "
        f"skipped(user-modified) {len(report.skipped_user_modified)}, "
        f"skipped(missing) {len(report.skipped_missing)}"
    )
    for name in report.refreshed:
        print(f"  {'would refresh' if dry_run else 'refreshed':13} {name}")
    for name in report.skipped_user_modified:
        print(f"  {'skip(user-mod)':13} {name}")
    return 0


# ----- verb: reset ----------------------------------------------------------


def _verb_reset(rest: list[str]) -> int:
    project_root, leftover_root = _pull_root_then_positional(rest)
    name, leftover = leftover_root
    if name is None:
        print("error: `equip reset` requires a NAME", file=sys.stderr)
        return 2
    if leftover:
        print(f"error: unknown argument(s) for `equip reset`: {leftover}", file=sys.stderr)
        return 2
    context_dir = project_root / ".context"
    try:
        manifest = read_manifest(context_dir)
        fresh = _fresh_renders(project_root, context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if name not in fresh:
        print(
            f"error: cannot reset {name!r}: not a generated item in the current catalog",
            file=sys.stderr,
        )
        return 1
    try:
        item = reset(project_root, manifest, name, fresh_render=fresh[name])
    except ResetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"equip reset: {item.name} restored -> {item.path} (v{item.version})")
    return 0


def _pull_root_then_positional(
    rest: list[str],
) -> tuple[Path, tuple[str | None, list[str]]]:
    """Reset takes ``NAME`` as its positional (not a path) + ``--root DIR``."""
    explicit_root, rest = _pull_root(rest)
    name: str | None = None
    leftover: list[str] = []
    for a in rest:
        if not a.startswith("--") and name is None:
            name = a
        else:
            leftover.append(a)
    root = _resolve_context_root(Path("."), explicit_root=explicit_root)
    return root, (name, leftover)


# ----- verb: uninstall ------------------------------------------------------


def _verb_uninstall(rest: list[str]) -> int:
    dry_run, rest = _pull_bool_flag(rest, "dry-run")
    project_root, leftover = _resolve_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip uninstall`: {leftover}", file=sys.stderr)
        return 2
    context_dir = project_root / ".context"
    try:
        manifest = read_manifest(context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = uninstall(project_root, manifest, dry_run=dry_run)
    prefix = "equip uninstall (--dry-run)" if dry_run else "equip uninstall"
    print(
        f"{prefix}: removed {len(report.removed)} file(s), "
        f"kept {len(report.skipped_user_modified)} user-modified, "
        f"removed hook event(s): {list(report.removed_hook_events)}"
    )
    for name in report.skipped_user_modified:
        print(f"  kept    {name} (user-modified)")
    return 0


# ----- verb: patch ----------------------------------------------------------


def _verb_patch(rest: list[str]) -> int:
    item_name, rest = _pull_flag_value(rest, "item")
    from_file, rest = _pull_flag_value(rest, "from-file")
    project_root, leftover = _resolve_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip patch`: {leftover}", file=sys.stderr)
        return 2
    if not item_name:
        print("error: `equip patch` requires --item NAME", file=sys.stderr)
        return 2
    if not from_file:
        print("error: `equip patch` requires --from-file F", file=sys.stderr)
        return 2

    old, new, err = _read_patch_file(Path(from_file))
    if err is not None:
        print(f"error: {err}", file=sys.stderr)
        return 2

    context_dir = project_root / ".context"
    try:
        manifest = read_manifest(context_dir)
        item = apply_patch(
            root=project_root, manifest=manifest, name=item_name, old=old, new=new
        )
    except PatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"equip patch: {item.name} patched -> {item.path} (v{item.version})")
    return 0


def _read_patch_file(path: Path) -> tuple[str, str, str | None]:
    """Parse a patch file: JSON ``{"old": "...", "new": "..."}``.

    Returns ``(old, new, None)`` on success or ``("", "", message)`` on any
    validation failure: missing file, bad JSON, missing keys, or an empty
    ``old`` (an empty ``old`` would match everywhere — never allowed).
    """
    if not path.is_file():
        return "", "", f"patch file not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "", "", f"patch file is not valid JSON: {exc}"
    if not isinstance(data, dict) or "old" not in data or "new" not in data:
        return "", "", "patch file must be a JSON object with 'old' and 'new' keys"
    old, new = data["old"], data["new"]
    if not isinstance(old, str) or not isinstance(new, str):
        return "", "", "patch 'old' and 'new' must both be strings"
    if not old:
        return "", "", "patch 'old' must be non-empty"
    return old, new, None


# ----- shared render path ---------------------------------------------------


def _fresh_renders(project_root: Path, context_dir: Path) -> dict[str, str]:
    """Rebuild the catalog's fresh render for every generated item, by name.

    The same detect → catalog → render path apply uses, so refresh/reset compare
    and restore against exactly what a fresh apply would write today.
    """
    from dummyindex.context.domains.preflight import build_preflight_report

    report = build_preflight_report(project_root)
    profile = detect_stack(context_dir)
    conventions = list_convention_docs(context_dir)
    grounding = _GROUNDING_BASE + conventions
    proj = _project_slug(project_root)
    decision = build_catalog(
        profile=profile, conventions=conventions, preflight=report, proj=proj
    )
    rendered = render_generated_set(
        profile=profile,
        specs=decision.generate,
        conventions=conventions,
        grounding=grounding,
    )
    return {item.name: content for item, _rel, content in rendered}


# ----- helpers --------------------------------------------------------------


def _project_slug(project_root: Path) -> str:
    """A filesystem-safe lowercase slug from the project dir name.

    Used in the verify skill's directory name (``<proj>-verify``). Falls back to
    ``project`` when the dir name has no usable characters.
    """
    raw = project_root.name.lower()
    cleaned = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in raw)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "project"
