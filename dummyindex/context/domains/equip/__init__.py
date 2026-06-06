"""Templates-first equip: render a tuned ``.claude/`` toolkit from ``.context/``.

Public surface: detect the stack + formatter, render the shipped templates with
project values, guard every write so it never clobbers a user file, and record
the result in ``.context/equipment.json``. The CLI boundary
(``dummyindex/cli/equip.py``) wires these together; this package holds the logic.
"""
from __future__ import annotations

from ._constants import EQUIP_SENTINEL, SCHEMA_VERSION
from ._hash import content_hash
from ._proposal import extract_proposal_capabilities
from .adopt import adopt_existing, adopt_spec_to_item, registry_capabilities
from .catalog import build_catalog
from .detect import detect_stack
from .enums import Capability, EquipmentKind, EquipmentSource, EquipVerb, ItemState
from .errors import EquipError, PatchError, ResetError, TemplateError
from .evolve import apply_patch
from .hookwire import wire_hooks
from .lifecycle import (
    RefreshReport,
    StatusReport,
    UninstallReport,
    classify_item,
    is_evolved,
    refresh,
    reset,
    status,
    uninstall,
)
from .manifest import EQUIPMENT_REL, read_manifest, write_manifest
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
from .plan import render_generated_set
from .render import (
    IMPLEMENTER_TEMPLATE,
    REVIEWER_TEMPLATE,
    TESTER_TEMPLATE,
    VERIFY_TEMPLATE,
    list_convention_docs,
    render_template,
    set_frontmatter_version,
)
from .safety import is_safe_to_write

__all__ = [
    "EQUIPMENT_REL",
    "EQUIP_SENTINEL",
    "GENERATED_SENTINEL",
    "IMPLEMENTER_TEMPLATE",
    "REVIEWER_TEMPLATE",
    "SCHEMA_VERSION",
    "TESTER_TEMPLATE",
    "VERIFY_TEMPLATE",
    "AdoptSpec",
    "Capability",
    "CatalogDecision",
    "EquipError",
    "EquipVerb",
    "EquipmentItem",
    "EquipmentKind",
    "EquipmentManifest",
    "EquipmentSource",
    "GenerateSpec",
    "HookSpec",
    "ItemState",
    "PatchError",
    "RefreshReport",
    "ResetError",
    "StackProfile",
    "StatusReport",
    "TemplateError",
    "UninstallReport",
    "adopt_existing",
    "adopt_spec_to_item",
    "apply_patch",
    "build_catalog",
    "classify_item",
    "content_hash",
    "detect_stack",
    "extract_proposal_capabilities",
    "is_evolved",
    "is_safe_to_write",
    "list_convention_docs",
    "read_manifest",
    "refresh",
    "registry_capabilities",
    "render_generated_set",
    "render_template",
    "reset",
    "set_frontmatter_version",
    "status",
    "uninstall",
    "wire_hooks",
    "write_manifest",
]
