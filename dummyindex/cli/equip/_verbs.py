"""Lifecycle + evolution verb handlers for ``dummyindex context equip``.

Subcommand-private sibling of ``cli/equip.py``: the dispatcher and the apply
pipeline stay there; the hash-baselined lifecycle verbs (status / refresh /
reset / uninstall) and the patch seam live here. Wire-only — every handler
parses its flags, calls the equip domain, prints, returns an exit code.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.equip import (
    EquipError,
    ResetError,
    apply_patch,
    read_manifest,
    refresh,
    reset,
    status,
    uninstall,
)

from ._common import (
    _fresh_renders,
    _pull_bool_flag,
    _pull_flag_value,
    _pull_root_then_positional,
    _resolve_root,
)


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
        f"skipped(evolved) {len(report.skipped_evolved)}, "
        f"skipped(missing) {len(report.skipped_missing)}"
    )
    for name in report.refreshed:
        print(f"  {'would refresh' if dry_run else 'refreshed':13} {name}")
    for name in report.skipped_user_modified:
        print(f"  {'skip(user-mod)':13} {name}")
    for name in report.skipped_evolved:
        print(f"  {'skip(evolved)':13} {name}")
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
