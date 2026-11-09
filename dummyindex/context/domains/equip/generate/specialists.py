"""The GENERATED specialist family — first-class agents keyed by capability.

Every templated specialist (db/security/performance/docs/search) generates on a
bare ``equip apply``; ``add-specialist`` or a proposal capability only moves one to
the front, keeping an applied specialist's hash-baselined identity stable. A
capability with no template falls back to manifest-only adoption on purpose.
Imports no sibling policy module, so :mod:`.adopt` stays template-agnostic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..enums import Capability, Dimension, EquipmentKind
from ..models import GenerateSpec

_AGENTS_DIR = ".context/equipment"

# Specialist template filenames, shipped alongside the core four in
# ``dummyindex/skills/equip/templates/``. Module-private — the only public read
# surface is :func:`templated_capabilities` + :data:`SPECIALIST_TEMPLATES`.
_DB_SPECIALIST_TEMPLATE = "db-specialist-agent.md.tmpl"
_SECURITY_SPECIALIST_TEMPLATE = "security-specialist-agent.md.tmpl"
_PERFORMANCE_SPECIALIST_TEMPLATE = "performance-specialist-agent.md.tmpl"
_DOCS_SPECIALIST_TEMPLATE = "docs-specialist-agent.md.tmpl"
_SEARCH_SPECIALIST_TEMPLATE = "search-specialist-agent.md.tmpl"

_HOW_TO_USE = ".context/HOW_TO_USE.md"
# Both DECISIONS locations are declared as candidates (repos differ on where
# the curated file lives); the CLI boundary filters grounding docs against
# disk, so only the location that actually exists is recorded per repo.
_DECISIONS = ".context/DECISIONS.md"
_DECISIONS_DOCS = ".context/docs/DECISIONS.md"


@dataclass(frozen=True)
class SpecialistTemplate:
    """One capability's generated-specialist template + its grounding docs.

    The agent is named ``{proj}-{name_suffix}``. ``grounding_docs`` and
    ``invariants`` go into the manifest only, never the rendered bytes, so they
    cannot shift the origin hash. ``invariants`` are slot-free literals the
    template emits verbatim; the canary (``classify_item``) reports a user edit
    that deletes one as ``INVARIANT_BROKEN``, not a silent ``CUSTOMIZED``.
    """

    capability: str
    template: str
    name_suffix: str
    grounding_docs: tuple[str, ...]
    invariants: tuple[str, ...] = ()
    # "procedure" (how to work) | "domain" (project knowledge) | None (legacy
    # single-template specialist). Manifests without it stay valid.
    dimension: Dimension | None = None


_PROC_DOCS = (_HOW_TO_USE, _DECISIONS, _DECISIONS_DOCS)
_FRONTEND_DOMAIN_DOCS = (
    _HOW_TO_USE,
    ".context/PROJECT.md",
    ".context/architecture/overview.md",
    _DECISIONS,
    _DECISIONS_DOCS,
)
_API_DOMAIN_DOCS = (
    _HOW_TO_USE,
    ".context/PROJECT.md",
    ".context/architecture/overview.md",
    ".context/conventions/data-access.md",
)
_MIGRATION_DOMAIN_DOCS = (
    _HOW_TO_USE,
    ".context/conventions/data-access.md",
    ".context/docs/SCHEMA.md",
    _DECISIONS,
    _DECISIONS_DOCS,
)
_CI_DOMAIN_DOCS = (
    _HOW_TO_USE,
    ".context/PROJECT.md",
    ".context/conventions/testing.md",
)
# Slot-free literals every procedure / domain template emits verbatim.
_PROC_INV = (
    "## Ground yourself first (mandatory, before any edit)",
    "Stay inside the planned scope.",
)
_DOMAIN_INV = (
    "## Ground yourself first (mandatory, before answering)",
    "Cite the file or doc behind every claim.",
)


def _pair(
    capability: str,
    ident: str,
    dimension: Dimension,
    docs: tuple[str, ...],
    invariants: tuple[str, ...],
) -> SpecialistTemplate:
    return SpecialistTemplate(
        capability=capability,
        template=f"{ident}-{dimension.value}-agent.md.tmpl",
        name_suffix=f"{ident}-{dimension.value}",
        grounding_docs=docs,
        invariants=invariants,
        dimension=dimension,
    )


# key -> its generated-specialist template. The key is the capability for the
# legacy single-template specialists and ``{capability}-{dimension}`` for the
# two-template ones (frontend / api / migration / ci). A capability with no
# template still falls back to manifest-only adoption. Add one here only when a
# real, grounded template backs it.
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
                _DECISIONS_DOCS,
            ),
            # Slot-free literals the db template always emits (verified verbatim):
            # the ground-first discipline, the additive-migration rule, the scope
            # guard. Deleting any is a real loss of contract, not a cosmetic edit.
            invariants=(
                "## Ground yourself first (mandatory, before any edit)",
                "Additive/expand-then-contract by default",
                "Stay inside the planned scope.",
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
                _DECISIONS_DOCS,
            ),
            # Slot-free literals the security template always emits: ground-first,
            # the tenant-isolation checklist anchor, the evidence-before-"secure"
            # rule. These ARE the security contract — dropping one is an alarm.
            invariants=(
                "## Ground yourself first (mandatory, before judging or editing)",
                "**Tenant isolation.**",
                'Never assert "secure" without the evidence to back it.',
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
                _DECISIONS_DOCS,
            ),
            # Slot-free literals the performance template always emits: ground-
            # first, the measure-first discipline, and correctness-over-speed.
            invariants=(
                "## Ground yourself first (mandatory, before any change)",
                "**Measure first.**",
                "Correctness first: never change observable behavior to win a benchmark.",
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
            # Slot-free literals the docs template always emits: ground-first, the
            # verify-against-source rule, and the no-aspirational-docs guardrail —
            # the truth-to-the-code contract that makes this specialist safe.
            invariants=(
                "## Ground yourself first (mandatory, before writing a word)",
                "every claim is one you could verify by reading the source",
                "No aspirational or speculative documentation",
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
                _DECISIONS_DOCS,
            ),
            # Slot-free literals the search template always emits: ground-first,
            # idempotent indexing, and the scope guard.
            invariants=(
                "## Ground yourself first (mandatory, before any edit)",
                "Keep indexing idempotent and",
                "Stay inside the planned scope; a new retrieval backend gets its own plan.",
            ),
        ),
        "frontend-procedure": _pair(
            Capability.FRONTEND, "frontend", Dimension.PROCEDURE, _PROC_DOCS, _PROC_INV
        ),
        "frontend-domain": _pair(
            Capability.FRONTEND,
            "frontend",
            Dimension.DOMAIN,
            _FRONTEND_DOMAIN_DOCS,
            _DOMAIN_INV,
        ),
        "api-procedure": _pair(
            Capability.API, "api", Dimension.PROCEDURE, _PROC_DOCS, _PROC_INV
        ),
        "api-domain": _pair(
            Capability.API, "api", Dimension.DOMAIN, _API_DOMAIN_DOCS, _DOMAIN_INV
        ),
        "migration-procedure": _pair(
            Capability.MIGRATION,
            "migration",
            Dimension.PROCEDURE,
            _PROC_DOCS,
            _PROC_INV,
        ),
        "migration-domain": _pair(
            Capability.MIGRATION,
            "migration",
            Dimension.DOMAIN,
            _MIGRATION_DOMAIN_DOCS,
            _DOMAIN_INV,
        ),
        "ci-procedure": _pair(
            Capability.CI, "ci", Dimension.PROCEDURE, _PROC_DOCS, _PROC_INV
        ),
        "ci-domain": _pair(
            Capability.CI, "ci", Dimension.DOMAIN, _CI_DOMAIN_DOCS, _DOMAIN_INV
        ),
    }
)


def templated_capabilities() -> frozenset[str]:
    """The set of capabilities a generated specialist template exists for.

    Handed to :func:`adopt.resolve_coverage` so the coverage policy can decide
    *generate vs adopt* per capability without importing this module.
    """
    return frozenset(t.capability for t in SPECIALIST_TEMPLATES.values())


def invariants_for(
    capabilities: tuple[str, ...], dimension: Dimension | str | None = None
) -> tuple[str, ...]:
    """The canary ``invariants`` for the first templated capability in ``capabilities``.

    Stamped by :func:`plan.render_generated_set` as manifest metadata, never
    rendered bytes. The core four (no template) get ``()``, so the canary stays
    dormant for them.
    """
    for capability in capabilities:
        for tmpl in SPECIALIST_TEMPLATES.values():
            if tmpl.capability == capability and tmpl.dimension == dimension:
                return tmpl.invariants
    return ()


def specialist_specs(
    capability: str, *, label: str, proj: str
) -> tuple[GenerateSpec, ...]:
    """Every generated spec backing ``capability`` (one, or procedure + domain)."""
    return tuple(
        specialist_spec(key, label=label, proj=proj)
        for key, tmpl in SPECIALIST_TEMPLATES.items()
        if tmpl.capability == capability
    )


def specialist_spec(capability: str, *, label: str, proj: str) -> GenerateSpec:
    """Build the :class:`GenerateSpec` for one registry key's generated specialist.

    ``capability`` is the :data:`SPECIALIST_TEMPLATES` key (the capability itself
    for legacy specialists, ``{capability}-{dimension}`` otherwise).

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
        capabilities=(tmpl.capability,),
        rel_path=f"{_AGENTS_DIR}/{name}.md",
        grounding_docs=tmpl.grounding_docs,
        dimension=tmpl.dimension.value if tmpl.dimension else None,
    )
