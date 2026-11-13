"""The policy core: decide what equip generates, adopts, and wires (spec §3 + §6).

:func:`build_catalog` is a pure function over a :class:`StackProfile`, the repo's
convention docs, a :class:`PreflightReport`, and (optionally) the capabilities a
proposal demands. It returns a :class:`CatalogDecision` — no I/O, fully
unit-testable. The CLI boundary (Phase 2) renders + writes from this decision.

Policy (spec §3 + §6):

- **Generate** (always): ``{label}-implementer`` + ``{label}-tester`` agents, a
  ``{proj}-reviewer`` agent, a ``{proj}-verify`` skill, and the baseline
  specialists (security / performance / docs) on every non-generic stack. The
  evidence-gated ones (db / search) need stack evidence, a proposal capability,
  or an explicit ask; the dimensioned ones (frontend / api / migration / ci) are
  signal-gated the same way.
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
from ..enums import Capability, EquipmentKind
from ..models import CatalogDecision, GenerateSpec, HookSpec, StackProfile
from .adopt import resolve_coverage
from .render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
)
from .specialists import (
    ALWAYS_ON_CAPABILITIES,
    SPECIALIST_TEMPLATES,
    specialist_specs,
    templated_capabilities,
)

_CAPABILITIES_DIR = ".context/equipment"
_FORMAT_EVENT = "PostToolUse"
_FORMAT_MATCHER = "Write|Edit"

# Frontend evidence (the stack-consistency gate for registry adoption): a
# frontend-ecosystem language label, or any detected frontend framework.
_FRONTEND_STACK_LABELS = frozenset({"typescript", "javascript"})
_FRONTEND_FRAMEWORKS = frozenset({"react", "vue", "svelte", "next.js"})
_API_FRAMEWORKS = frozenset({"fastapi", "django", "flask", "express", "spring boot"})


def profile_has_frontend(profile: StackProfile) -> bool:
    """True when the detected stack shows real frontend evidence.

    Pure predicate feeding ``resolve_coverage(stack_frontend=...)`` so a
    backend-only repo never adopts a Frontend Developer off plan-text keywords.
    """
    if profile.label in _FRONTEND_STACK_LABELS:
        return True
    return any(f.lower() in _FRONTEND_FRAMEWORKS for f in profile.frameworks)


def profile_has_api(profile: StackProfile) -> bool:
    """True when the detected stack shows a server-side web/API framework."""
    return any(f.lower() in _API_FRAMEWORKS for f in profile.frameworks)


def _stack_signalled_capabilities(profile: StackProfile) -> tuple[str, ...]:
    """Dimensioned capabilities (frontend / api) the detected stack evidences.

    migration / ci carry no stack evidence in the profile: they are generated
    only when a proposal names them or an explicit ask / manifest carries them.
    """
    out: list[str] = []
    if profile_has_frontend(profile):
        out.append(Capability.FRONTEND)
    if profile_has_api(profile):
        out.append(Capability.API)
    return tuple(out)


def _evidenced_capabilities(profile: StackProfile) -> frozenset[str]:
    """Evidence-gated capabilities the detected stack actually backs."""
    out: set[str] = set()
    if profile.data_stores:
        out.add(Capability.DATABASE)
    if profile.search_backends:
        out.add(Capability.SEARCH)
    return frozenset(out)


def _all_templated_capabilities(
    forced: tuple[str, ...], profile: StackProfile
) -> tuple[str, ...]:
    """``forced`` followed by the undimensioned capabilities this stack earns.

    Baseline specialists (security / performance / docs) join on every non-generic
    stack; evidence-gated ones (db / search) join only when the stack evidences
    them. Dimensioned capabilities (frontend / api / migration / ci) are NOT
    forced: they are signal-gated, so a backend repo gets no frontend specialist
    and a user's own matching project agent is still adopted. Explicit /
    manifest-carried capabilities lead the order so their spec order (and
    manifest order) is stable across re-applies; the remainder follow in
    :data:`SPECIALIST_TEMPLATES` declaration order for determinism.
    """
    baseline: frozenset[str] = (
        frozenset() if profile.label == "generic" else ALWAYS_ON_CAPABILITIES
    )
    earned = baseline | _evidenced_capabilities(profile)
    ordered = list(forced) + [
        t.capability
        for t in SPECIALIST_TEMPLATES.values()
        if t.dimension is None and t.capability in earned and t.capability not in forced
    ]
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

    Baseline specialists are generated on every equip pass of a non-generic
    stack. Evidence-gated ones (db / search) and dimensioned ones (frontend / api
    / migration / ci) are generated only on a stack / proposal signal or an
    explicit ask.

    ``forced_specialist_capabilities`` (an explicit ``add-specialist`` ask, plus
    already-applied specialists carried forward from the manifest) are still
    honoured and still lead the order, so an explicit ask and a re-apply keep
    their existing, hash-baselined identity.
    ``proposal_capabilities`` follow the precedence in :func:`resolve_coverage`
    (project agent → template → registry → generic); a capability with no
    template still falls through to adoption.
    """
    # Stack-detected dimensioned capabilities ride the proposal path (project
    # agent -> template), so a user's own matching agent still wins adoption.
    signalled = tuple(
        c
        for c in _stack_signalled_capabilities(profile)
        if c not in proposal_capabilities
    )
    coverage = resolve_coverage(
        preflight=preflight,
        proposal_capabilities=proposal_capabilities + signalled,
        forced_capabilities=_all_templated_capabilities(
            forced_specialist_capabilities, profile
        ),
        templated_capabilities=templated_capabilities(),
        stack_frontend=profile_has_frontend(profile),
    )
    specialists = tuple(
        spec
        for capability in coverage.generate_capabilities
        for spec in specialist_specs(capability, label=profile.label, proj=proj)
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
