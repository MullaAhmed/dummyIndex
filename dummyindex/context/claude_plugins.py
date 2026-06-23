"""Wire marketplaces + plugins into ``.claude/settings.json``.

Sibling of :mod:`.claude_settings` (and reuses its ``load_settings`` /
``write_settings``): native plugin state lives under two top-level keys —
``extraKnownMarketplaces`` (a marketplace the project wants available) and
``enabledPlugins`` (``"<plugin>@<marketplace>": true``). Same preserve-or-refuse
+ atomic-write discipline: we never overwrite a settings.json we cannot
round-trip (a malformed file raises :class:`MalformedSettingsError`).

Read side: :func:`list_marketplaces` / :func:`list_known_marketplaces` expose
the marketplaces Claude Code already knows (settings declarations + the native
``~/.claude/plugins/known_marketplaces.json`` registry) so discovery can
resolve them instead of erroring "not found in known marketplaces".
"""

from __future__ import annotations

import json
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

    Read-side and deliberately tolerant: an absent or malformed settings file
    (or an entry without a github repo) yields no declarations rather than an
    error — discovery enrichment must never fail because a settings file the
    user owns is broken (the write path still preserves-or-refuses).
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
