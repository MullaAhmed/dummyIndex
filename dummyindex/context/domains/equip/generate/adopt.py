"""Resolve a capability set into *generate vs adopt* coverage (spec §4).

Precedence per capability: a project agent whose ``.claude/agents/`` stem implies
it (adopted, manifest-only); else a shipped specialist template (generated as an
editable, hash-baselined file); else a :class:`SubagentType` registry specialist
(adopted, ``path=""``); else the generic implementer. *Forced* capabilities
generate whenever a template exists, skipping the project-agent step. Pure.
"""

from __future__ import annotations

from dataclasses import dataclass

from dummyindex.context.domains.dev_pick import SubagentType
from dummyindex.context.domains.preflight.models import PreflightReport

from ..constants import _CAPABILITY_TOKENS
from ..enums import Capability, EquipmentKind
from ..models import AdoptSpec, EquipmentItem

# Registry capability map; every SubagentType member, ``general-purpose`` included,
# maps to a non-empty tuple. No member covers security/docs/performance on purpose:
# those gaps go to the generic implementer rather than a mis-adoption.
_REGISTRY_CAPABILITIES: dict[SubagentType, tuple[str, ...]] = {
    SubagentType.DATA: (Capability.DATABASE, Capability.DATA),
    SubagentType.FRONTEND: (Capability.FRONTEND,),
    SubagentType.AI: (Capability.DATA,),
    SubagentType.BACKEND: (Capability.IMPLEMENT,),
    SubagentType.SENIOR: (Capability.IMPLEMENT, Capability.REVIEW),
    SubagentType.GENERAL: (Capability.IMPLEMENT, Capability.REVIEW),
}


def _infer_capabilities(stem: str) -> tuple[str, ...]:
    """Capabilities implied by an agent's file stem, via the shared token table.

    Lowercased substring match. A stem can imply several capabilities (e.g.
    ``data-migration-reviewer`` → database + review). Order follows the table.
    """
    text = stem.lower()
    out: list[str] = []
    for capability, tokens in _CAPABILITY_TOKENS:
        if any(token in text for token in tokens) and capability not in out:
            out.append(capability)
    return tuple(out)


@dataclass(frozen=True)
class Coverage:
    """The split of a requested capability set into generate vs adopt.

    ``generate_capabilities`` are the capabilities the catalog should render a
    generated specialist for (each backed by a template); ``adopt`` are the
    manifest-only adoptions (project agents / registry specialists). Each
    requested capability lands in at most one bucket.
    """

    generate_capabilities: tuple[str, ...] = ()
    adopt: tuple[AdoptSpec, ...] = ()


def resolve_coverage(
    *,
    preflight: PreflightReport,
    proposal_capabilities: tuple[str, ...] = (),
    forced_capabilities: tuple[str, ...] = (),
    templated_capabilities: frozenset[str] = frozenset(),
    stack_frontend: bool = True,
) -> Coverage:
    """Split requested capabilities into generate vs adopt (spec §4).

    ``forced_capabilities`` generate when a template backs them, else are dropped.
    ``proposal_capabilities`` follow the module precedence, each satisfied once.
    ``stack_frontend=False`` (no frontend evidence) skips FRONTEND *registry*
    adoptions so a backend repo never gets a Frontend Developer off plan text;
    project agents bypass that gate.
    """
    project = _project_specs(preflight.project_agents)
    covered: set[str] = set()
    generate: list[str] = []
    adopt: list[AdoptSpec] = []

    for capability in forced_capabilities:
        if capability in covered:
            continue
        if capability in templated_capabilities:
            generate.append(capability)
            covered.add(capability)

    for capability in proposal_capabilities:
        if capability in covered:
            continue
        project_spec = _match_project(project, capability)
        if project_spec is not None:
            adopt.append(project_spec)
            covered.update(project_spec.capabilities)
            continue
        if capability in templated_capabilities:
            if not stack_frontend and capability == Capability.FRONTEND:
                # Same stack-consistency gate as the registry branch: no
                # frontend evidence ⇒ no frontend specialist either.
                continue
            generate.append(capability)
            covered.add(capability)
            continue
        registry_spec = _match_registry(capability)
        if registry_spec is not None:
            if not stack_frontend and Capability.FRONTEND in registry_spec.capabilities:
                # No frontend evidence: leave it to the generic implementer.
                # The CLI surfaces the skip so it is not silent.
                continue
            adopt.append(registry_spec)
            covered.update(registry_spec.capabilities)
            continue
        # Uncovered: left to the generic implementer (decided in the catalog).

    return Coverage(generate_capabilities=tuple(generate), adopt=tuple(adopt))


def adopt_existing(
    *, preflight: PreflightReport, needed: tuple[str, ...]
) -> tuple[AdoptSpec, ...]:
    """Adopt project/registry specialists covering the ``needed`` capabilities.

    Back-compat pure adoption: :func:`resolve_coverage` with no templates and no
    forced caps. Project agents first, registry next; uncovered yields nothing.
    """
    return resolve_coverage(preflight=preflight, proposal_capabilities=needed).adopt


def _project_specs(project_agents: tuple[str, ...]) -> tuple[AdoptSpec, ...]:
    """One :class:`AdoptSpec` per project agent, capabilities inferred from stem."""
    specs: list[AdoptSpec] = []
    for stem in project_agents:
        caps = _infer_capabilities(stem)
        if not caps:
            continue
        specs.append(
            AdoptSpec(
                name=stem,
                subagent_type=stem,
                capabilities=caps,
                path=f".claude/agents/{stem}.md",
            )
        )
    return tuple(specs)


def _match_project(project: tuple[AdoptSpec, ...], capability: str) -> AdoptSpec | None:
    for spec in project:
        if capability in spec.capabilities:
            return spec
    return None


def _match_registry(capability: str) -> AdoptSpec | None:
    for member, caps in _REGISTRY_CAPABILITIES.items():
        if capability in caps:
            return AdoptSpec(
                name=member.value,
                subagent_type=member.value,
                capabilities=caps,
            )
    return None


def adopt_spec_to_item(spec: AdoptSpec) -> EquipmentItem:
    """Render an adoption as an :class:`EquipmentItem` for the manifest."""
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=spec.name,
        path=spec.path,
        source=spec.source,
        capabilities=spec.capabilities,
        subagent_type=spec.subagent_type,
    )


def registry_capabilities() -> dict[SubagentType, tuple[str, ...]]:
    """A copy of the registry capability map; mutating it has no effect."""
    return dict(_REGISTRY_CAPABILITIES)
