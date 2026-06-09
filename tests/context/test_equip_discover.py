"""Capability matching + ranking of discovered plugins (pure)."""
from dummyindex.context.domains.equip import (
    Candidate,
    MarketplaceCatalog,
    PluginEntry,
    capabilities_for,
    match_candidates,
)


def _cat():
    return MarketplaceCatalog(
        name="official",
        repo="anthropics/claude-plugins-official",
        trusted=True,
        plugins=(
            PluginEntry(
                name="pg-tuner",
                description="Postgres performance",
                keywords=("database", "performance"),
            ),
            PluginEntry(
                name="rag-search",
                description="semantic vector search",
                keywords=("search", "rag"),
            ),
        ),
    )


def test_capabilities_for_maps_keywords():
    caps = capabilities_for(PluginEntry(name="x", keywords=("database", "performance")))
    assert "database" in caps and "performance" in caps


def test_auto_match_ranks_by_capability_overlap():
    out = match_candidates((_cat(),), needed_caps=("database",))
    assert isinstance(out[0], Candidate)
    assert out[0].plugin.name == "pg-tuner"
    assert "database" in out[0].capabilities
    assert out[0].trusted is True


def test_query_match_filters_by_token():
    out = match_candidates((_cat(),), query="vector search")
    assert [c.plugin.name for c in out] == ["rag-search"]


def test_no_signal_returns_empty():
    assert match_candidates((_cat(),)) == ()


def test_ranking_is_deterministic_by_score_then_name():
    cat = MarketplaceCatalog(
        name="m", repo="o/r",
        plugins=(
            PluginEntry(name="b-tool", keywords=("database",)),
            PluginEntry(name="a-tool", keywords=("database",)),
        ),
    )
    out = match_candidates((cat,), needed_caps=("database",))
    # equal score -> sorted by plugin name ascending
    assert [c.plugin.name for c in out] == ["a-tool", "b-tool"]
