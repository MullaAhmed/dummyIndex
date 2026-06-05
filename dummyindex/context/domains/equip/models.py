"""Frozen dataclasses for the equip flow + the generated-file sentinel.

Three data shapes, data only (behaviour lives in the sibling ``detect`` /
``render`` / ``manifest`` / ``safety`` modules):

- :class:`StackProfile` — the dominant stack label + the frameworks behind it,
  derived from ``.context/map/files.json``.
- :class:`EquipmentItem` — one tuned tool (agent / skill / command / hook) that
  equip rendered or recorded.
- :class:`EquipmentManifest` — the whole ``.context/equipment.json`` payload.

``GENERATED_SENTINEL`` is the marker every generated ``.md`` carries so a later
run can recognise its own output and safely regenerate it (never clobbering a
user-authored file at the same path). It is a markdown comment so it survives
in rendered prose without showing up as visible text — distinct from
``context.hooks.SENTINEL`` (which is shaped for settings.json command strings).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._constants import SCHEMA_VERSION
from .enums import EquipmentKind, EquipmentSource

# Marker embedded in every generated `.claude/**.md`. A markdown comment, so it
# is invisible in the rendered file yet greppable for the never-clobber check.
GENERATED_SENTINEL = "<!-- dummyindex:generated -->"

__all__ = [
    "GENERATED_SENTINEL",
    "SCHEMA_VERSION",
    "EquipmentItem",
    "EquipmentManifest",
    "StackProfile",
]


@dataclass(frozen=True)
class StackProfile:
    """The repo's dominant stack, derived from ``map/files.json``."""

    label: str                       # e.g. "python" / "typescript" / "generic"
    frameworks: tuple[str, ...] = ()  # detected framework labels, most-common first

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "frameworks": list(self.frameworks)}


@dataclass(frozen=True)
class EquipmentItem:
    """One tuned tool equip rendered (or recorded, for the format hook)."""

    kind: EquipmentKind
    name: str
    path: str                        # repo-relative POSIX path under .claude/
    source: EquipmentSource
    capabilities: tuple[str, ...] = ()
    grounded_in: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "source": self.source,
            "capabilities": list(self.capabilities),
            "grounded_in": list(self.grounded_in),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EquipmentItem":
        return cls(
            kind=EquipmentKind(data["kind"]),
            name=str(data["name"]),
            path=str(data["path"]),
            source=EquipmentSource(data["source"]),
            capabilities=tuple(str(c) for c in data.get("capabilities", [])),
            grounded_in=tuple(str(g) for g in data.get("grounded_in", [])),
        )


@dataclass(frozen=True)
class EquipmentManifest:
    """The ``.context/equipment.json`` payload."""

    schema_version: int
    items: tuple[EquipmentItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EquipmentManifest":
        raw_items = data.get("items", [])
        items = tuple(
            EquipmentItem.from_dict(i) for i in raw_items if isinstance(i, dict)
        )
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            items=items,
        )
