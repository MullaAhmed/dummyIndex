"""Local Claude Code plugin state — readers + the ``equip verify`` verb.

Subcommand-private sibling of ``discover.py``: everything here reads the
machine's existing plugin wiring (project/user settings declarations, the
native ``~/.claude/plugins`` registry, on-disk marketplace clones) so the
plugin-manager verbs can resolve marketplaces Claude Code already knows and
verify that an install actually loaded. Read-only — nothing in this module
writes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.claude_plugins import (
    DeclaredMarketplace,
    list_known_marketplaces,
    list_marketplaces,
)
from dummyindex.context.domains.equip import EquipError, MarketplaceCatalog, parse_catalog
from dummyindex.context.domains.equip.plugins.sources import CATALOG_PATH

from .common import pull_root


def declared_marketplaces(project_root: Path) -> tuple[DeclaredMarketplace, ...]:
    """Every marketplace this machine already declares, deduped by name.

    Sources, in precedence order: project ``.claude/settings.json``, project
    ``.claude/settings.local.json``, user ``~/.claude/settings.json``, and the
    native ``~/.claude/plugins/known_marketplaces.json`` registry.
    """
    seen: dict[str, DeclaredMarketplace] = {}
    for declared in (
        *list_marketplaces(project_root / ".claude" / "settings.json"),
        *list_marketplaces(project_root / ".claude" / "settings.local.json"),
        *list_marketplaces(Path.home() / ".claude" / "settings.json"),
        *list_known_marketplaces(),
    ):
        seen.setdefault(declared.name, declared)
    return tuple(seen.values())


def catalog_from_local_clone(declared: DeclaredMarketplace) -> MarketplaceCatalog | None:
    """Parse a declared marketplace's catalog from its on-disk clone, if any.

    Prefers the registry's ``installLocation``, falling back to the standard
    ``~/.claude/plugins/marketplaces/<name>/`` clone path. No network. Returns
    ``None`` when no readable catalog exists (the caller then falls back to a
    ``gh`` fetch of the declared repo).
    """
    candidates: list[Path] = []
    if declared.install_location:
        candidates.append(Path(declared.install_location))
    candidates.append(Path.home() / ".claude" / "plugins" / "marketplaces" / declared.name)
    for base in candidates:
        path = base / CATALOG_PATH
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            # Declared-but-not-seeded marketplaces are never auto-trusted.
            return parse_catalog(data, repo=declared.repo, trusted=False)
        except EquipError:
            continue
    return None


# ----- verb: verify ----------------------------------------------------------


def run_verify(rest: list[str]) -> int:
    """``equip verify <plugin>@<marketplace>`` — did the plugin actually load?

    Install only *declares* a plugin in settings; Claude Code loads it at
    session start via its native registry. This read-only check reports whether
    the target appears in ``~/.claude/plugins/installed_plugins.json`` (with
    scope + version), whether the marketplace clone exists on disk, and when
    the registry last updated it. Exit 0 when loaded; 1 when declared-but-not-
    loaded (with the actionable next step); 2 on usage errors.
    """
    _root, rest = pull_root(rest)  # tolerated for symmetry; verify is home-scoped
    target = next((a for a in rest if "@" in a and not a.startswith("--")), None)
    if target is None:
        print("error: `equip verify` requires <plugin>@<marketplace>", file=sys.stderr)
        return 2
    _plugin, _, marketplace = target.partition("@")
    if not _plugin or not marketplace:
        print("error: target must be <plugin>@<marketplace>", file=sys.stderr)
        return 2

    record = _installed_plugin_record(target)
    clone = Path.home() / ".claude" / "plugins" / "marketplaces" / marketplace
    known = {d.name: d for d in list_known_marketplaces()}.get(marketplace)

    print(f"equip verify: {target}")
    print(f"  marketplace clone: {'present' if clone.is_dir() else 'absent'} ({clone})")
    if known is not None and known.last_updated:
        print(f"  marketplace last updated: {known.last_updated}")
    if record is not None:
        scope = record.get("scope") or "-"
        version = record.get("version") or "-"
        print(f"  loaded: yes (scope {scope}, version {version})")
        return 0
    print("  loaded: NO — declared but not registered in installed_plugins.json")
    print(
        "  next: restart Claude Code (plugins load at session start), or open "
        "/plugin and refresh the marketplace, then re-run `equip verify`."
    )
    return 1


def _installed_plugin_record(target: str) -> dict | None:
    """The first registry record for ``target`` from installed_plugins.json.

    Shape: ``{"version": 2, "plugins": {"<plugin>@<mkt>": [{scope, installPath,
    version, gitCommitSha, ...}]}}``. Tolerant: an absent or undecodable
    registry reads as not-loaded.
    """
    path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    records = plugins.get(target) if isinstance(plugins, dict) else None
    if isinstance(records, list) and records and isinstance(records[0], dict):
        return records[0]
    return None
