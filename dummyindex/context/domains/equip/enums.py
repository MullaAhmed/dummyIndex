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


class EquipVerb(str, Enum):
    """The verbs ``dummyindex context equip <verb>`` dispatches on (spec §9).

    ``(str, Enum)`` so a raw CLI token round-trips through ``EquipVerb(token)``.
    ``APPLY`` is the default when the first token is not a verb (back-compat with
    bare ``equip`` and ``equip <path>``).
    """

    APPLY = "apply"
    ADD_SPECIALIST = "add-specialist"
    STATUS = "status"
    REFRESH = "refresh"
    RESET = "reset"
    UNINSTALL = "uninstall"
    PATCH = "patch"


class Capability(str, Enum):
    """The capability vocabulary persisted to ``equipment.json`` (spec §8).

    A fixed alphabet shared by the catalog (generated items), adoption (the
    registry map + stem inference), and C's task→equipment mapping. ``(str,
    Enum)`` keeps the JSON wire format identical to plain strings; the manifest
    loader stays tolerant of arbitrary strings on input.
    """

    IMPLEMENT = "implement"
    TEST = "test"
    VERIFY = "verify"
    REVIEW = "review"
    FORMAT = "format"
    DATABASE = "database"
    DATA = "data"
    SECURITY = "security"
    FRONTEND = "frontend"
    PERFORMANCE = "performance"
    DOCS = "docs"
    SEARCH = "search"


class ItemState(str, Enum):
    """A generated item's relationship to its recorded origin-hash baseline.

    The hash is the authority (spec §7): equal ⇒ ours to evolve, different ⇒
    the user owns it now, absent ⇒ gone. ``(str, Enum)`` so the value lands
    cleanly in ``equip status --json``.
    """

    PRISTINE = "pristine"            # disk hash == recorded origin_hash
    USER_MODIFIED = "user-modified"  # disk hash != origin_hash (skip forever)
    MISSING = "missing"              # file absent
