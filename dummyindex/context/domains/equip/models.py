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
    """The repo's dominant stack + its detected toolchain.

    ``label`` + ``frameworks`` come from ``map/files.json`` and the manifests;
    the eight toolchain fields are derived from the same raw-manifest token scan
    (no TOML/JSON parsing). Each ``*_command`` is the literal shell command a
    generated tool runs; ``None`` everywhere when nothing was detected, so equip
    still produces a usable (if untuned) toolkit on a fresh repo.
    """

    label: str                       # e.g. "python" / "typescript" / "generic"
    frameworks: tuple[str, ...] = ()  # detected framework labels, most-common first
    formatter: str | None = None      # "ruff" | "black" | "prettier"
    format_command: str | None = None
    test_runner: str | None = None    # "pytest" | "jest" | "vitest" | "go test" | ...
    test_command: str | None = None
    linter: str | None = None         # "ruff" | "eslint"
    lint_command: str | None = None
    type_checker: str | None = None   # "mypy" | "pyright" | "tsc"
    typecheck_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "frameworks": list(self.frameworks),
            "formatter": self.formatter,
            "format_command": self.format_command,
            "test_runner": self.test_runner,
            "test_command": self.test_command,
            "linter": self.linter,
            "lint_command": self.lint_command,
            "type_checker": self.type_checker,
            "typecheck_command": self.typecheck_command,
        }


@dataclass(frozen=True)
class EquipmentItem:
    """One tuned tool equip rendered (or recorded, for the format hook).

    The v2 fields (``subagent_type`` / ``version`` / ``origin_hash``) are
    optional and default to ``None`` so a v1 manifest entry (which lacks them)
    loads cleanly. ``subagent_type`` points the build skill at a dispatch
    target; ``version`` + ``origin_hash`` are recorded only on file-backed
    *generated* items and drive the hash-baselined lifecycle (refresh/reset/
    patch). They stay ``None`` for skills, hooks, and adopted registry agents.
    """

    kind: EquipmentKind
    name: str
    path: str                        # repo-relative POSIX path under .claude/
    source: EquipmentSource
    capabilities: tuple[str, ...] = ()
    grounded_in: tuple[str, ...] = ()
    subagent_type: str | None = None
    version: str | None = None
    origin_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "source": self.source,
            "capabilities": list(self.capabilities),
            "grounded_in": list(self.grounded_in),
            "subagent_type": self.subagent_type,
            "version": self.version,
            "origin_hash": self.origin_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EquipmentItem":
        sub = data.get("subagent_type")
        ver = data.get("version")
        oh = data.get("origin_hash")
        return cls(
            kind=EquipmentKind(data["kind"]),
            name=str(data["name"]),
            path=str(data["path"]),
            source=EquipmentSource(data["source"]),
            capabilities=tuple(str(c) for c in data.get("capabilities", [])),
            grounded_in=tuple(str(g) for g in data.get("grounded_in", [])),
            subagent_type=str(sub) if sub is not None else None,
            version=str(ver) if ver is not None else None,
            origin_hash=str(oh) if oh is not None else None,
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
