"""`dummyindex context equip [--dry-run]` — render a tuned
``.claude/`` toolkit from ``.context/`` + preflight, and record it in
``.context/equipment.json``.

Wire-only: parse args, call the equip domain + preflight inventory, print the
plan/summary, exit. The two writes equip makes into ``.claude/`` are additive
and never-clobber — every target is checked with ``is_safe_to_write`` and a
pre-existing user file is skipped (and reported), never overwritten. A detected
formatter is recorded in the manifest as a ``hook`` item *only*; this MVP never
edits ``.claude/settings.json``.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dummyindex.context.domains.equip import (
    EQUIPMENT_REL,
    IMPLEMENTER_TEMPLATE,
    SCHEMA_VERSION,
    VERIFY_TEMPLATE,
    EquipError,
    EquipmentItem,
    EquipmentManifest,
    EquipmentKind,
    EquipmentSource,
    build_equipment_plan,
    detect_formatter,
    detect_stack,
    is_safe_to_write,
    list_convention_docs,
    write_manifest,
)
from dummyindex.context.domains.preflight import PreflightReport

from ._common import _parse_path_and_root, _resolve_context_root

# Grounding cited by every rendered tool (in addition to the conventions list).
_GROUNDING_BASE: tuple[str, ...] = (".context/HOW_TO_USE.md",)


def _cmd_equip(args: list[str]) -> int:
    rest, dry_run = _pull_equip_flags(args)
    scope, explicit_root, leftover = _parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip`: {leftover}", file=sys.stderr)
        return 2

    project_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"

    from dummyindex.context.domains.preflight import build_preflight_report

    report: PreflightReport = build_preflight_report(project_root)

    stack = detect_stack(context_dir)
    conventions = list_convention_docs(context_dir)
    grounding = _GROUNDING_BASE + conventions
    proj = _project_slug(project_root)

    try:
        plan = build_equipment_plan(
            project_root=project_root,
            context_dir=context_dir,
            stack_label=stack.label,
            conventions=conventions,
            grounding=grounding,
            proj=proj,
        )
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    formatter = detect_formatter(project_root)
    if formatter is not None:
        plan = plan + (_format_hook_item(formatter, grounding),)

    print(f"equip: stack={stack.label} frameworks={list(stack.frameworks)}")
    if dry_run:
        return _print_dry_run(plan, context_dir)

    return _apply(plan, report=report, context_dir=context_dir)


# ----- argument parsing -----------------------------------------------------


def _pull_equip_flags(args: list[str]) -> tuple[list[str], bool]:
    """Strip ``--dry-run`` before ``_parse_path_and_root``."""
    rest: list[str] = []
    dry_run = False
    for a in args:
        if a == "--dry-run":
            dry_run = True
        else:
            rest.append(a)
    return rest, dry_run


# ----- plan construction helpers --------------------------------------------


def _format_hook_item(
    formatter: str, grounding: tuple[str, ...]
) -> tuple[EquipmentItem, None, None]:
    """A record-only PostToolUse format-hook item (never written to disk here)."""
    item = EquipmentItem(
        kind=EquipmentKind.HOOK,
        name=f"{formatter}-format",
        path=".claude/settings.json",
        source=EquipmentSource.GENERATED,
        capabilities=("format",),
        grounded_in=grounding,
    )
    return (item, None, None)


# ----- dry-run + apply ------------------------------------------------------


def _print_dry_run(
    plan: tuple[tuple[EquipmentItem, Path | None, str | None], ...],
    context_dir: Path,
) -> int:
    print("equip plan (--dry-run, nothing written):")
    for item, target, _content in plan:
        if target is None:
            print(f"  record  {item.kind.value:6} {item.name}  ->  manifest only ({item.path})")
        else:
            print(f"  write   {item.kind.value:6} {item.name}  ->  {item.path}")
    print(f"  manifest ->  {context_dir / 'equipment.json'} ({len(plan)} item(s))")
    return 0


def _apply(
    plan: tuple[tuple[EquipmentItem, Path | None, str | None], ...],
    *,
    report: PreflightReport,
    context_dir: Path,
) -> int:
    written: list[EquipmentItem] = []
    skipped: list[EquipmentItem] = []
    for item, target, content in plan:
        if target is None or content is None:
            # Record-only item (the format hook) — manifest entry, no file.
            written.append(item)
            continue
        if not is_safe_to_write(target, report):
            skipped.append(item)
            print(f"  skip    {item.name}  ->  {item.path} (existing user file, not ours)")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(target)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            print(f"error: could not write {item.path}: {exc}", file=sys.stderr)
            return 1
        written.append(item)
        print(f"  write   {item.name}  ->  {item.path}")

    manifest = EquipmentManifest(schema_version=SCHEMA_VERSION, items=tuple(written))
    try:
        path = write_manifest(context_dir, manifest)
    except EquipError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"equip: wrote {len(written)} item(s), skipped {len(skipped)} -> {path}"
    )
    return 0


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
