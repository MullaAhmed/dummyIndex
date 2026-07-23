"""Per-repo council preferences — `.context/config.json`.

v0.14 introduces a small, durable record of the user's onboarding choices:
scope of indexing, council mode/effort, model preference, whether the
managed Claude Code hooks are wired, and any external doc roots. It stores
**choices only** — never API keys, tokens, or any secret. Keys live in the
user's Claude environment, not here.

v2 (schema_version 2) refines two blunt dials and records the writer version:
``command_depths`` overrides council effort per command (``mode`` stays the
global fallback), ``wired`` replaces the ``wire_superpowers`` boolean with a
declarative list of plugins/skills to keep present, and ``dummyindex_version``
records the CLI that last wrote the file (descriptive, never a gate). A v1
config (``wire_superpowers``) is migrated in memory on read.

v3 (schema_version 3) adds the PreToolUse doc-guard dials: ``doc_guard_enabled``
(default **on everywhere**, so the guard engages even before a config exists) and
``doc_guard_allow`` (a glob allowlist exempting a legitimately-published
planning-doc path). A v2 config is migrated in memory on read by adding both keys
at their defaults, preserving every existing choice. The guard's ``Write`` hot
path reads these through :func:`read_doc_guard_settings` (a cheap, tolerant read),
never the full :class:`Config`.

v4 (schema_version 4) adds ``default_plugins_enabled`` as a three-state default
plugin policy: ``true`` opts a Claude-enabled repo into the reviewed defaults,
``false`` is the durable all-defaults opt-out, and ``null`` records that defaults
were not applicable to a Codex-only baseline yet. Older configs are migrated
without conflating an empty explicit opt-out with that canonical Codex baseline.

Schema (``.context/config.json``):
    {
      "schema_version": 4,
      "scope": "repo",            // "repo" | "subdir" | "explicit"
      "scope_path": null,          // string when scope=="subdir", else null
      "mode": "standard",         // "light" | "standard" | "deep"
      "model": "sonnet-4.6",      // "current" | "opus-4.8" | "sonnet-4.6" | "haiku-4.5"
      "auto_refresh_hook": true,
      "external_docs": [],         // list of doc-root strings
      "reconcile_exclude": [],     // fnmatch globs hidden from reconcile/drift
      "command_depths": {           // per-command council effort override
        "reconcile": "light"        // keys: ingest|reconcile|audit|build
      },
      "wired": [                    // declarative plugins/skills to keep present
        { "kind": "plugin", "target": "superpowers@claude-plugins-official",
          "version": null }
      ],
      "default_plugins_enabled": true, // true | false | null (Codex-only)
      "dummyindex_version": "0.31.0",  // CLI that last wrote this file
      "doc_guard_enabled": true,       // PreToolUse write-guard on/off
      "doc_guard_allow": []            // globs exempt from the guard
    }

I/O mirrors ``context/build/manifest.py``: ``write_config`` is atomic
(tmp + replace), pretty JSON with a trailing newline; ``read_config``
returns ``None`` when absent and raises ``ConfigError`` on malformed
input. The functions take the ``.context/`` directory itself, exactly as
``manifest.py`` takes ``context_dir``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from ..default_plugins import WiredEntry, WiredKind, default_wired

_E = TypeVar("_E", bound=Enum)

CONFIG_SCHEMA_VERSION = 4
# Schema versions ``from_dict`` accepts. v1-v3 are read-migrated in memory;
# v4 carries explicit default-plugin applicability/opt-out state.
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4})
CONFIG_REL = Path("config.json")

# Renamed ``model`` values, read-migrated in memory so configs written before a
# rename keep loading (the opus model value was ``opus-4.7`` before the 4.8
# bump). Maps an obsolete value -> its current :class:`ModelChoice` value. The
# user's choice is preserved (opus stays opus); only the version label moves.
_LEGACY_MODEL_VALUES = {"opus-4.7": "opus-4.8"}


class ScopeKind(str, Enum):
    """What the user pointed the index at."""

    REPO = "repo"
    SUBDIR = "subdir"
    EXPLICIT = "explicit"


class CouncilMode(str, Enum):
    """How much synthesis effort the council spends."""

    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


class ModelChoice(str, Enum):
    """Which model the council runs on — never silently defaulted.

    ``current`` delegates model selection to the active host session. It is
    primarily the Codex choice; the versioned entries preserve Claude Code's
    existing per-subagent model selection.
    """

    CURRENT = "current"
    OPUS_4_8 = "opus-4.8"
    SONNET_4_6 = "sonnet-4.6"
    HAIKU_4_5 = "haiku-4.5"


class DepthCommand(str, Enum):
    """A command whose council/build effort can be tuned per-command.

    A closed alphabet (the keys of ``Config.command_depths``). ``rebuild`` is
    deliberately absent — it is deterministic (no council stage to consume a
    depth), so a ``--depth`` on it would silently no-op.
    """

    INGEST = "ingest"
    RECONCILE = "reconcile"
    AUDIT = "audit"
    BUILD = "build"


DEFAULT_MODE = CouncilMode.STANDARD
DEFAULT_MODEL = ModelChoice.SONNET_4_6
DEFAULT_SCOPE = ScopeKind.REPO
DEFAULT_AUTO_REFRESH_HOOK = True
# v3 PreToolUse doc-guard. Default **on everywhere** (engages even before a
# config exists); ``doc_guard_allow`` is a glob allowlist a repo sets to exempt
# a legitimately-published planning-doc path from the guard.
DEFAULT_DOC_GUARD_ENABLED = True
DEFAULT_DOC_GUARD_ALLOW: tuple[str, ...] = ()


class ConfigError(ValueError):
    """Malformed config.json, unknown enum value, or wrong field type."""


def current_dummyindex_version() -> str:
    """The installed dummyindex CLI version, or ``"unknown"``.

    The single source of the ``importlib.metadata`` read so callers don't
    duplicate the dance (mirrors ``cli/init.py``'s version lookup). Used to
    stamp ``config.dummyindex_version`` on every write and to populate it on a
    v1→v2 migration.
    """
    try:
        from importlib.metadata import version

        return version("dummyindex")
    except Exception:
        return "unknown"


@dataclass(frozen=True)
class Config:
    """The user's onboarding choices. Immutable — produce a new copy to change.

    ``scope``/``mode``/``model`` are enum members (the enums are ``(str, Enum)``
    so equality with plain strings still holds). Serialise with ``.value``.
    ``command_depths`` is a tuple of ``(DepthCommand, CouncilMode)`` pairs
    serialised as a JSON object; ``wired`` is a tuple of :class:`WiredEntry`.
    """

    schema_version: int
    scope: ScopeKind
    scope_path: str | None
    mode: CouncilMode
    model: ModelChoice
    auto_refresh_hook: bool
    external_docs: tuple[str, ...] = ()
    reconcile_exclude: tuple[str, ...] = ()
    command_depths: tuple[tuple[DepthCommand, CouncilMode], ...] = ()
    wired: tuple[WiredEntry, ...] = ()
    default_plugins_enabled: bool | None = None
    dummyindex_version: str = "unknown"
    doc_guard_enabled: bool = DEFAULT_DOC_GUARD_ENABLED
    doc_guard_allow: tuple[str, ...] = DEFAULT_DOC_GUARD_ALLOW

    def __post_init__(self) -> None:
        # Cross-field invariant: a subdir scope must name the subdir.
        if self.scope == ScopeKind.SUBDIR and not self.scope_path:
            raise ConfigError("config.scope_path is required when scope is 'subdir'")
        if self.default_plugins_enabled is not None and not isinstance(
            self.default_plugins_enabled, bool
        ):
            raise ConfigError("config.default_plugins_enabled must be boolean or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scope": self.scope.value,
            "scope_path": self.scope_path,
            "mode": self.mode.value,
            "model": self.model.value,
            "auto_refresh_hook": self.auto_refresh_hook,
            "external_docs": list(self.external_docs),
            "reconcile_exclude": list(self.reconcile_exclude),
            "command_depths": {
                cmd.value: depth.value for cmd, depth in self.command_depths
            },
            "wired": [entry.to_dict() for entry in self.wired],
            "default_plugins_enabled": self.default_plugins_enabled,
            "dummyindex_version": self.dummyindex_version,
            "doc_guard_enabled": self.doc_guard_enabled,
            "doc_guard_allow": list(self.doc_guard_allow),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Config:
        if not isinstance(payload, dict):
            raise ConfigError(
                f"config payload must be an object, got {type(payload).__name__}"
            )

        # Schema gate first: accept v1-v3 for migration; reject bool/future.
        schema_version = payload.get("schema_version", CONFIG_SCHEMA_VERSION)
        # bool is a subclass of int, so isinstance(True, int) is True — reject
        # booleans explicitly and require a supported version.
        if (
            isinstance(schema_version, bool)
            or schema_version not in _SUPPORTED_SCHEMA_VERSIONS
        ):
            allowed = ", ".join(str(v) for v in sorted(_SUPPORTED_SCHEMA_VERSIONS))
            raise ConfigError(f"config.schema_version must be one of: {allowed}")
        is_v1 = schema_version == 1

        scope = _require_enum(payload, "scope", ScopeKind)
        mode = _require_enum(payload, "mode", CouncilMode)
        # Read-migrate a renamed model value before validation so a config
        # written before the rename keeps loading (preserves the choice).
        raw_model = payload.get("model")
        model_value = _LEGACY_MODEL_VALUES.get(raw_model, raw_model)
        model = _require_enum({"model": model_value}, "model", ModelChoice)

        scope_path = payload.get("scope_path")
        if scope_path is not None and not isinstance(scope_path, str):
            raise ConfigError("config.scope_path must be a string or null")

        auto_refresh_hook = payload.get("auto_refresh_hook", DEFAULT_AUTO_REFRESH_HOOK)
        if not isinstance(auto_refresh_hook, bool):
            raise ConfigError("config.auto_refresh_hook must be a boolean")

        raw_docs = payload.get("external_docs", ())
        if isinstance(raw_docs, (str, bytes)) or not _is_iterable(raw_docs):
            raise ConfigError("config.external_docs must be a list of strings")
        external_docs: tuple[str, ...] = tuple(str(d) for d in raw_docs)

        # Optional since a later schema rev; absent → empty (back-compat).
        raw_excl = payload.get("reconcile_exclude", ())
        if isinstance(raw_excl, (str, bytes)) or not _is_iterable(raw_excl):
            raise ConfigError("config.reconcile_exclude must be a list of strings")
        reconcile_exclude: tuple[str, ...] = tuple(str(g) for g in raw_excl)

        command_depths = _parse_command_depths(payload.get("command_depths"))
        wired = _parse_wired(payload, is_v1=is_v1)
        default_plugins_enabled = _parse_default_plugins_enabled(
            payload,
            schema_version=schema_version,
            wired=wired,
        )

        # v3 doc-guard. Absent (a v1/v2 config) → defaults (value-preserving
        # migration adds these keys without disturbing existing choices).
        doc_guard_enabled = payload.get("doc_guard_enabled", DEFAULT_DOC_GUARD_ENABLED)
        if not isinstance(doc_guard_enabled, bool):
            raise ConfigError("config.doc_guard_enabled must be a boolean")
        raw_allow = payload.get("doc_guard_allow", DEFAULT_DOC_GUARD_ALLOW)
        if isinstance(raw_allow, (str, bytes)) or not _is_iterable(raw_allow):
            raise ConfigError("config.doc_guard_allow must be a list of strings")
        doc_guard_allow: tuple[str, ...] = tuple(str(g) for g in raw_allow)

        # Descriptive, never a gate: tolerate any value. v1→v2 migration (and an
        # absent field) populate the current version.
        raw_version = payload.get("dummyindex_version")
        if raw_version is None:
            dummyindex_version = current_dummyindex_version()
        else:
            dummyindex_version = str(raw_version)

        return cls(
            schema_version=CONFIG_SCHEMA_VERSION,
            scope=scope,
            scope_path=scope_path,
            mode=mode,
            model=model,
            auto_refresh_hook=auto_refresh_hook,
            external_docs=external_docs,
            reconcile_exclude=reconcile_exclude,
            command_depths=command_depths,
            wired=wired,
            default_plugins_enabled=default_plugins_enabled,
            dummyindex_version=dummyindex_version,
            doc_guard_enabled=doc_guard_enabled,
            doc_guard_allow=doc_guard_allow,
        )


def _is_iterable(value: Any) -> bool:
    try:
        iter(value)
    except TypeError:
        return False
    return True


def _require_enum(payload: dict[str, Any], key: str, enum_cls: type[_E]) -> _E:
    """Validate ``payload[key]`` is a member of ``enum_cls``; return the member."""
    raw = payload.get(key)
    try:
        return enum_cls(raw)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ConfigError(f"config.{key}={raw!r} is not one of: {allowed}") from exc


def _coerce_enum(raw: Any, key: str, enum_cls: type[_E]) -> _E:
    """Validate ``raw`` is a member of ``enum_cls`` or raise ``ConfigError``.

    Mirrors :func:`_require_enum` but takes the value directly (the command_depths
    keys/values are not top-level payload keys).
    """
    try:
        return enum_cls(raw)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum_cls)
        raise ConfigError(f"config.{key}={raw!r} is not one of: {allowed}") from exc


def _parse_command_depths(
    raw: Any,
) -> tuple[tuple[DepthCommand, CouncilMode], ...]:
    """Parse the ``command_depths`` JSON object into ordered enum pairs.

    Absent/empty → ``()``. An unknown command key raises ``ConfigError`` naming
    the valid commands (the ``DepthCommand`` ``ValueError`` path); an invalid
    depth value raises ``ConfigError`` naming the allowed depths.
    """
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ConfigError("config.command_depths must be an object")
    pairs: list[tuple[DepthCommand, CouncilMode]] = []
    for key, value in raw.items():
        command = _coerce_enum(key, "command_depths", DepthCommand)
        depth = _coerce_enum(value, f"command_depths.{key}", CouncilMode)
        pairs.append((command, depth))
    return tuple(pairs)


def _parse_wired(payload: dict[str, Any], *, is_v1: bool) -> tuple[WiredEntry, ...]:
    """Parse ``wired`` (v2) or migrate ``wire_superpowers`` (v1) in memory.

    v1 migration: ``wire_superpowers: true`` → :func:`default_wired`; ``false``
    → empty. v2: an absent/empty ``wired`` → ``()``; each entry is validated at
    the :meth:`WiredEntry.from_dict` boundary, re-raised as ``ConfigError``.
    """
    if is_v1 and "wired" not in payload:
        wire_superpowers = payload.get("wire_superpowers", True)
        if not isinstance(wire_superpowers, bool):
            raise ConfigError("config.wire_superpowers must be a boolean")
        return default_wired() if wire_superpowers else ()

    raw = payload.get("wired", ())
    if isinstance(raw, (str, bytes)) or not _is_iterable(raw):
        raise ConfigError("config.wired must be a list of entries")
    try:
        return tuple(WiredEntry.from_dict(e) for e in raw)
    except ValueError as exc:
        raise ConfigError(f"config.wired is invalid: {exc}") from exc


def _parse_default_plugins_enabled(
    payload: dict[str, Any],
    *,
    schema_version: int,
    wired: tuple[WiredEntry, ...],
) -> bool | None:
    """Read v4 default state or infer it conservatively for a legacy config.

    v1 carried an explicit ``wire_superpowers`` boolean, so that value maps
    directly to the all-default state. In v2/v3, a non-empty ``wired`` ledger
    meant defaults were enabled and an empty ledger meant an explicit opt-out.
    The one exception is the exact host-aware Codex baseline introduced before
    v4: its empty ledger meant "not applicable", not "disabled".
    """
    if schema_version == CONFIG_SCHEMA_VERSION:
        if "default_plugins_enabled" not in payload:
            raise ConfigError("config.default_plugins_enabled is required in schema 4")
        raw = payload["default_plugins_enabled"]
        if raw is not None and not isinstance(raw, bool):
            raise ConfigError("config.default_plugins_enabled must be boolean or null")
        return raw

    if schema_version == 1 and "wired" not in payload:
        # _parse_wired validated this field before this helper is reached.
        return payload.get("wire_superpowers", True)
    if not wired and _is_legacy_codex_baseline(payload):
        return None
    return bool(wired)


def _is_legacy_codex_baseline(payload: dict[str, Any]) -> bool:
    """Whether a v2/v3 payload is the canonical, unmodified Codex baseline."""
    return (
        payload.get("scope") == ScopeKind.REPO.value
        and payload.get("scope_path") is None
        and payload.get("mode") == DEFAULT_MODE.value
        and payload.get("model") == ModelChoice.CURRENT.value
        and payload.get("auto_refresh_hook") is False
        and payload.get("external_docs", []) == []
        and payload.get("reconcile_exclude", []) == []
        and payload.get("command_depths", {}) == {}
        and payload.get("doc_guard_enabled", DEFAULT_DOC_GUARD_ENABLED) is True
        and payload.get("doc_guard_allow", []) == []
    )


def default_config(*, platform: str = "claude") -> Config:
    """Return the non-interactive ``--defaults`` baseline for one host set.

    Every baseline uses repo scope, standard mode, and no external docs.
    Claude uses the recommended ``sonnet-4.6`` model with managed hooks on;
    Codex uses the active-session ``current`` model with Claude hooks off; a
    both-host config uses ``current`` while recording that Claude's hooks are
    on. Claude and both-host configs seed ``wired`` from
    ``default_plugins.DEFAULT_PLUGINS``; Codex-only has no Claude plugin
    declarations. The installed dummyindex version is stamped.

    ``platform`` is validated here so every non-interactive writer (installer
    and onboarding CLI) shares the same closed host alphabet and values.
    """
    if platform not in {"claude", "codex", "both"}:
        raise ConfigError(f"platform={platform!r} is not one of: claude, codex, both")
    portable_model = platform in {"codex", "both"}
    return Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=DEFAULT_SCOPE,
        scope_path=None,
        mode=DEFAULT_MODE,
        model=ModelChoice.CURRENT if portable_model else DEFAULT_MODEL,
        auto_refresh_hook=platform != "codex",
        external_docs=(),
        command_depths=(),
        wired=() if platform == "codex" else default_wired(),
        default_plugins_enabled=None if platform == "codex" else True,
        dummyindex_version=current_dummyindex_version(),
        doc_guard_enabled=DEFAULT_DOC_GUARD_ENABLED,
        doc_guard_allow=DEFAULT_DOC_GUARD_ALLOW,
    )


def resolve_depth(
    context_dir: Path, command: DepthCommand, depth_flag: str | None
) -> CouncilMode:
    """Resolve the council mode for ``command``. Single seam for every caller.

    Precedence: ``depth_flag`` → ``config.command_depths[command]`` →
    ``config.mode`` → ``CouncilMode.STANDARD``. An invalid ``depth_flag`` raises
    ``ConfigError`` listing the allowed depths. ``audit/workspace.py`` delegates
    here so per-command depth is resolved one way for every command.
    """
    if depth_flag is not None:
        return _coerce_enum(depth_flag, "depth", CouncilMode)

    config = read_config(context_dir)
    if config is None:
        return CouncilMode.STANDARD
    for cmd, depth in config.command_depths:
        if cmd == command:
            return depth
    return config.mode


def read_config(context_dir: Path) -> Config | None:
    """Return the config if it exists; ``None`` otherwise.

    ``context_dir`` is the ``.context/`` directory itself (mirrors
    ``manifest.read_manifest``). Raises ``ConfigError`` on malformed JSON
    or a schema the loader rejects.
    """
    path = context_dir / CONFIG_REL
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"could not read config.json: {exc}") from exc
    return Config.from_dict(raw)


def read_doc_guard_settings(context_dir: Path) -> tuple[bool, tuple[str, ...]]:
    """Cheaply read the doc-guard settings off disk for the ``Write`` hook hot path.

    Returns ``(doc_guard_enabled, doc_guard_allow)``. Reads **only** these two keys
    straight from ``config.json``; it never builds a full :class:`Config` (which
    would parse ``wired``/``command_depths`` via :class:`WiredEntry`) and it never
    raises. An absent ``.context/``, an absent/unreadable/malformed ``config.json``,
    a non-object payload, or a missing/mistyped key all fall back to the defaults
    ``(True, ())`` — default-on means the guard engages even before ``.context/``
    exists. The strict :meth:`Config.from_dict` path is the source of truth for a
    well-formed config; this accessor is a deliberately tolerant fast read.
    """
    default = (DEFAULT_DOC_GUARD_ENABLED, DEFAULT_DOC_GUARD_ALLOW)
    try:
        raw = json.loads((context_dir / CONFIG_REL).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return default
        enabled = raw.get("doc_guard_enabled", DEFAULT_DOC_GUARD_ENABLED)
        if not isinstance(enabled, bool):
            enabled = DEFAULT_DOC_GUARD_ENABLED
        raw_allow = raw.get("doc_guard_allow", DEFAULT_DOC_GUARD_ALLOW)
        if isinstance(raw_allow, (str, bytes)) or not _is_iterable(raw_allow):
            return (enabled, DEFAULT_DOC_GUARD_ALLOW)
        return (enabled, tuple(str(g) for g in raw_allow))
    except Exception:
        return default


def _needs_migration(raw: dict[str, Any]) -> bool:
    """Whether an on-disk config dict is stale and should be re-persisted.

    True when its schema predates the current one or its ``model`` is a renamed
    legacy value. Deliberately *not* triggered by a mere ``dummyindex_version``
    difference — that would churn ``config.json`` (and its git diff) on every
    ``install``. Only a substantive schema/value migration rewrites the file.
    """
    schema_version = raw.get("schema_version", CONFIG_SCHEMA_VERSION)
    if isinstance(schema_version, int) and not isinstance(schema_version, bool):
        if schema_version < CONFIG_SCHEMA_VERSION:
            return True
    return raw.get("model") in _LEGACY_MODEL_VALUES


def migrate_config_in_place(context_dir: Path) -> bool:
    """Migrate a loadable-but-stale ``config.json`` on disk; return whether it
    moved. A value-preserving round-trip (read -> normalise -> write), *not* a
    clobber: every user choice survives, only a stale schema/renamed value is
    upgraded. Absent config, a current config, or a genuinely unreadable one
    (unknown enum / malformed JSON) are all left untouched and report ``False``.

    Used by the installer so ``/dummyindex-update`` heals existing repos whose
    config predates a rename, instead of leaving them with an unreadable file.
    """
    path = context_dir / CONFIG_REL
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(raw, dict) or not _needs_migration(raw):
        return False
    try:
        config = Config.from_dict(raw)
    except ConfigError:
        return False
    write_config(context_dir, config)
    return True


def reconcile_wired_with_equipment(context_dir: Path) -> bool:
    """Fold equip-installed plugins into ``config.wired``; return whether it moved.

    The ``wired`` ledger is *declared intent* and ``equipment.json`` is the
    *render manifest* — the two are reconcilable on the shared
    ``<plugin>@<marketplace>`` key (``equip install`` writes both). But a v1→v2
    migration seeds ``wired`` from :func:`default_wired` alone, and an older CLI
    equipped plugins without the ``config.wired`` write-back — either way a plugin
    that is genuinely installed (recorded in ``equipment.json``, enabled in
    ``settings.json``) can be missing from ``config.wired``, so a later install or
    reconcile no longer treats it as wanted. This heals that drift: every
    ``kind=plugin`` equipment item whose name is absent from ``wired`` is appended
    as a :class:`WiredEntry`, preserving the existing order and entries.

    Best-effort and idempotent: an absent config is left untouched (never
    materialise a seeded config as a side effect), an absent/unreadable
    ``equipment.json`` contributes nothing, and a run that adds nothing rewrites
    nothing (no git churn) — each case reports ``False``.
    """
    from dataclasses import replace

    try:
        config = read_config(context_dir)
    except ConfigError:
        return False
    if config is None:
        return False

    try:
        from .equip.enums import EquipmentKind
        from .equip.errors import EquipError
        from .equip.lifecycle.manifest import read_manifest
    except ImportError:  # pragma: no cover - defensive
        return False
    try:
        manifest = read_manifest(context_dir)
    except EquipError:
        return False

    existing = {entry.target for entry in config.wired}
    added: list[WiredEntry] = []
    for item in manifest.items:
        if item.kind != EquipmentKind.PLUGIN or item.name in existing:
            continue
        existing.add(item.name)
        added.append(
            WiredEntry(kind=WiredKind.PLUGIN, target=item.name, version=item.version)
        )
    if not added:
        return False

    write_config(context_dir, replace(config, wired=config.wired + tuple(added)))
    return True


def reconcile_default_plugins(context_dir: Path, *, platform: str) -> bool:
    """Reconcile reviewed defaults before a Claude-enabled wiring pass.

    ``platform=codex`` is deliberately mutation-free. For ``claude``/``both``,
    an explicit ``False`` remains a durable opt-out; ``None`` transitions from
    the not-applicable Codex baseline to opted-in, and ``True`` stays opted-in.
    Missing entries from :func:`default_wired` are appended after every existing
    custom entry, preserving ledger order. No-op runs do not rewrite the file.

    A malformed config raises :class:`ConfigError` before any write so callers
    can warn and fail closed instead of silently falling back to defaults.
    """
    from dataclasses import replace

    if platform not in {"claude", "codex", "both"}:
        raise ConfigError(f"platform={platform!r} is not one of: claude, codex, both")
    if platform == "codex":
        return False

    config = read_config(context_dir)
    if config is None or config.default_plugins_enabled is False:
        return False

    existing = {entry.target for entry in config.wired}
    missing = tuple(entry for entry in default_wired() if entry.target not in existing)
    enabled = True
    if not missing and config.default_plugins_enabled is enabled:
        return False

    write_config(
        context_dir,
        replace(
            config,
            wired=config.wired + missing,
            default_plugins_enabled=enabled,
        ),
    )
    return True


def write_config(context_dir: Path, config: Config) -> Path:
    """Atomically write ``config.json`` under ``context_dir`` (the ``.context/``
    dir). Pretty JSON + trailing newline, tmp + replace — like manifest.py.

    Every write stamps ``dummyindex_version`` with the current CLI version so the
    field always reflects the last *config* writer (descriptive, not a gate).
    """
    from dataclasses import replace

    context_dir = context_dir.resolve()
    out_path = context_dir / CONFIG_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stamped = replace(config, dummyindex_version=current_dummyindex_version())
    payload = stamped.to_dict()
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    tmp.replace(out_path)
    return out_path
