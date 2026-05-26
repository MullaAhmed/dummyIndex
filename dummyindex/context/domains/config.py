"""Per-repo council preferences — `.context/config.json`.

v0.14 introduces a small, durable record of the user's onboarding choices:
scope of indexing, council mode/effort, model preference, whether the
SessionStart drift hook is wired, and any external doc roots. It stores
**choices only** — never API keys, tokens, or any secret. Keys live in the
user's Claude environment, not here.

Schema (``.context/config.json``):
    {
      "schema_version": 1,
      "scope": "repo",            // "repo" | "subdir" | "explicit"
      "scope_path": null,          // string when scope=="subdir", else null
      "mode": "standard",         // "light" | "standard" | "deep"
      "model": "sonnet-4.6",      // "opus-4.7" | "sonnet-4.6" | "haiku-4.5"
      "auto_refresh_hook": true,
      "external_docs": []          // list of doc-root strings
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

_E = TypeVar("_E", bound=Enum)

CONFIG_SCHEMA_VERSION = 1
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

    OPUS_4_7 = "opus-4.7"
    SONNET_4_6 = "sonnet-4.6"
    HAIKU_4_5 = "haiku-4.5"


DEFAULT_MODE = CouncilMode.STANDARD
DEFAULT_MODEL = ModelChoice.SONNET_4_6
DEFAULT_SCOPE = ScopeKind.REPO
DEFAULT_AUTO_REFRESH_HOOK = True


class ConfigError(ValueError):
    """Malformed config.json, unknown enum value, or wrong field type."""


@dataclass(frozen=True)
class Config:
    """The user's onboarding choices. Immutable — produce a new copy to change.

    ``scope``/``mode``/``model`` are enum members (the enums are ``(str, Enum)``
    so equality with plain strings still holds). Serialise with ``.value``.
    """

    schema_version: int
    scope: ScopeKind
    scope_path: Optional[str]
    mode: CouncilMode
    model: ModelChoice
    auto_refresh_hook: bool
    external_docs: tuple[str, ...] = ()

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
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Config":
        if not isinstance(payload, dict):
            raise ConfigError(f"config payload must be an object, got {type(payload).__name__}")

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

        schema_version = payload.get("schema_version", CONFIG_SCHEMA_VERSION)
        # bool is a subclass of int, so isinstance(True, int) is True — reject
        # booleans explicitly and require the exact supported version.
        if isinstance(schema_version, bool) or schema_version != CONFIG_SCHEMA_VERSION:
            raise ConfigError(f"config.schema_version must be {CONFIG_SCHEMA_VERSION}")

        return cls(
            schema_version=schema_version,
            scope=scope,
            scope_path=scope_path,
            mode=mode,
            model=model,
            auto_refresh_hook=auto_refresh_hook,
            external_docs=external_docs,
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


def default_config() -> Config:
    """The non-interactive ``--defaults`` baseline: repo scope, standard mode,
    the recommended model (sonnet-4.6), hook on, no external docs."""
    return Config(
        schema_version=CONFIG_SCHEMA_VERSION,
        scope=DEFAULT_SCOPE,
        scope_path=None,
        mode=DEFAULT_MODE,
        model=DEFAULT_MODEL,
        auto_refresh_hook=DEFAULT_AUTO_REFRESH_HOOK,
        external_docs=(),
    )


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
    dir). Pretty JSON + trailing newline, tmp + replace — like manifest.py."""
    context_dir = context_dir.resolve()
    out_path = context_dir / CONFIG_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = config.to_dict()
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return out_path
