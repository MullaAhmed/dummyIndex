"""Closed alphabets for the equip flow."""
from __future__ import annotations

from enum import Enum


class EquipmentKind(str, Enum):
    """The kind of tool an :class:`EquipmentItem` represents."""

    AGENT = "agent"
    SKILL = "skill"
    COMMAND = "command"
    HOOK = "hook"


class EquipmentSource(str, Enum):
    """How an :class:`EquipmentItem` came to exist in ``.claude/``."""

    GENERATED = "generated"
    INSTALLED = "installed"
