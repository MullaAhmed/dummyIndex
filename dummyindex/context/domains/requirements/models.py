"""Frozen data for ``.context/config.toml``.

``extra`` holds unknown keys as ``(key, value)`` pairs in source order. A tuple
keeps the dataclass frozen and comparable. Values may be unhashable, so do not
hash these objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import SCHEMA_VERSION
from .enums import RequirementKind, RequirementStatus

Extra = tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class PluginRequirement:
    id: str
    version: str | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class SkillRequirement:
    name: str
    from_: str = "dummyindex"
    extra: Extra = ()


@dataclass(frozen=True)
class Requirements:
    schema_version: int = SCHEMA_VERSION
    min_version: str | None = None
    plugins: tuple[PluginRequirement, ...] = ()
    skills: tuple[SkillRequirement, ...] = ()
    require_native_adapters: bool = False
    extra: Extra = ()
    dummyindex_extra: Extra = ()
    equipment_extra: Extra = ()


@dataclass(frozen=True)
class RequirementRow:
    kind: RequirementKind
    name: str
    status: RequirementStatus
    reason: str = ""
    fix: str = ""
