"""Closed alphabets for the equip flow."""

from __future__ import annotations

from enum import Enum


class EquipmentKind(str, Enum):
    """The kind of tool an :class:`EquipmentItem` represents.

    ``PLUGIN`` is a natively-enabled marketplace plugin (often a skill+command
    bundle) — recorded as its own kind so schema consumers never misread it as
    a dispatchable agent. Legacy manifests that recorded plugins as ``agent``
    still load; they are normalized on their next re-record.
    """

    AGENT = "agent"
    SKILL = "skill"
    COMMAND = "command"
    HOOK = "hook"
    PLUGIN = "plugin"


class EquipmentSource(str, Enum):
    """How an :class:`EquipmentItem` came to exist in ``.claude/``."""

    GENERATED = "generated"
    INSTALLED = "installed"
    MARKETPLACE = "marketplace"  # native-enabled plugin (settings.json keys)
    VENDORED = "vendored"  # copied agent/skill file under .claude/


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
    REMOVE = "remove"
    UNINSTALL = "uninstall"
    PATCH = "patch"
    DISCOVER = "discover"
    INSTALL = "install"
    VERIFY = "verify"


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

    PRISTINE = "pristine"  # disk hash == recorded origin_hash
    USER_MODIFIED = "user-modified"  # disk hash != origin_hash (skip forever)
    MISSING = "missing"  # file absent
    ADOPTED = "adopted"  # manifest-only adoption (no baseline of ours)
    # Canary refinements of USER_MODIFIED, reachable only when an item carries
    # ``invariants`` and the hash differs (else USER_MODIFIED, exactly as today).
    # Both are *user-owned* — never auto-rewritten, re-baselined, or deleted.
    CUSTOMIZED = "customized"  # hash differs, every invariant preserved
    INVARIANT_BROKEN = "invariant-broken"  # hash differs, ≥1 invariant missing


class TrustTier(str, Enum):
    """Whether a marketplace source is auto-trusted (Anthropic-official)."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class InstallMechanism(str, Enum):
    """How a discovered candidate is wired: native enable vs vendored copy."""

    NATIVE = "native"
    VENDOR = "vendor"


class PluginSurface(str, Enum):
    """A capability surface a plugin can declare. The last four run code."""

    AGENT = "agent"
    SKILL = "skill"
    COMMAND = "command"
    HOOK = "hook"
    MCP = "mcp"
    LSP = "lsp"
    BIN = "bin"
