"""Per-repo council preferences — `.context/config.json`.

v0.14 introduces a small, durable record of the user's onboarding choices:
scope of indexing, council mode/effort, model preference, whether the
SessionStart drift hook is wired, and any external doc roots. It stores
**choices only** — never API keys, tokens, or any secret. Keys live in the
user's Claude environment, not here.

v2 (schema_version 2) refines two blunt dials and records the writer version:
``command_depths`` overrides council effort per command (``mode`` stays the
global fallback), ``wired`` replaces the ``wire_superpowers`` boolean with a
declarative list of plugins/skills to keep present, and ``dummyindex_version``
records the CLI that last wrote the file (descriptive, never a gate). A v1
config (``wire_superpowers``) is migrated in memory on read.

Schema (``.context/config.json``):
    {
      "schema_version": 2,
      "scope": "repo",            // "repo" | "subdir" | "explicit"
      "scope_path": null,          // string when scope=="subdir", else null
      "mode": "standard",         // "light" | "standard" | "deep"
      "model": "sonnet-4.6",      // "opus-4.8" | "sonnet-4.6" | "haiku-4.5"
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
      "dummyindex_version": "0.28.0"  // CLI that last wrote this file
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
from typing import Any, Optional, TypeVar

from ..default_plugins import WiredEntry, default_wired

_E = TypeVar("_E", bound=Enum)

CONFIG_SCHEMA_VERSION = 2
# Schema versions ``from_dict`` accepts. v1 is read-migrated in memory.
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
CONFIG_REL = Path("config.json")


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
    """Which model the council runs on — never silently defaulted."""

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
    scope_path: Optional[str]
    mode: CouncilMode
    model: ModelChoice
    auto_refresh_hook: bool
    external_docs: tuple[str, ...] = ()
    reconcile_exclude: tuple[str, ...] = ()
    command_depths: tuple[tuple[DepthCommand, CouncilMode], ...] = ()
    wired: tuple[WiredEntry, ...] = ()
    dummyindex_version: str = "unknown"

    def __post_init__(self) -> None:
        # Cross-field invariant: a subdir scope must name the subdir.
        if self.scope == ScopeKind.SUBDIR and not self.scope_path:
            raise ConfigError("config.scope_path is required when scope is 'subdir'")

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
            "dummyindex_version": self.dummyindex_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Config":
        if not isinstance(payload, dict):
            raise ConfigError(f"config payload must be an object, got {type(payload).__name__}")

        # Schema gate first: accept v1 (migrate) and v2; reject bool + 3+.
        schema_version = payload.get("schema_version", CONFIG_SCHEMA_VERSION)
        # bool is a subclass of int, so isinstance(True, int) is True — reject
        # booleans explicitly and require a supported version.
        if isinstance(schema_version, bool) or schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            allowed = ", ".join(str(v) for v in sorted(_SUPPORTED_SCHEMA_VERSIONS))
            raise ConfigError(f"config.schema_version must be one of: {allowed}")
        is_v1 = schema_version == 1

        scope = _require_enum(payload, "scope", ScopeKind)
        mode = _require_enum(payload, "mode", CouncilMode)
        model = _require_enum(payload, "model", ModelChoice)

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
            dummyindex_version=dummyindex_version,
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


def default_config() -> Config:
    """The non-interactive ``--defaults`` baseline: repo scope, standard mode,
    the recommended model (sonnet-4.6), hook on, no external docs. ``wired`` is
    seeded from ``default_plugins.DEFAULT_PLUGINS`` and the version is stamped."""
    return Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=DEFAULT_SCOPE,
        scope_path=None,
        mode=DEFAULT_MODE,
        model=DEFAULT_MODEL,
        auto_refresh_hook=DEFAULT_AUTO_REFRESH_HOOK,
        external_docs=(),
        command_depths=(),
        wired=default_wired(),
        dummyindex_version=current_dummyindex_version(),
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


def read_config(context_dir: Path) -> Optional[Config]:
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
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return out_path
