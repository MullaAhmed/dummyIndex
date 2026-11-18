"""Wire marketplaces + plugins into ``.claude/settings.json``.

State lives under ``extraKnownMarketplaces`` and ``enabledPlugins``
(``"<plugin>@<marketplace>": true``). Writes reuse :mod:`.claude_settings`'
preserve-or-refuse + atomic write: we never overwrite a settings.json we cannot
round-trip. The ``list_*`` readers expose marketplaces Claude Code already knows
(settings + native ``known_marketplaces.json``) so discovery can resolve them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .claude_settings import MalformedSettingsError, load_settings, write_settings

_MARKETPLACES = "extraKnownMarketplaces"
_ENABLED = "enabledPlugins"


@dataclass(frozen=True)
class DeclaredMarketplace:
    """One marketplace Claude Code already knows about, and where it lives.

    ``install_location`` / ``last_updated`` are populated only from the native
    ``known_marketplaces.json`` registry; settings declarations carry neither.
    """

    name: str
    repo: str
    install_location: str | None = None
    last_updated: str | None = None


def list_marketplaces(settings_path: Path) -> tuple[DeclaredMarketplace, ...]:
    """``extraKnownMarketplaces`` entries declared in one settings file.

    Tolerant: an absent or malformed file, or an entry without a github repo,
    yields no declarations, since discovery must never fail on a broken user file
    (the write path still preserves-or-refuses).
    """
    try:
        settings = load_settings(settings_path)
    except MalformedSettingsError:
        return ()
    block = settings.get(_MARKETPLACES)
    if not isinstance(block, dict):
        return ()
    return _declared_from_mapping(block)


def list_known_marketplaces(
    home: Path | None = None,
) -> tuple[DeclaredMarketplace, ...]:
    """Marketplaces registered in ``~/.claude/plugins/known_marketplaces.json``.

    Shape: ``{name: {source: {source: "github", repo}, installLocation,
    lastUpdated}}`` — the registry Claude Code's own plugin manager maintains.
    Tolerant of an absent/undecodable file (returns ``()``).
    """
    base = home if home is not None else Path.home()
    path = base / ".claude" / "plugins" / "known_marketplaces.json"
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, dict):
        return ()
    return _declared_from_mapping(data)


def _declared_from_mapping(block: dict) -> tuple[DeclaredMarketplace, ...]:
    """Build declarations from a ``{name: {source: {repo}, ...}}`` mapping."""
    out: list[DeclaredMarketplace] = []
    for name, entry in block.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        source = entry.get("source")
        repo = source.get("repo") if isinstance(source, dict) else None
        if not isinstance(repo, str) or "/" not in repo:
            continue
        location = entry.get("installLocation")
        updated = entry.get("lastUpdated")
        out.append(
            DeclaredMarketplace(
                name=name,
                repo=repo,
                install_location=location if isinstance(location, str) else None,
                last_updated=updated if isinstance(updated, str) else None,
            )
        )
    return tuple(out)


def add_marketplace(
    settings_path: Path, *, name: str, repo: str, ref: str | None = None
) -> bool:
    """Add a github marketplace under ``extraKnownMarketplaces``.

    Returns ``True`` iff a new/changed entry was written, ``False`` when an
    identical entry already existed (idempotent).
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(settings_path)
    block = settings.setdefault(_MARKETPLACES, {})
    source: dict[str, str] = {"source": "github", "repo": repo}
    if ref:
        source["ref"] = ref
    entry = {"source": source}
    if block.get(name) == entry:
        return False
    block[name] = entry
    write_settings(settings_path, settings)
    return True


def remove_marketplace(settings_path: Path, *, name: str) -> bool:
    """Drop a marketplace entry. Returns ``True`` iff something was removed."""
    if not settings_path.exists():
        return False
    settings = load_settings(settings_path)
    block = settings.get(_MARKETPLACES)
    if not isinstance(block, dict) or name not in block:
        return False
    block.pop(name)
    if not block:
        settings.pop(_MARKETPLACES, None)
    write_settings(settings_path, settings)
    return True


def enable_plugin(settings_path: Path, *, plugin: str, marketplace: str) -> bool:
    """Set ``enabledPlugins["<plugin>@<marketplace>"] = true``.

    Returns ``True`` iff a new entry was written, ``False`` when already enabled.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(settings_path)
    block = settings.setdefault(_ENABLED, {})
    key = f"{plugin}@{marketplace}"
    if block.get(key) is True:
        return False
    block[key] = True
    write_settings(settings_path, settings)
    return True


def disable_plugin(settings_path: Path, *, plugin: str, marketplace: str) -> bool:
    """Remove an ``enabledPlugins`` entry. Returns ``True`` iff one was removed."""
    if not settings_path.exists():
        return False
    settings = load_settings(settings_path)
    block = settings.get(_ENABLED)
    key = f"{plugin}@{marketplace}"
    if not isinstance(block, dict) or key not in block:
        return False
    block.pop(key)
    if not block:
        settings.pop(_ENABLED, None)
    write_settings(settings_path, settings)
    return True


class PluginRegistryError(Exception):
    """``installed_plugins.json`` exists but cannot be read or has a bad shape.

    Distinct from "not installed" (``None``) so callers can report ``unknown``.
    """


def installed_plugin_record(
    target: str, *, config_dir: Path, project_root: Path | None
) -> dict | None:
    """The first registry record for ``target`` that applies to this project.

    Reads ``<config_dir>/plugins/installed_plugins.json``. Shape:
    ``{"version": 2, "plugins": {"<plugin>@<mkt>": [{scope, projectPath?,
    installPath, version, ...}]}}``. User-scope records always apply. A
    project- or local-scope record applies only when its ``projectPath`` is
    ``project_root``, so another repo's install does not count here.

    Returns ``None`` when the file is absent or no record applies. Raises
    :class:`PluginRegistryError` when the file is unreadable or malformed.
    """
    path = config_dir / "plugins" / "installed_plugins.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginRegistryError(f"cannot read {path}: {exc}") from exc
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        raise PluginRegistryError(f"{path}: missing 'plugins' object")
    records = plugins.get(target)
    if records is None:
        return None
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise PluginRegistryError(f"{path}: malformed records for {target}")
    wanted = _normalized(project_root) if project_root is not None else None
    for record in records:
        if record.get("scope") not in ("project", "local"):
            return record
        project_path = record.get("projectPath")
        if (
            wanted is not None
            and isinstance(project_path, str)
            and _normalized(Path(project_path)) == wanted
        ):
            return record
    return None


def _normalized(path: Path) -> str:
    """Comparable form of a path: resolved, with Windows case/slashes folded."""
    return os.path.normcase(str(path.resolve()))
