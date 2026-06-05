"""`dummyindex context equip [--for-proposal S] [--dry-run]` — render a tuned
``.claude/`` toolkit from ``.context/`` + preflight, and record it in
``.context/equipment.json``.

Wire-only: parse args, call the equip domain + preflight inventory, print the
plan/summary, exit. The two writes equip makes into ``.claude/`` are additive
and never-clobber — every target is checked with ``is_safe_to_write`` and a
pre-existing user file is skipped (and reported), never overwritten. A detected
formatter is recorded in the manifest as a ``hook`` item *only*; this MVP never
edits ``.claude/settings.json`` (see INTEGRATION.md for the settings entry).
"""
from __future__ import annotations

import sys
from pathlib import Path

from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    EquipError,
    EquipmentItem,
    EquipmentManifest,
    detect_formatter,
    detect_stack,
    is_safe_to_write,
    list_convention_docs,
    render_template,
    write_manifest,
)
from dummyindex.context.domains.equip.render import (
    IMPLEMENTER_TEMPLATE,
    VERIFY_TEMPLATE,
)

from ._common import _parse_path_and_root, _resolve_context_root

# Grounding cited by every rendered tool (in addition to the conventions list).
_GROUNDING_BASE: tuple[str, ...] = (".context/HOW_TO_USE.md",)


def _cmd_equip(args: list[str]) -> int:
    rest, dry_run, _proposal = _pull_equip_flags(args)
    scope, explicit_root, leftover = _parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s) for `equip`: {leftover}", file=sys.stderr)
        return 2

    project_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"

    from dummyindex.context.domains.preflight import build_preflight_report

    report = build_preflight_report(project_root)

    stack = detect_stack(context_dir)
    conventions = list_convention_docs(context_dir)
    grounding = _GROUNDING_BASE + conventions
    proj = _project_slug(project_root)

    try:
        plan = _build_plan(
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


def _pull_equip_flags(args: list[str]) -> tuple[list[str], bool, str | None]:
    """Strip ``--dry-run`` and ``--for-proposal S`` before ``_parse_path_and_root``.

    ``--for-proposal`` isn't in ``_common._FLAGS_TAKING_VALUE``, so its value
    would otherwise be mis-captured as the positional scope. We consume both the
    flag and its value here. ``--for-proposal`` is accepted (it names the
    proposal this toolkit is for) but unused in this thin MVP — the rendered set
    is the same regardless.
    """
    rest: list[str] = []
    dry_run = False
    proposal: str | None = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dry-run":
            dry_run = True
            i += 1
        elif a == "--for-proposal" and i + 1 < len(args):
            proposal = args[i + 1]
            i += 2
        elif a.startswith("--for-proposal="):
            proposal = a.split("=", 1)[1]
            i += 1
        else:
            rest.append(a)
            i += 1
    return rest, dry_run, proposal


# ----- plan construction ----------------------------------------------------


def _build_plan(
    *,
    project_root: Path,
    context_dir: Path,
    stack_label: str,
    conventions: tuple[str, ...],
    grounding: tuple[str, ...],
    proj: str,
) -> tuple[tuple[EquipmentItem, Path, str], ...]:
    """Render the toolkit into ``(item, target_path, content)`` triples.

    Two rendered tools: a stack implementer agent and a per-project verify
    skill. The format hook (if any) is appended by the caller as a record-only
    item with no content to write.
    """
    agent_rel = f".claude/agents/{stack_label}-implementer.md"
    skill_rel = f".claude/skills/{proj}-verify/SKILL.md"

    agent_body = render_template(
        IMPLEMENTER_TEMPLATE, stack=stack_label, conventions=conventions
    )
    skill_body = render_template(
        VERIFY_TEMPLATE, stack=stack_label, conventions=conventions
    )

    agent_item = EquipmentItem(
        kind="agent",
        name=f"{stack_label}-implementer",
        path=agent_rel,
        source="generated",
        capabilities=("implement",),
        grounded_in=grounding,
    )
    skill_item = EquipmentItem(
        kind="skill",
        name=f"{proj}-verify",
        path=skill_rel,
        source="generated",
        capabilities=("test", "verify"),
        grounded_in=grounding,
    )
    return (
        (agent_item, project_root / agent_rel, agent_body),
        (skill_item, project_root / skill_rel, skill_body),
    )


def _format_hook_item(
    formatter: str, grounding: tuple[str, ...]
) -> tuple[EquipmentItem, None, None]:
    """A record-only PostToolUse format-hook item (never written to disk here)."""
    item = EquipmentItem(
        kind="hook",
        name=f"{formatter}-format",
        path=".claude/settings.json",
        source="generated",
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
            print(f"  record  {item.kind:6} {item.name}  ->  manifest only ({item.path})")
        else:
            print(f"  write   {item.kind:6} {item.name}  ->  {item.path}")
    print(f"  manifest ->  {context_dir / 'equipment.json'} ({len(plan)} item(s))")
    return 0


def _apply(
    plan: tuple[tuple[EquipmentItem, Path | None, str | None], ...],
    *,
    report,
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
