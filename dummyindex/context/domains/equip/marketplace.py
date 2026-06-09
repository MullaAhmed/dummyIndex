"""Marketplace catalog model + parse/validate. Pure; no I/O.

A marketplace is a git repo with ``.claude-plugin/marketplace.json`` listing
plugins. This module turns a parsed-JSON dict into frozen dataclasses and
validates it at the boundary (CONVENTIONS §13). Fetching that JSON lives in
:mod:`.sources`; matching in :mod:`.discover`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import PluginSurface
from .errors import CatalogError

# Marketplace-entry keys that declare a code-running surface, mapped to the
# PluginSurface they imply. Inert surfaces (agents/skills/commands) need no
# special handling — their absence from this map is the point.
_CODE_SURFACE_KEYS: dict[str, str] = {
    "hooks": PluginSurface.HOOK.value,
    "mcpServers": PluginSurface.MCP.value,
    "lspServers": PluginSurface.LSP.value,
    "bin": PluginSurface.BIN.value,
}


@dataclass(frozen=True)
class SeedMarketplace:
    """A known starting-point marketplace.

    ``is_collection`` marks a loose agent/skill repo (e.g. ``anthropics/skills``)
    with no ``marketplace.json`` — its contents are vendored, not natively
    enabled. ``trusted`` marks an Anthropic-official source (auto-approvable even
    when it runs code).
    """

    name: str
    repo: str
    trusted: bool
    is_collection: bool = False


SEED_MARKETPLACES: tuple[SeedMarketplace, ...] = (
    SeedMarketplace("claude-plugins-official", "anthropics/claude-plugins-official", trusted=True),
    SeedMarketplace("claude-plugins-community", "anthropics/claude-plugins-community", trusted=False),
    SeedMarketplace("knowledge-work-plugins", "anthropics/knowledge-work-plugins", trusted=True),
    SeedMarketplace("agent-skills", "anthropics/skills", trusted=True, is_collection=True),
    SeedMarketplace("ecc", "affaan-m/ECC", trusted=False),
    SeedMarketplace("agency-agents", "msitarzewski/agency-agents", trusted=False),
)


@dataclass(frozen=True)
class PluginEntry:
    """One plugin row from a marketplace catalog.

    ``declared_surfaces`` holds the :class:`PluginSurface` values the entry
    declares a code-running surface for (hooks / MCP / LSP); empty means inert.
    """

    name: str
    description: str = ""
    version: str | None = None
    keywords: tuple[str, ...] = ()
    category: str | None = None
    declared_surfaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketplaceCatalog:
    """A parsed ``marketplace.json`` plus the trust/collection flags its seed
    carries (``parse_catalog`` is handed these — they are not in the JSON)."""

    name: str
    repo: str
    plugins: tuple[PluginEntry, ...] = ()
    trusted: bool = False
    is_collection: bool = False


def validate_catalog(data: Any) -> None:
    """Raise :class:`CatalogError` unless ``data`` is a catalog-shaped object."""
    if not isinstance(data, dict):
        raise CatalogError(
            f"marketplace.json must be a JSON object, got {type(data).__name__}"
        )
    if "plugins" not in data or not isinstance(data["plugins"], list):
        raise CatalogError("marketplace.json must contain a 'plugins' array")


def _surfaces(entry: dict[str, Any]) -> tuple[str, ...]:
    return tuple(surface for key, surface in _CODE_SURFACE_KEYS.items() if key in entry)


def _parse_entry(raw: Any) -> PluginEntry | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        return None
    kws = raw.get("keywords", [])
    keywords = tuple(str(k) for k in kws) if isinstance(kws, list) else ()
    cat = raw.get("category")
    ver = raw.get("version")
    return PluginEntry(
        name=raw["name"],
        description=str(raw.get("description", "")),
        version=str(ver) if isinstance(ver, str) else None,
        keywords=keywords,
        category=str(cat) if isinstance(cat, str) else None,
        declared_surfaces=_surfaces(raw),
    )


def parse_catalog(
    data: dict[str, Any],
    *,
    repo: str,
    trusted: bool = False,
    is_collection: bool = False,
) -> MarketplaceCatalog:
    """Validate then build a :class:`MarketplaceCatalog`.

    Malformed plugin entries are dropped (one bad row never crashes the parse);
    a missing 'plugins' array raises :class:`CatalogError`.

    The JSON-declared ``name`` is preserved deliberately — it is the identifier
    Claude Code resolves the marketplace by, so overriding it here would break
    native install. ``name`` is therefore **not** a trust signal: identity is
    enforced by the discovery orchestration (``cli/_equip_discover``), which
    drops a catalog that claims a reserved/duplicate name from the wrong repo,
    and ``trusted`` is set by the caller from the seed/discovery path, never from
    this JSON.
    """
    validate_catalog(data)
    name = data.get("name")
    plugins = tuple(
        e for e in (_parse_entry(p) for p in data["plugins"]) if e is not None
    )
    return MarketplaceCatalog(
        name=str(name) if isinstance(name, str) else repo,
        repo=repo,
        plugins=plugins,
        trusted=trusted,
        is_collection=is_collection,
    )
