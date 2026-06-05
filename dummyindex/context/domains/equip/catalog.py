"""The policy core: decide what equip generates, adopts, and wires.

:func:`build_catalog` is a pure function over a :class:`StackProfile`, the repo's
convention docs, a :class:`PreflightReport`, and (optionally) the capabilities a
proposal demands. It returns a :class:`CatalogDecision` — no I/O, fully
unit-testable. The CLI boundary (Phase 2) renders + writes from this decision.

Policy (spec §3 + §6):

- **Generate** (always): ``{label}-implementer`` + ``{label}-tester`` agents, a
  ``{proj}-reviewer`` agent, and a ``{proj}-verify`` skill.
- **Hooks**: a PostToolUse format hook iff ``profile.format_command`` was
  detected (binary-guarded by the formatter name; spec §5).
- **Adopt**: project/registry specialists covering the proposal capabilities,
  *before* any generic fallback (adopt-before-generate). A capability no source
  covers is left to the generic implementer — never a speculative template.
"""
from __future__ import annotations

from dummyindex.context.domains.preflight.models import PreflightReport

from ._constants import EQUIP_SENTINEL
from .adopt import adopt_existing
from .enums import EquipmentKind
from .models import CatalogDecision, GenerateSpec, HookSpec, StackProfile
from .render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
)

_AGENTS_DIR = ".claude/agents"
_SKILLS_DIR = ".claude/skills"
_FORMAT_EVENT = "PostToolUse"
_FORMAT_MATCHER = "Write|Edit"


def build_catalog(
    *,
    profile: StackProfile,
    conventions: tuple[str, ...],
    preflight: PreflightReport,
    proj: str,
    proposal_capabilities: tuple[str, ...] = (),
) -> CatalogDecision:
    """Decide the full equip toolkit for this repo. Pure; no I/O."""
    generate = _standard_generated_set(profile.label, proj)
    adopt = adopt_existing(preflight=preflight, needed=proposal_capabilities)
    hooks = _format_hooks(profile)
    return CatalogDecision(generate=generate, adopt=adopt, hooks=hooks)


def _standard_generated_set(label: str, proj: str) -> tuple[GenerateSpec, ...]:
    return (
        GenerateSpec(
            name=f"{label}-implementer",
            kind=EquipmentKind.AGENT,
            template=IMPLEMENTER_TEMPLATE,
            capabilities=("implement",),
            rel_path=f"{_AGENTS_DIR}/{label}-implementer.md",
        ),
        GenerateSpec(
            name=f"{label}-tester",
            kind=EquipmentKind.AGENT,
            template=TESTER_TEMPLATE,
            capabilities=("test",),
            rel_path=f"{_AGENTS_DIR}/{label}-tester.md",
        ),
        GenerateSpec(
            name=f"{proj}-reviewer",
            kind=EquipmentKind.AGENT,
            template=REVIEWER_TEMPLATE,
            capabilities=("review",),
            rel_path=f"{_AGENTS_DIR}/{proj}-reviewer.md",
        ),
        GenerateSpec(
            name=f"{proj}-verify",
            kind=EquipmentKind.SKILL,
            template=VERIFY_TEMPLATE,
            capabilities=("test", "verify"),
            rel_path=f"{_SKILLS_DIR}/{proj}-verify/SKILL.md",
        ),
    )


def _format_hooks(profile: StackProfile) -> tuple[HookSpec, ...]:
    """A single PostToolUse format hook, or none when no formatter was detected."""
    if not profile.format_command or not profile.formatter:
        return ()
    command = _format_hook_command(profile.formatter, profile.format_command)
    return (
        HookSpec(
            name=f"{profile.formatter}-format",
            event=_FORMAT_EVENT,
            matcher=_FORMAT_MATCHER,
            command=command,
        ),
    )


def _format_hook_command(formatter: str, format_command: str) -> str:
    """Build the hook-shell command body (spec §5).

    Sentinel comment first (so refresh/uninstall can find it), then a guard that
    exits cleanly when the formatter binary is absent, then the format command
    (failures swallowed so a format error never blocks the edit), then ``exit 0``.
    """
    return (
        f"# {EQUIP_SENTINEL}\n"
        f"command -v {formatter} >/dev/null 2>&1 || exit 0\n"
        f"{format_command} 2>/dev/null || true\n"
        "exit 0\n"
    )
