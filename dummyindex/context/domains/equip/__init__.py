"""Templates-first equip: render a tuned ``.claude/`` toolkit from ``.context/``.

Public surface: detect the stack + formatter, render the shipped templates with
project values, guard every write so it never clobbers a user file, and record
the result in ``.context/equipment.json``. The CLI boundary
(``dummyindex/cli/equip/``) wires these together; this package holds the logic.
"""
from __future__ import annotations

from .constants import EQUIP_SENTINEL, SCHEMA_VERSION
from .lifecycle.hashing import content_hash
from .generate.proposal import extract_proposal_capabilities
from .generate.adopt import (
    Coverage,
    adopt_existing,
    adopt_spec_to_item,
    registry_capabilities,
    resolve_coverage,
)
from .plugins.blast_radius import BlastRadius, analyze_blast_radius
from .generate.catalog import build_catalog, profile_has_frontend
from .generate.detect import detect_stack
from .plugins.discover import Candidate, capabilities_for, match_candidates
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
    WireError,
)
from .lifecycle.evolve import apply_patch
from .wiring.hooks import wire_hooks
from .plugins.install_plan import InstallPlan, PlannedInstall, build_install_plan
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
from .lifecycle.manifest import EQUIPMENT_REL, read_manifest, write_manifest
from .lifecycle.remove import RemoveReport, remove_item
from .plugins.marketplace import (
    SEED_MARKETPLACES,
    MarketplaceCatalog,
    PluginEntry,
    SeedMarketplace,
    parse_catalog,
    validate_catalog,
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
from .generate.plan import render_generated_set
from .generate.render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
    list_convention_docs,
    render_template,
    set_frontmatter_version,
)
from .wiring.safety import is_safe_to_write
from .plugins.sources import (
    GitHubSearchResult,
    RunResult,
    Runner,
    ToolAvailability,
    available_tools,
    default_runner,
    fetch_catalog,
    fetch_file,
    search_github,
)
from .generate.specialists import (
    SPECIALIST_TEMPLATES,
    SpecialistTemplate,
    specialist_spec,
    templated_capabilities,
)
from .plugins.vendor import stamp_vendored, vendored_item

__all__ = [
    "EQUIPMENT_REL",
    "EQUIP_SENTINEL",
    "GENERATED_SENTINEL",
    "IMPLEMENTER_TEMPLATE",
    "REVIEWER_TEMPLATE",
    "SCHEMA_VERSION",
    "SEED_MARKETPLACES",
    "TESTER_TEMPLATE",
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
    "SourceError",
    "SpecialistTemplate",
    "StackProfile",
    "StatusReport",
    "TemplateError",
    "ToolAvailability",
    "TrustTier",
    "UninstallReport",
    "WireError",
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
    "classify_item",
    "content_hash",
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
    "read_manifest",
    "refresh",
    "registry_capabilities",
    "remove_item",
    "render_generated_set",
    "render_template",
    "reset",
    "resolve_coverage",
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
