"""Marketplace catalog parsing + validation (pure)."""

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip import (
    SEED_MARKETPLACES,
    CatalogError,
    MarketplaceCatalog,
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
    cat = parse_catalog(
        _load("marketplace_community.json"), repo="anthropics/claude-plugins-community"
    )
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
    agency = by_repo["msitarzewski/agency-agents"]
    assert agency.is_collection is True


# ----- seed catalog verified against docs/sources/installable-sources.md -----
# (2026-06-13 verification pass: existence, marketplace.json presence, trust.)


def test_seed_drift_fixed_anthropics_skills_is_native_now():
    # anthropics/skills ships .claude-plugin/marketplace.json — the old
    # is_collection flag was stale.
    by_repo = {s.repo: s for s in SEED_MARKETPLACES}
    skills = by_repo["anthropics/skills"]
    assert skills.is_collection is False
    assert skills.trusted is True


def test_seed_drift_fixed_agency_agents_is_collection():
    # msitarzewski/agency-agents has NO marketplace.json — it is a loose agent
    # collection and must be vendored, never natively enabled.
    by_repo = {s.repo: s for s in SEED_MARKETPLACES}
    assert by_repo["msitarzewski/agency-agents"].is_collection is True


def test_seed_includes_verified_high_value_sources():
    by_repo = {s.repo: s for s in SEED_MARKETPLACES}
    expected_native_untrusted = (
        "obra/superpowers",
        "obra/superpowers-marketplace",
        "wshobson/agents",
        "addyosmani/agent-skills",
        "trailofbits/skills",
        "kepano/obsidian-skills",
    )
    for repo in expected_native_untrusted:
        seed = by_repo[repo]
        assert seed.trusted is False, repo
        assert seed.is_collection is False, repo
    claude_code = by_repo["anthropics/claude-code"]
    assert claude_code.trusted is True
    assert claude_code.is_collection is False
    vercel = by_repo["vercel-labs/agent-skills"]
    assert vercel.trusted is True
    assert vercel.is_collection is True  # loose skills collection (skills.sh)


def test_seed_trust_is_strictly_anthropic_or_vercel():
    for seed in SEED_MARKETPLACES:
        owner = seed.repo.split("/")[0]
        if seed.trusted:
            assert owner in {"anthropics", "vercel-labs"}, seed.repo
        else:
            assert owner not in {"anthropics"} or seed.repo == (
                "anthropics/claude-plugins-community"  # community submissions
            )


def test_seed_names_and_repos_unique():
    names = [s.name for s in SEED_MARKETPLACES]
    repos = [s.repo for s in SEED_MARKETPLACES]
    assert len(names) == len(set(names))
    assert len(repos) == len(set(repos))
