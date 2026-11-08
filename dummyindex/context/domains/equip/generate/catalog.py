"""The policy core: decide what equip generates, adopts, and wires (spec §3 + §6).

:func:`build_catalog` is pure; the CLI renders and writes its :class:`CatalogDecision`.
It always generates the implementer, tester, reviewer, verify skill and **every**
template-backed specialist (no opt-in); adds a PostToolUse format hook iff a
formatter was detected (binary-guarded, spec §5); and adopts project/registry
specialists for proposal capabilities no template backs.
"""

from __future__ import annotations

from dummyindex.context.domains.preflight.models import PreflightReport

from ..constants import EQUIP_SENTINEL
from ..enums import Capability, EquipmentKind
from ..models import CatalogDecision, GenerateSpec, HookSpec, StackProfile
from .adopt import resolve_coverage
from .render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
)
from .specialists import SPECIALIST_TEMPLATES, specialist_spec, templated_capabilities

_CAPABILITIES_DIR = ".context/equipment"
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


def _all_templated_capabilities(forced: tuple[str, ...]) -> tuple[str, ...]:
    """``forced`` followed by every template-backed capability, deduplicated.

    Specialists generate unconditionally, so the forced set is the whole templated
    alphabet. Explicit/manifest-carried capabilities lead so the manifest order is
    stable across re-applies; the rest follow :data:`SPECIALIST_TEMPLATES` order.
    """
    ordered = list(forced) + [c for c in SPECIALIST_TEMPLATES if c not in forced]
    return tuple(dict.fromkeys(ordered))


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

    Every template-backed specialist generates on every pass (an ability, not an
    opt-in). ``forced_specialist_capabilities`` (an ``add-specialist`` ask plus
    specialists carried from the manifest) lead the order so they keep their
    hash-baselined identity. ``proposal_capabilities`` follow the precedence in
    :func:`resolve_coverage`; one with no template falls through to adoption.
    """
    coverage = resolve_coverage(
        preflight=preflight,
        proposal_capabilities=proposal_capabilities,
        forced_capabilities=_all_templated_capabilities(forced_specialist_capabilities),
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
            rel_path=f"{_CAPABILITIES_DIR}/{label}-implementer.md",
        ),
        GenerateSpec(
            name=f"{label}-tester",
            kind=EquipmentKind.AGENT,
            template=TESTER_TEMPLATE,
            capabilities=(Capability.TEST,),
            rel_path=f"{_CAPABILITIES_DIR}/{label}-tester.md",
        ),
        GenerateSpec(
            name=f"{proj}-reviewer",
            kind=EquipmentKind.AGENT,
            template=REVIEWER_TEMPLATE,
            capabilities=(Capability.REVIEW,),
            rel_path=f"{_CAPABILITIES_DIR}/{proj}-reviewer.md",
        ),
        GenerateSpec(
            name=f"{proj}-verify",
            kind=EquipmentKind.SKILL,
            template=VERIFY_TEMPLATE,
            capabilities=(Capability.TEST, Capability.VERIFY),
            rel_path=f"{_CAPABILITIES_DIR}/{proj}-verify.md",
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
    native_command = format_command.replace("<changed-paths>", '"$CLAUDE_FILE_PATHS"')
    if native_command.startswith("uv run "):
        native_command = native_command[len("uv run ") :]
    return (
        f"# {EQUIP_SENTINEL}:{event}\n"
        f"command -v {formatter} >/dev/null 2>&1 || exit 0\n"
        f"{native_command} 2>/dev/null || true\n"
        "exit 0\n"
    )
