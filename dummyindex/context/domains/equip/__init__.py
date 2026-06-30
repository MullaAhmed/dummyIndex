"""Templates-first equip: render a tuned ``.claude/`` toolkit from ``.context/``.

Public surface: detect the stack + formatter, render the shipped templates with
project values, guard every write so it never clobbers a user file, and record
the result in ``.context/equipment.json``. The CLI boundary
(``dummyindex/cli/equip/``) wires these together; this package holds the logic.
"""

from __future__ import annotations

from .constants import EQUIP_SENTINEL, SCHEMA_VERSION, VENDORED_SENTINEL
from .enums import (
    Capability,
    EquipmentKind,
    EquipmentSource,
    EquipVerb,
    InstallMechanism,
    ItemState,
    PluginSurface,
    TrustTier,
)
from .errors import (
    CatalogError,
    EquipError,
    PatchError,
    RemoveError,
    ResetError,
    SourceError,
    TemplateError,
)
from .generate.adopt import (
    Coverage,
    adopt_existing,
    adopt_spec_to_item,
    registry_capabilities,
    resolve_coverage,
)
from .generate.catalog import build_catalog, profile_has_frontend
from .generate.detect import detect_stack
from .generate.gaps import (
    capability_gaps,
    covered_capabilities,
    required_capabilities,
)
from .generate.plan import render_generated_set
from .generate.proposal import capabilities_from_text, extract_proposal_capabilities
from .generate.render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
    list_convention_docs,
    render_template,
    set_frontmatter_version,
)
from .generate.specialists import (
    SPECIALIST_TEMPLATES,
    SpecialistTemplate,
    specialist_spec,
    templated_capabilities,
)
from .lifecycle.evolve import apply_patch
from .lifecycle.hashing import content_hash
from .lifecycle.manifest import EQUIPMENT_REL, read_manifest, write_manifest
from .lifecycle.remove import RemoveReport, remove_item
from .lifecycle.status import (
    RefreshReport,
    StatusReport,
    UninstallReport,
    classify_item,
    is_evolved,
    is_lifecycle_managed,
    is_user_owned,
    is_vendored_file,
    refresh,
    reset,
    status,
    uninstall,
)
from .models import (
    GENERATED_SENTINEL,
    AdoptSpec,
    CatalogDecision,
    EquipmentItem,
    EquipmentManifest,
    GenerateSpec,
    HookSpec,
    StackProfile,
)
from .plugins.blast_radius import BlastRadius, analyze_blast_radius
from .plugins.discover import Candidate, capabilities_for, match_candidates
from .plugins.install_plan import InstallPlan, PlannedInstall, build_install_plan
from .plugins.marketplace import (
    SEED_MARKETPLACES,
    MarketplaceCatalog,
    PluginEntry,
    SeedMarketplace,
    parse_catalog,
    validate_catalog,
)
from .plugins.sources import (
    GitHubSearchResult,
    Runner,
    RunResult,
    SkillRef,
    ToolAvailability,
    available_tools,
    default_runner,
    fetch_catalog,
    fetch_file,
    list_skills,
    resolve_ref,
    search_github,
)
from .plugins.vendor import stamp_vendored, vendored_item
from .wiring.hooks import wire_hooks
from .wiring.safety import is_safe_to_write

__all__ = [
    "EQUIPMENT_REL",
    "EQUIP_SENTINEL",
    "GENERATED_SENTINEL",
    "IMPLEMENTER_TEMPLATE",
    "REVIEWER_TEMPLATE",
    "SCHEMA_VERSION",
    "SEED_MARKETPLACES",
    "TESTER_TEMPLATE",
    "VENDORED_SENTINEL",
    "VERIFY_TEMPLATE",
    "SPECIALIST_TEMPLATES",
    "AdoptSpec",
    "BlastRadius",
    "Candidate",
    "Capability",
    "CatalogDecision",
    "CatalogError",
    "Coverage",
    "EquipError",
    "EquipVerb",
    "EquipmentItem",
    "EquipmentKind",
    "EquipmentManifest",
    "EquipmentSource",
    "GenerateSpec",
    "GitHubSearchResult",
    "HookSpec",
    "InstallMechanism",
    "InstallPlan",
    "ItemState",
    "MarketplaceCatalog",
    "PatchError",
    "PlannedInstall",
    "PluginEntry",
    "PluginSurface",
    "RefreshReport",
    "RemoveError",
    "RemoveReport",
    "ResetError",
    "RunResult",
    "Runner",
    "SeedMarketplace",
    "SkillRef",
    "SourceError",
    "SpecialistTemplate",
    "StackProfile",
    "StatusReport",
    "TemplateError",
    "ToolAvailability",
    "TrustTier",
    "UninstallReport",
    "parse_catalog",
    "validate_catalog",
    "adopt_existing",
    "adopt_spec_to_item",
    "analyze_blast_radius",
    "apply_patch",
    "available_tools",
    "build_catalog",
    "build_install_plan",
    "capabilities_for",
    "capabilities_from_text",
    "capability_gaps",
    "classify_item",
    "content_hash",
    "covered_capabilities",
    "default_runner",
    "detect_stack",
    "fetch_catalog",
    "fetch_file",
    "match_candidates",
    "profile_has_frontend",
    "search_github",
    "extract_proposal_capabilities",
    "is_evolved",
    "is_lifecycle_managed",
    "is_safe_to_write",
    "is_user_owned",
    "is_vendored_file",
    "list_convention_docs",
    "list_skills",
    "read_manifest",
    "refresh",
    "registry_capabilities",
    "remove_item",
    "render_generated_set",
    "render_template",
    "required_capabilities",
    "reset",
    "resolve_coverage",
    "resolve_ref",
    "set_frontmatter_version",
    "specialist_spec",
    "stamp_vendored",
    "status",
    "templated_capabilities",
    "uninstall",
    "vendored_item",
    "wire_hooks",
    "write_manifest",
]
