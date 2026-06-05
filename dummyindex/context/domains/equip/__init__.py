"""Templates-first equip: render a tuned ``.claude/`` toolkit from ``.context/``.

Public surface: detect the stack + formatter, render the shipped templates with
project values, guard every write so it never clobbers a user file, and record
the result in ``.context/equipment.json``. The CLI boundary
(``dummyindex/cli/equip.py``) wires these together; this package holds the logic.
"""
from __future__ import annotations

from ._constants import EQUIP_SENTINEL, SCHEMA_VERSION
from ._hash import content_hash
from .detect import detect_formatter, detect_stack
from .enums import EquipmentKind, EquipmentSource
from .errors import EquipError, TemplateError
from .manifest import EQUIPMENT_REL, read_manifest, write_manifest
from .models import (
    GENERATED_SENTINEL,
    EquipmentItem,
    EquipmentManifest,
    StackProfile,
)
from .plan import build_equipment_plan
from .render import (
    IMPLEMENTER_TEMPLATE,
    VERIFY_TEMPLATE,
    list_convention_docs,
    render_template,
)
from .safety import is_safe_to_write

__all__ = [
    "EQUIPMENT_REL",
    "EQUIP_SENTINEL",
    "GENERATED_SENTINEL",
    "IMPLEMENTER_TEMPLATE",
    "SCHEMA_VERSION",
    "VERIFY_TEMPLATE",
    "EquipError",
    "EquipmentItem",
    "EquipmentKind",
    "EquipmentManifest",
    "EquipmentSource",
    "StackProfile",
    "TemplateError",
    "build_equipment_plan",
    "content_hash",
    "detect_formatter",
    "detect_stack",
    "is_safe_to_write",
    "list_convention_docs",
    "read_manifest",
    "render_template",
    "write_manifest",
]
