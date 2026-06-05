"""Adopt existing specialists to cover capability gaps — never generate, never write.

Two sources, in precedence order (spec §4):

1. **Project agents** — file stems the preflight step found under
   ``.claude/agents/``. The stem implies its capabilities via the shared keyword
   table (``security`` → security, ``db|data`` → database, …); ``subagent_type``
   is the stem itself.
2. **Known-specialist registry** — the global :class:`SubagentType` members
   (``Backend Architect``, ``Data Engineer`` …) with a fixed capability map.
   Registry agents have no project file: ``path=""``, ``source=INSTALLED``.

:func:`adopt_existing` is pure over its inputs and writes nothing. It walks the
needed capabilities in order, satisfying each at most once — a project agent
first, then a registry specialist — and skips any capability neither source
covers (it falls back to the generic implementer, decided in the catalog).
"""
from __future__ import annotations

from dummyindex.context.domains.dev_pick import SubagentType
from dummyindex.context.domains.preflight.models import PreflightReport

from ._constants import _CAPABILITY_TOKENS
from .models import AdoptSpec

# Fixed capability map for the known-specialist registry. Every SubagentType
# member maps to a non-empty tuple — including the universal ``general-purpose``
# fallback, which covers the broad implement/review work no specialist claims.
# There is intentionally no security/docs/performance specialist among the
# global members: a gap in those capabilities is left for the generic
# implementer rather than mis-adopted.
_REGISTRY_CAPABILITIES: dict[SubagentType, tuple[str, ...]] = {
    SubagentType.DATA: ("database", "data"),
    SubagentType.FRONTEND: ("frontend",),
    SubagentType.AI: ("data",),
    SubagentType.BACKEND: ("implement",),
    SubagentType.SENIOR: ("implement", "review"),
    SubagentType.GENERAL: ("implement", "review"),
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


def adopt_existing(
    *, preflight: PreflightReport, needed: tuple[str, ...]
) -> tuple[AdoptSpec, ...]:
    """Adopt project/registry specialists covering the ``needed`` capabilities.

    Returns one :class:`AdoptSpec` per capability actually covered, each
    capability satisfied at most once. Project agents are preferred; the
    registry fills remaining gaps; uncovered capabilities yield nothing.
    """
    project = _project_specs(preflight.project_agents)
    covered: set[str] = set()
    adopted: list[AdoptSpec] = []

    for capability in needed:
        if capability in covered:
            continue
        spec = _match_project(project, capability) or _match_registry(capability)
        if spec is None:
            continue
        adopted.append(spec)
        covered.update(spec.capabilities)
    return tuple(adopted)


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
