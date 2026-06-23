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
        name="m",
        repo="o/r",
        plugins=(
            PluginEntry(name="b-tool", keywords=("database",)),
            PluginEntry(name="a-tool", keywords=("database",)),
        ),
    )
    out = match_candidates((cat,), needed_caps=("database",))
    # equal score -> sorted by plugin name ascending
    assert [c.plugin.name for c in out] == ["a-tool", "b-tool"]


# ----- capability tagging: whole-word, never substring (audit C4-P1) ---------


def test_capabilities_for_no_substring_false_positives():
    # 'orm' in 'brainstorming', 'auth' in 'author', 'ui' in 'guide'/'build',
    # 'db' in 'feedback', 'data' in 'metadata' — none of these may fire.
    entry = PluginEntry(
        name="superpowers",
        description="brainstorming guide for every author; build feedback metadata",
    )
    caps = capabilities_for(entry)
    assert "database" not in caps
    assert "security" not in caps
    assert "frontend" not in caps


def test_capabilities_for_design_audit_is_review_not_security():
    caps = capabilities_for(
        PluginEntry(name="impeccable", description="design audit toolkit")
    )
    assert "review" in caps
    assert "security" not in caps


def test_capabilities_for_whole_words_and_stems_still_match():
    caps = capabilities_for(
        PluginEntry(
            name="pg-helper",
            description="database migrations and query optimization",
            keywords=("sql",),
        )
    )
    assert "database" in caps
    assert "performance" in caps  # 'optimi' prefix stem catches 'optimization'


def test_capabilities_for_authentication_still_security():
    caps = capabilities_for(PluginEntry(name="x", description="authentication helper"))
    assert "security" in caps


# ----- query matching: stopwords + thresholds (audit C4-P1) -------------------


def test_query_stopwords_do_not_match():
    # 'design to code bridge': an entry whose only overlap is the stopword 'to'
    # must score 0 and be dropped.
    cat = MarketplaceCatalog(
        name="m",
        repo="o/r",
        plugins=(
            PluginEntry(name="brainstorming", description="how to think better"),
            PluginEntry(
                name="canvas-to-code", description="design to code bridge for figma"
            ),
        ),
    )
    out = match_candidates((cat,), query="design to code bridge")
    assert [c.plugin.name for c in out] == ["canvas-to-code"]


def test_multiword_query_requires_two_content_hits():
    cat = MarketplaceCatalog(
        name="m",
        repo="o/r",
        plugins=(
            PluginEntry(name="kitchen-sink", description="design everything"),  # 1 hit
            PluginEntry(
                name="figma-bridge", description="design to code bridge"
            ),  # >=2
        ),
    )
    out = match_candidates((cat,), query="design code bridge")
    assert [c.plugin.name for c in out] == ["figma-bridge"]


def test_name_hits_outrank_description_hits():
    cat = MarketplaceCatalog(
        name="m",
        repo="o/r",
        plugins=(
            PluginEntry(name="other-tool", description="vector store"),
            PluginEntry(name="vector-db", description="store things"),
        ),
    )
    out = match_candidates((cat,), query="vector")
    assert out[0].plugin.name == "vector-db"


# ----- force_repos: explicit --repo plugins always surface -------------------


def test_force_repos_keeps_zero_score_candidates_first():
    seeded = MarketplaceCatalog(
        name="big",
        repo="big/marketplace",
        plugins=(PluginEntry(name="generic-tool", keywords=("database",)),),
    )
    named = MarketplaceCatalog(
        name="tiny",
        repo="low/profile",
        plugins=(PluginEntry(name="obscure-plugin", description="nothing matchy"),),
    )
    out = match_candidates(
        (seeded, named),
        needed_caps=("database",),
        force_repos=frozenset({"low/profile"}),
    )
    assert out[0].plugin.name == "obscure-plugin"  # forced first, despite score 0
    assert {c.plugin.name for c in out} == {"obscure-plugin", "generic-tool"}
