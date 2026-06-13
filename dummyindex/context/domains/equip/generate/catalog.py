"""The policy core: decide what equip generates, adopts, and wires.

:func:`build_catalog` is a pure function over a :class:`StackProfile`, the repo's
convention docs, a :class:`PreflightReport`, and (optionally) the capabilities a
proposal demands. It returns a :class:`CatalogDecision` — no I/O, fully
unit-testable. The CLI boundary (Phase 2) renders + writes from this decision.

Policy (spec §3 + §6):

- **Generate** (always): ``{label}-implementer`` + ``{label}-tester`` agents, a
  ``{proj}-reviewer`` agent, and a ``{proj}-verify`` skill — plus, on demand,
  any GENERATED specialist (``{proj}-db-specialist`` …) a requested capability
  has a template for.
- **Hooks**: a PostToolUse format hook iff ``profile.format_command`` was
  detected (binary-guarded by the formatter name; spec §5).
- **Adopt**: project/registry specialists covering the proposal capabilities a
  template does *not* back. A grounded template is a real specialist (generated
  as a file), not a speculative one; only an un-grounded, no-template, no-evidence
  capability stays un-generated — left to a manifest-only adoption or the
  generic implementer.
"""
from __future__ import annotations

from dummyindex.context.domains.preflight.models import PreflightReport

from ..constants import EQUIP_SENTINEL
from .adopt import resolve_coverage
from ..enums import Capability, EquipmentKind
from ..models import CatalogDecision, GenerateSpec, HookSpec, StackProfile
from .render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
)
from .specialists import specialist_spec, templated_capabilities

_AGENTS_DIR = ".claude/agents"
_SKILLS_DIR = ".claude/skills"
_FORMAT_EVENT = "PostToolUse"
_FORMAT_MATCHER = "Write|Edit"

# Frontend evidence (the stack-consistency gate for registry adoption): a
# frontend-ecosystem language label, or any detected frontend framework.
_FRONTEND_STACK_LABELS = frozenset({"typescript", "javascript"})
_FRONTEND_FRAMEWORKS = frozenset({"react", "vue", "svelte", "next.js"})


def profile_has_frontend(profile: StackProfile) -> bool:
    """True when the detected stack shows real frontend evidence.

    Pure predicate feeding ``resolve_coverage(stack_frontend=...)`` so a
    backend-only repo never adopts a Frontend Developer off plan-text keywords.
    """
    if profile.label in _FRONTEND_STACK_LABELS:
        return True
    return any(f.lower() in _FRONTEND_FRAMEWORKS for f in profile.frameworks)


def build_catalog(
    *,
    profile: StackProfile,
    conventions: tuple[str, ...],
    preflight: PreflightReport,
    proj: str,
    proposal_capabilities: tuple[str, ...] = (),
    forced_specialist_capabilities: tuple[str, ...] = (),
) -> CatalogDecision:
    """Decide the full equip toolkit for this repo. Pure; no I/O.

    ``forced_specialist_capabilities`` are capabilities to GENERATE a specialist
    for unconditionally when a template backs them — an explicit
    ``add-specialist`` ask, plus any already-applied specialist carried forward
    from the manifest so a plain re-apply never drops it.
    ``proposal_capabilities`` follow the precedence in :func:`resolve_coverage`
    (project agent → template → registry → generic).
    """
    coverage = resolve_coverage(
        preflight=preflight,
        proposal_capabilities=proposal_capabilities,
        forced_capabilities=forced_specialist_capabilities,
        templated_capabilities=templated_capabilities(),
        stack_frontend=profile_has_frontend(profile),
    )
    specialists = tuple(
        specialist_spec(capability, label=profile.label, proj=proj)
        for capability in coverage.generate_capabilities
    )
    generate = _standard_generated_set(profile.label, proj) + specialists
    hooks = _format_hooks(profile)
    return CatalogDecision(generate=generate, adopt=coverage.adopt, hooks=hooks)


def _standard_generated_set(label: str, proj: str) -> tuple[GenerateSpec, ...]:
    return (
        GenerateSpec(
            name=f"{label}-implementer",
            kind=EquipmentKind.AGENT,
            template=IMPLEMENTER_TEMPLATE,
            capabilities=(Capability.IMPLEMENT,),
            rel_path=f"{_AGENTS_DIR}/{label}-implementer.md",
        ),
        GenerateSpec(
            name=f"{label}-tester",
            kind=EquipmentKind.AGENT,
            template=TESTER_TEMPLATE,
            capabilities=(Capability.TEST,),
            rel_path=f"{_AGENTS_DIR}/{label}-tester.md",
        ),
        GenerateSpec(
            name=f"{proj}-reviewer",
            kind=EquipmentKind.AGENT,
            template=REVIEWER_TEMPLATE,
            capabilities=(Capability.REVIEW,),
            rel_path=f"{_AGENTS_DIR}/{proj}-reviewer.md",
        ),
        GenerateSpec(
            name=f"{proj}-verify",
            kind=EquipmentKind.SKILL,
            template=VERIFY_TEMPLATE,
            capabilities=(Capability.TEST, Capability.VERIFY),
            rel_path=f"{_SKILLS_DIR}/{proj}-verify/SKILL.md",
        ),
    )


def _format_hooks(profile: StackProfile) -> tuple[HookSpec, ...]:
    """A single PostToolUse format hook, or none when no formatter was detected."""
    if not profile.format_command or not profile.formatter:
        return ()
    command = _format_hook_command(
        profile.formatter, profile.format_command, event=_FORMAT_EVENT
    )
    return (
        HookSpec(
            name=f"{profile.formatter}-format",
            event=_FORMAT_EVENT,
            matcher=_FORMAT_MATCHER,
            command=command,
        ),
    )


def _format_hook_command(formatter: str, format_command: str, *, event: str) -> str:
    """Build the hook-shell command body (spec §5).

    Sentinel comment first (so refresh/uninstall can find it), suffixed with the
    event name so future hooks targeting different events key independently;
    then a guard that exits cleanly when the formatter binary is absent, then
    the format command (failures swallowed so a format error never blocks the
    edit), then ``exit 0``.
    """
    return (
        f"# {EQUIP_SENTINEL}:{event}\n"
        f"command -v {formatter} >/dev/null 2>&1 || exit 0\n"
        f"{format_command} 2>/dev/null || true\n"
        "exit 0\n"
    )
