"""The GENERATED specialist family — first-class agents keyed by capability.

The four core tools (implementer / tester / reviewer / verify) are always
generated. *Specialists* (db / security / performance / docs / search) are
generated **on demand** — when a proposal's plan demands a capability a template
covers, or the user asks explicitly via ``equip add-specialist <capability>``.
A capability with **no** template here is not generated: it falls back to a
manifest-only adoption (a project agent or a registry specialist such as
*Frontend Developer*) — that fallback is deliberate, not a missing feature.

Each :class:`SpecialistTemplate` declares the shipped ``*.md.tmpl`` it renders,
the project-scoped name suffix (so the file, the frontmatter ``name:``, and the
manifest ``subagent_type`` all agree — the one invariant the refresh/reset
lifecycle relies on), and the ``.context/`` docs the specialist grounds in. The
templates fill the same slots the core four use (``{{stack}}`` / ``{{proj}}`` /
``{{conventions}}`` / the toolchain commands), so no new render machinery is
needed: a specialist *is* a core-shaped generated artifact, hash-baselined and
lifecycle-managed identically.

This module is pure data + one constructor; it imports no sibling policy module,
so :mod:`.adopt` stays template-agnostic (it is handed the templated-capability
set as a parameter) and :mod:`.catalog` composes the two.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .enums import Capability, EquipmentKind
from .models import GenerateSpec

_AGENTS_DIR = ".claude/agents"

# Specialist template filenames, shipped alongside the core four in
# ``dummyindex/skills/equip/templates/``. Module-private — the only public read
# surface is :func:`templated_capabilities` + :data:`SPECIALIST_TEMPLATES`.
_DB_SPECIALIST_TEMPLATE = "db-specialist-agent.md.tmpl"
_SECURITY_SPECIALIST_TEMPLATE = "security-specialist-agent.md.tmpl"
_PERFORMANCE_SPECIALIST_TEMPLATE = "performance-specialist-agent.md.tmpl"
_DOCS_SPECIALIST_TEMPLATE = "docs-specialist-agent.md.tmpl"
_SEARCH_SPECIALIST_TEMPLATE = "search-specialist-agent.md.tmpl"

_HOW_TO_USE = ".context/HOW_TO_USE.md"
_DECISIONS = ".context/DECISIONS.md"


@dataclass(frozen=True)
class SpecialistTemplate:
    """One capability's generated-specialist template + its grounding docs.

    ``name_suffix`` is appended to the project slug to form the agent's name
    (``{proj}-{name_suffix}``). ``grounding_docs`` are the capability-specific
    ``.context/`` paths the rendered prose points the specialist at; they are
    recorded in the manifest's ``grounded_in`` (metadata only — never part of
    the rendered bytes, so they cannot affect the origin-hash baseline).
    """

    capability: str
    template: str
    name_suffix: str
    grounding_docs: tuple[str, ...]


# capability -> its generated-specialist template. Deliberately omits FRONTEND:
# the registry's *Frontend Developer* covers it, so frontend stays a
# manifest-only adoption (the canonical "no template → adopt" fallback). Add a
# capability here only when a real, grounded template backs it.
#
# A read-only ``MappingProxyType`` (not a bare ``dict``): the registry is a fixed
# constant — a caller must never be able to mutate the package's specialist set
# (global immutability rule). Iteration / ``[]`` / ``.items()`` / ``in`` all work
# for reads (and tests), only assignment is refused.
SPECIALIST_TEMPLATES: Mapping[str, SpecialistTemplate] = MappingProxyType(
    {
        Capability.DATABASE: SpecialistTemplate(
            capability=Capability.DATABASE,
            template=_DB_SPECIALIST_TEMPLATE,
            name_suffix="db-specialist",
            grounding_docs=(
                _HOW_TO_USE,
                ".context/conventions/data-access.md",
                ".context/docs/SCHEMA.md",
                _DECISIONS,
            ),
        ),
        Capability.SECURITY: SpecialistTemplate(
            capability=Capability.SECURITY,
            template=_SECURITY_SPECIALIST_TEMPLATE,
            name_suffix="security-specialist",
            grounding_docs=(
                _HOW_TO_USE,
                ".context/conventions/auth.md",
                ".context/conventions/security.md",
                _DECISIONS,
            ),
        ),
        Capability.PERFORMANCE: SpecialistTemplate(
            capability=Capability.PERFORMANCE,
            template=_PERFORMANCE_SPECIALIST_TEMPLATE,
            name_suffix="performance-specialist",
            grounding_docs=(
                _HOW_TO_USE,
                ".context/conventions/performance.md",
                _DECISIONS,
            ),
        ),
        Capability.DOCS: SpecialistTemplate(
            capability=Capability.DOCS,
            template=_DOCS_SPECIALIST_TEMPLATE,
            name_suffix="docs-specialist",
            grounding_docs=(
                _HOW_TO_USE,
                ".context/PROJECT.md",
                ".context/INDEX.md",
            ),
        ),
        Capability.SEARCH: SpecialistTemplate(
            capability=Capability.SEARCH,
            template=_SEARCH_SPECIALIST_TEMPLATE,
            name_suffix="search-specialist",
            grounding_docs=(
                _HOW_TO_USE,
                ".context/conventions/data-access.md",
                ".context/docs/SCHEMA.md",
                _DECISIONS,
            ),
        ),
    }
)


def templated_capabilities() -> frozenset[str]:
    """The set of capabilities a generated specialist template exists for.

    Handed to :func:`adopt.resolve_coverage` so the coverage policy can decide
    *generate vs adopt* per capability without importing this module.
    """
    return frozenset(SPECIALIST_TEMPLATES)


def specialist_spec(capability: str, *, label: str, proj: str) -> GenerateSpec:
    """Build the :class:`GenerateSpec` for ``capability``'s generated specialist.

    The name is project-scoped (``{proj}-{suffix}``) so it is stable across
    apply/refresh/reset — the manifest matches by name only. Raises
    :class:`KeyError` if no template backs ``capability`` (callers gate on
    :func:`templated_capabilities`).
    """
    tmpl = SPECIALIST_TEMPLATES[capability]
    name = f"{proj}-{tmpl.name_suffix}"
    return GenerateSpec(
        name=name,
        kind=EquipmentKind.AGENT,
        template=tmpl.template,
        capabilities=(capability,),
        rel_path=f"{_AGENTS_DIR}/{name}.md",
        grounding_docs=tmpl.grounding_docs,
    )
