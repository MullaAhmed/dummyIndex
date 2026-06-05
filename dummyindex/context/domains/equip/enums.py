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


class ItemState(str, Enum):
    """A generated item's relationship to its recorded origin-hash baseline.

    The hash is the authority (spec §7): equal ⇒ ours to evolve, different ⇒
    the user owns it now, absent ⇒ gone. ``(str, Enum)`` so the value lands
    cleanly in ``equip status --json``.
    """

    PRISTINE = "pristine"            # disk hash == recorded origin_hash
    USER_MODIFIED = "user-modified"  # disk hash != origin_hash (skip forever)
    MISSING = "missing"              # file absent
