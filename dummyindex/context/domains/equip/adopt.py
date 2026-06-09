"""Resolve a capability set into *generate vs adopt* coverage (spec §4).

Per capability, in precedence order:

1. **Project agent** — a file stem the preflight step found under
   ``.claude/agents/``. The stem implies its capabilities via the shared keyword
   table (``security`` → security, ``db|data`` → database, …); ``subagent_type``
   is the stem itself. Adopted (manifest-only): the user already covers it.
2. **Generated specialist template** — a capability a shipped template backs is
   *generated* as a first-class, editable, hash-baselined file (the catalog
   renders it). This supersedes a registry adoption: a grounded template is a
   real specialist, not a manifest pointer.
3. **Known-specialist registry** — the global :class:`SubagentType` members
   (``Backend Architect``, ``Data Engineer`` …) with a fixed capability map.
   Registry agents have no project file: ``path=""``, ``source=INSTALLED``.

A capability none of these cover falls back to the generic implementer.

:func:`resolve_coverage` is pure over its inputs and writes nothing. *Forced*
capabilities (an explicit ``add-specialist`` ask, or an already-applied
specialist read back from the manifest) generate whenever a template exists,
bypassing the project-agent preference — the user has committed to a generated
file. :func:`adopt_existing` is the back-compat thin wrapper: pure adoption with
no templates and no forced caps.
"""
from __future__ import annotations

from dataclasses import dataclass

from dummyindex.context.domains.dev_pick import SubagentType
from dummyindex.context.domains.preflight.models import PreflightReport

from ._constants import _CAPABILITY_TOKENS
from .enums import Capability, EquipmentKind
from .models import AdoptSpec, EquipmentItem

# Fixed capability map for the known-specialist registry. Every SubagentType
# member maps to a non-empty tuple — including the universal ``general-purpose``
# fallback, which covers the broad implement/review work no specialist claims.
# There is intentionally no security/docs/performance specialist among the
# global members: a gap in those capabilities is left for the generic
# implementer rather than mis-adopted.
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
) -> Coverage:
    """Split requested capabilities into generate vs adopt (spec §4).

    ``forced_capabilities`` (an explicit ``add-specialist`` ask, or an
    already-applied specialist carried forward from the manifest) generate a
    specialist whenever a template backs them — bypassing the project-agent
    preference. A forced capability with no template is dropped here (the CLI
    validates explicit asks; manifest-derived forced caps are always templated).

    ``proposal_capabilities`` follow the full precedence: a covering project
    agent is adopted first (the user already owns it — not a gap), else a
    template generates, else a registry specialist is adopted, else the gap
    falls to the generic implementer. Each capability is satisfied at most once.
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
            generate.append(capability)
            covered.add(capability)
            continue
        registry_spec = _match_registry(capability)
        if registry_spec is not None:
            adopt.append(registry_spec)
            covered.update(registry_spec.capabilities)
            continue
        # Uncovered: left to the generic implementer (decided in the catalog).

    return Coverage(generate_capabilities=tuple(generate), adopt=tuple(adopt))


def adopt_existing(
    *, preflight: PreflightReport, needed: tuple[str, ...]
) -> tuple[AdoptSpec, ...]:
    """Adopt project/registry specialists covering the ``needed`` capabilities.

    The back-compat surface for pure adoption (no templates, no forced caps):
    one :class:`AdoptSpec` per capability actually covered, project agents
    preferred, registry fills remaining gaps, uncovered capabilities yield
    nothing. Equivalent to :func:`resolve_coverage` with an empty templated set.
    """
    return resolve_coverage(
        preflight=preflight, proposal_capabilities=needed
    ).adopt


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


def _match_project(
    project: tuple[AdoptSpec, ...], capability: str
) -> AdoptSpec | None:
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
    """Render an adoption as an :class:`EquipmentItem` for the manifest.

    Module-level converter (not a method) — data classes hold data; the
    transformation lives with the adoption logic that produces the specs.
    """
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=spec.name,
        path=spec.path,
        source=spec.source,
        capabilities=spec.capabilities,
        subagent_type=spec.subagent_type,
    )


def registry_capabilities() -> dict[SubagentType, tuple[str, ...]]:
    """Public, read-only view of the registry capability map (copy).

    Exposed so callers (and tests) never reach into the private module-level
    table; mutating the returned dict has no effect on adoption.
    """
    return dict(_REGISTRY_CAPABILITIES)
