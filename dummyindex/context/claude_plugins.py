"""Wire marketplaces + plugins into ``.claude/settings.json``.

Sibling of :mod:`.claude_settings` (and reuses its ``load_settings`` /
``write_settings``): native plugin state lives under two top-level keys —
``extraKnownMarketplaces`` (a marketplace the project wants available) and
``enabledPlugins`` (``"<plugin>@<marketplace>": true``). Same preserve-or-refuse
+ atomic-write discipline: we never overwrite a settings.json we cannot
round-trip (a malformed file raises :class:`MalformedSettingsError`).
"""
from __future__ import annotations

from pathlib import Path

from .claude_settings import load_settings, write_settings

_MARKETPLACES = "extraKnownMarketplaces"
_ENABLED = "enabledPlugins"


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
