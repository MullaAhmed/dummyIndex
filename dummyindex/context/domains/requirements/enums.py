"""Closed alphabets for requirement rows and skill origins."""

from __future__ import annotations

from enum import Enum


class RequirementStatus(str, Enum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    VERSION_MISMATCH = "version-mismatch"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class RequirementKind(str, Enum):
    PLUGIN = "plugin"
    SKILL = "skill"
    EQUIPMENT = "equipment"
    DUMMYINDEX = "dummyindex"


class SkillOrigin(str, Enum):
    DUMMYINDEX = "dummyindex"
    PLUGIN = "plugin"
    PROJECT = "project"
