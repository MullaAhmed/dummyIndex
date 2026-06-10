"""Marketplace catalog parsing + validation (pure)."""
import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip import (
    CatalogError,
    MarketplaceCatalog,
    SEED_MARKETPLACES,
    SeedMarketplace,
    parse_catalog,
    validate_catalog,
)

FIX = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def test_parse_official_catalog():
    cat = parse_catalog(
        _load("marketplace_official.json"),
        repo="anthropics/claude-plugins-official",
        trusted=True,
    )
    assert isinstance(cat, MarketplaceCatalog)
    assert cat.name == "claude-plugins-official"
    assert cat.trusted is True
    assert {p.name for p in cat.plugins} == {"code-review", "pg-tuner"}
    pg = next(p for p in cat.plugins if p.name == "pg-tuner")
    assert pg.version == "1.2.0"
    assert "hook" in pg.declared_surfaces and "mcp" in pg.declared_surfaces


def test_inert_plugin_declares_no_code_surface():
    cat = parse_catalog(_load("marketplace_community.json"), repo="anthropics/claude-plugins-community")
    rag = cat.plugins[0]
    assert rag.declared_surfaces == ()


def test_bin_key_maps_to_bin_surface():
    cat = parse_catalog(
        {"name": "m", "plugins": [{"name": "p", "bin": "./bin"}]}, repo="o/r"
    )
    assert "bin" in cat.plugins[0].declared_surfaces


def test_validate_rejects_missing_plugins():
    with pytest.raises(CatalogError):
        validate_catalog({"name": "x", "owner": {"name": "y"}})


def test_validate_rejects_non_object():
    with pytest.raises(CatalogError):
        validate_catalog([1, 2, 3])


def test_parse_ignores_malformed_plugin_entries():
    cat = parse_catalog(
        {"name": "m", "plugins": [{"no_name": True}, {"name": "ok"}]},
        repo="o/r",
    )
    assert {p.name for p in cat.plugins} == {"ok"}


def test_seed_marketplaces_include_official_and_collection():
    by_repo = {s.repo: s for s in SEED_MARKETPLACES}
    assert isinstance(SEED_MARKETPLACES[0], SeedMarketplace)
    official = by_repo["anthropics/claude-plugins-official"]
    assert official.trusted is True
    skills = by_repo["anthropics/skills"]
    assert skills.is_collection is True
