"""Lifecycle + evolution verb handlers for ``dummyindex context equip``.

Subcommand-private sibling of ``cli/equip.py``: the dispatcher and the apply
pipeline stay there; the hash-baselined lifecycle verbs (status / refresh /
reset / remove / uninstall) and the patch seam live here. Wire-only — every
handler parses its flags, calls the equip domain, prints, returns an exit code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.equip import (
    EquipError,
    RefreshReport,
    ResetError,
    apply_patch,
    read_manifest,
    refresh,
    remove_item,
    reset,
    status,
    uninstall,
)

from .common import (
    fresh_renders,
    pull_bool_flag,
    pull_flag_value,
    pull_root_then_positional,
    resolve_root,
)


def _print_refresh_report(report: RefreshReport, *, dry_run: bool) -> None:
    """Render an ``equip refresh`` report to stdout (pure CLI-boundary formatting).

    The canary alarm — tools that dropped a load-bearing invariant
    (``INVARIANT_BROKEN``) — is surfaced as a distinct ``⚠`` section. Those tools
    are *kept* (they are user-owned), but listing them only under the benign
    "user-modified" skips would bury the dropped convention, which is the whole
    point of the canary, so they get their own alarm line too.
    """
    prefix = "equip refresh (--dry-run)" if dry_run else "equip refresh"
    print(
        f"{prefix}: refreshed {len(report.refreshed)}, "
        f"unchanged {len(report.unchanged)}, "
        f"skipped(user-modified) {len(report.skipped_user_modified)}, "
        f"skipped(evolved) {len(report.skipped_evolved)}, "
        f"skipped(missing) {len(report.skipped_missing)}"
    )
    for name in report.refreshed:
        print(f"  {'would refresh' if dry_run else 'refreshed':13} {name}")
    for name in report.skipped_user_modified:
        print(f"  {'skip(user-mod)':13} {name}")
    for name in report.skipped_evolved:
        print(f"  {'skip(evolved)':13} {name}")
    if report.alarm_invariant_broken:
        print(
            f"  ⚠ {len(report.alarm_invariant_broken)} tool(s) dropped a "
            "load-bearing invariant (review — INVARIANT_BROKEN):"
        )
        for name in report.alarm_invariant_broken:
            print(f"  ⚠ broken     {name}")


# ----- verb: status ---------------------------------------------------------


def run_status(rest: list[str]) -> int:
    as_json, rest = pull_bool_flag(rest, "json")
    project_root, leftover = resolve_root(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `equip status`: {leftover}",
            file=sys.stderr,
        )
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
            ],
            "missing_playbook": list(report.missing_playbook),
        }
        print(json.dumps(payload, indent=2))
        return 0
    if not report.items:
        print("equip status: no tracked items (run `equip` first).")
        return 0
    print("equip status:")
    for name, state, version in report.items:
        ver = version or "-"
        print(f"  {state.value:13} {name}  (v{ver})")
    for name in report.missing_playbook:
        print(f"  {'incomplete':13} {name}  (no usage playbook)")
    return 0


# ----- verb: refresh --------------------------------------------------------


def run_refresh(rest: list[str]) -> int:
    dry_run, rest = pull_bool_flag(rest, "dry-run")
    project_root, leftover = resolve_root(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `equip refresh`: {leftover}",
            file=sys.stderr,
        )
        return 2
    context_dir = project_root / ".context"
    try:
        fresh = fresh_renders(project_root, context_dir)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    report = refresh(project_root, fresh_renders=fresh, dry_run=dry_run)
    _print_refresh_report(report, dry_run=dry_run)
    return 0


# ----- verb: reset ----------------------------------------------------------


def run_reset(rest: list[str]) -> int:
    project_root, leftover_root = pull_root_then_positional(rest)
    name, leftover = leftover_root
    if name is None:
        print("error: `equip reset` requires a NAME", file=sys.stderr)
        return 2
    if leftover:
        print(
            f"error: unknown argument(s) for `equip reset`: {leftover}", file=sys.stderr
        )
        return 2
    context_dir = project_root / ".context"
    try:
        manifest = read_manifest(context_dir)
        fresh = fresh_renders(project_root, context_dir)
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


# ----- verb: remove -----------------------------------------------------------


def run_remove(rest: list[str]) -> int:
    """``equip remove NAME [--delete-file] [--keep-wiring]`` — drop one entry.

    Surgical, never-destructive by default: adopted entries lose only their
    record; marketplace entries are un-wired from settings (shared marketplaces
    kept; ``--keep-wiring`` skips un-wiring); file-backed generated/vendored
    items refuse unless ``--delete-file`` is passed.
    """
    delete_file, rest = pull_bool_flag(rest, "delete-file")
    keep_wiring, rest = pull_bool_flag(rest, "keep-wiring")
    project_root, leftover_root = pull_root_then_positional(rest)
    name, leftover = leftover_root
    if name is None:
        print("error: `equip remove` requires a NAME", file=sys.stderr)
        return 2
    if leftover:
        print(
            f"error: unknown argument(s) for `equip remove`: {leftover}",
            file=sys.stderr,
        )
        return 2
    context_dir = project_root / ".context"
    try:
        manifest = read_manifest(context_dir)
        report = remove_item(
            project_root,
            manifest,
            name,
            delete_file=delete_file,
            keep_wiring=keep_wiring,
        )
    except EquipError as exc:
        # RemoveError (unknown name / refused file-backed / malformed settings)
        # and a corrupt manifest both map to rc 1, consistent with reset.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    details: list[str] = ["record dropped"]
    if report.deleted_file:
        details.append(f"deleted {report.deleted_file}")
    if report.disabled_plugin:
        details.append("plugin disabled in settings")
    if report.removed_marketplace:
        details.append(f"marketplace {report.removed_marketplace!r} un-wired")
    print(f"equip remove: {report.name} — {', '.join(details)}")
    return 0


# ----- verb: uninstall ------------------------------------------------------


def run_uninstall(rest: list[str]) -> int:
    dry_run, rest = pull_bool_flag(rest, "dry-run")
    project_root, leftover = resolve_root(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `equip uninstall`: {leftover}",
            file=sys.stderr,
        )
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


def run_patch(rest: list[str]) -> int:
    item_name, rest = pull_flag_value(rest, "item")
    from_file, rest = pull_flag_value(rest, "from-file")
    project_root, leftover = resolve_root(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `equip patch`: {leftover}", file=sys.stderr
        )
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
    except EquipError as exc:
        # PatchError (unknown item / `old` not matched once) is a runtime domain
        # failure → exit 1, consistent with reset's ResetError. The `--from-file`
        # *validation* errors above already returned 2 before we got here.
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
