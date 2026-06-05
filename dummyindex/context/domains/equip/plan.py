"""Build the equip plan: render toolkit items into ``(item, target, content)`` triples.

The CLI boundary wires this together; domain logic lives here so it is
testable in isolation without parsing args.
"""
from __future__ import annotations

from pathlib import Path

from .enums import EquipmentKind, EquipmentSource
from .models import EquipmentItem
from .render import IMPLEMENTER_TEMPLATE, VERIFY_TEMPLATE, render_template


def build_equipment_plan(
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
        kind=EquipmentKind.AGENT,
        name=f"{stack_label}-implementer",
        path=agent_rel,
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        grounded_in=grounding,
    )
    skill_item = EquipmentItem(
        kind=EquipmentKind.SKILL,
        name=f"{proj}-verify",
        path=skill_rel,
        source=EquipmentSource.GENERATED,
        capabilities=("test", "verify"),
        grounded_in=grounding,
    )
    return (
        (agent_item, project_root / agent_rel, agent_body),
        (skill_item, project_root / skill_rel, skill_body),
    )
