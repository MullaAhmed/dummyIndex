"""The viewer's tier-2/tier-3 payload (`graph-extras` island) and its limits.

Three contracts under test:

- **Bounded expansion index** — top-k symbol-graph neighbors per curated
  `symbolRef`, ranked by the seed's PageRank, hard-capped by a byte budget
  enforced in Python at embed time (never the full symbol graph).
- **Escape discipline** — the extras island is a second model/extraction
  -derived interpolation sink; both `<script>`-terminating sequences must
  survive a round trip inert, exactly like the scan island.
- **Graceful degradation** — no communities artifact means tier 2 stays
  hidden; a `symbolRef` that resolves nowhere simply doesn't expand.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dummyindex.context.output.viewer.extras import (
    EXPANSION_BUDGET_BYTES,
    EXPANSION_TOP_K,
    build_viewer_extras,
    load_viewer_extras,
)

from dummyindex.context.domains.features.constants import SCAN_SCHEMA_VERSION
from dummyindex.context.output.viewer import render_viewer_html

_ROOT = Path("/repo")

_SYMBOL_GRAPH = {
    "directed": False,
    "multigraph": False,
    "graph": {},
    "nodes": [
        {
            "id": "login",
            "label": "login()",
            "community": 0,
            "file_type": "code",
            "source_file": "/repo/app/auth.py",
            "source_location": "L1",
        },
        {
            "id": "verify",
            "label": "verify()",
            "community": 0,
            "file_type": "code",
            "source_file": "/repo/app/auth.py",
            "source_location": "L20",
        },
        {
            "id": "charge",
            "label": "charge()",
            "community": 1,
            "file_type": "code",
            "source_file": "/repo/app/billing.py",
            "source_location": "L5",
        },
        {
            "id": "refund",
            "label": "refund()",
            "community": 1,
            "file_type": "code",
            "source_file": "/repo/app/billing.py",
            "source_location": "L30",
        },
        {
            "id": "note",
            "label": "Log a user in.",
            "community": 0,
            "file_type": "rationale",
            "source_file": "/repo/app/auth.py",
            "source_location": "L2",
        },
    ],
    "links": [
        {
            "source": "login",
            "target": "verify",
            "_src": "login",
            "_tgt": "verify",
            "relation": "calls",
        },
        {
            "source": "login",
            "target": "charge",
            "_src": "login",
            "_tgt": "charge",
            "relation": "calls",
        },
        {
            "source": "refund",
            "target": "login",
            "_src": "refund",
            "_tgt": "login",
            "relation": "calls",
        },
        {
            "source": "note",
            "target": "login",
            "_src": "note",
            "_tgt": "login",
            "relation": "rationale_for",
        },
    ],
}

_CARDS = {
    "schema_version": 1,
    "communities": [
        {
            "slug": "auth-login",
            "size": 2,
            "feature": "auth",
            "summary": "Log users in.",
            "members": [
                {
                    "id": "login",
                    "label": "login()",
                    "score": 0.5,
                    "path": "app/auth.py:1",
                },
                {
                    "id": "verify",
                    "label": "verify()",
                    "score": 0.4,
                    "path": "app/auth.py:20",
                },
            ],
        },
        {
            "slug": "billing-charge",
            "size": 2,
            "members": [
                {
                    "id": "charge",
                    "label": "charge()",
                    "score": 0.9,
                    "path": "app/billing.py:5",
                },
                {
                    "id": "refund",
                    "label": "refund()",
                    "score": 0.1,
                    "path": "app/billing.py:30",
                },
            ],
        },
    ],
}

_RANK = {
    "schema_version": 1,
    "ranked": [
        {"id": "charge", "score": 0.9},
        {"id": "login", "score": 0.5},
        {"id": "verify", "score": 0.4},
    ],
}


def _scan(nodes: list[dict] | None = None) -> dict:
    return {
        "schema_version": SCAN_SCHEMA_VERSION,
        "project": {"name": "repo", "slug": "repo"},
        "stats": {"agents": 0, "models": 0, "tools": 0, "integrations": 0},
        "graph": {
            "nodes": nodes
            if nodes is not None
            else [
                {
                    "id": "auth",
                    "label": "Auth",
                    "kind": "service",
                    "symbolRef": "login",
                    "evidence": "EXTRACTED",
                },
                {
                    "id": "billing",
                    "label": "Billing",
                    "kind": "service",
                    "symbolRef": "charge",
                },
            ],
            "edges": [],
        },
        "confidence": "EXTRACTED",
    }


def _extras_island(html: str) -> dict:
    marker = '<script type="application/json" id="graph-extras">'
    start = html.index(marker) + len(marker)
    return json.loads(html[start : html.index("</script>", start)])


def _features_dir(tmp_path: Path, *, cards: dict | None, graph: dict | None) -> Path:
    context_dir = tmp_path / ".context"
    features_dir = context_dir / "features"
    features_dir.mkdir(parents=True)
    (context_dir / "meta.json").write_text(
        json.dumps({"root": str(_ROOT), "schema_version": 1}), encoding="utf-8"
    )
    if cards is not None:
        (features_dir / "graph-communities.json").write_text(
            json.dumps(cards), encoding="utf-8"
        )
    if graph is not None:
        (features_dir / "symbol-graph.json").write_text(
            json.dumps(graph), encoding="utf-8"
        )
    (features_dir / "seed-rank.json").write_text(json.dumps(_RANK), encoding="utf-8")
    return features_dir


# ----- the expansion index ----------------------------------------------------


@pytest.mark.unit
def test_expansion_lists_ranked_neighbors_with_citations() -> None:
    extras = build_viewer_extras(_scan(), _CARDS, _SYMBOL_GRAPH, _RANK, root=_ROOT)
    expansion = dict(extras.expansion)

    login = [n.to_dict() for n in expansion["login"]]
    # Ranked by seed-rank score desc, id breaking ties; the rationale node
    # never appears — it annotates a symbol, it is not one.
    assert [n["id"] for n in login] == ["charge", "verify", "refund"]
    assert login[0] == {
        "id": "charge",
        "label": "charge()",
        "relation": "calls",
        "dir": "out",
        "path": "app/billing.py:5",
    }
    assert login[2]["dir"] == "in"


@pytest.mark.unit
def test_expansion_caps_neighbors_at_top_k() -> None:
    nodes = [dict(_SYMBOL_GRAPH["nodes"][0])]
    links = []
    for i in range(EXPANSION_TOP_K + 4):
        nid = f"callee-{i:02d}"
        nodes.append(
            {
                "id": nid,
                "label": f"{nid}()",
                "community": 0,
                "file_type": "code",
                "source_file": "/repo/app/auth.py",
                "source_location": f"L{i + 2}",
            }
        )
        links.append(
            {
                "source": "login",
                "target": nid,
                "_src": "login",
                "_tgt": nid,
                "relation": "calls",
            }
        )
    graph = {"nodes": nodes, "links": links}
    scan = _scan(
        [{"id": "auth", "label": "Auth", "kind": "service", "symbolRef": "login"}]
    )

    extras = build_viewer_extras(scan, None, graph, None, root=_ROOT)
    ((ref, neighbors),) = extras.expansion
    assert ref == "login"
    assert len(neighbors) == EXPANSION_TOP_K


@pytest.mark.unit
def test_expansion_budget_truncates_whole_entries_by_rank() -> None:
    """The byte budget drops the lowest-ranked refs first, never a suffix mix."""
    assert EXPANSION_BUDGET_BYTES == 300 * 1024

    full = build_viewer_extras(_scan(), None, _SYMBOL_GRAPH, _RANK, root=_ROOT)
    assert [ref for ref, _ in full.expansion] == ["charge", "login"], (
        "charge outranks login in the seed shortlist"
    )
    full_bytes = len(
        json.dumps(
            full.to_dict()["expansion"], ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
    )

    trimmed = build_viewer_extras(
        _scan(), None, _SYMBOL_GRAPH, _RANK, root=_ROOT, budget_bytes=full_bytes - 1
    )
    kept = [ref for ref, _ in trimmed.expansion]
    assert kept == ["charge"], "truncation keeps the best-ranked prefix"
    trimmed_bytes = len(
        json.dumps(
            trimmed.to_dict()["expansion"], ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
    )
    assert trimmed_bytes <= full_bytes - 1


@pytest.mark.unit
def test_expansion_skips_refs_absent_from_the_symbol_graph() -> None:
    scan = _scan(
        [
            {"id": "a", "label": "A", "kind": "service", "symbolRef": "no-such-symbol"},
            {"id": "b", "label": "B", "kind": "service", "symbolRef": "auth-login"},
            {"id": "c", "label": "C", "kind": "service"},
        ]
    )
    extras = build_viewer_extras(scan, _CARDS, _SYMBOL_GRAPH, _RANK, root=_ROOT)
    # A community slug and an unknown id both degrade to "doesn't expand".
    assert extras.expansion == ()


# ----- community links --------------------------------------------------------


@pytest.mark.unit
def test_community_links_count_cross_community_call_volume() -> None:
    extras = build_viewer_extras(_scan(), _CARDS, _SYMBOL_GRAPH, _RANK, root=_ROOT)
    links = [link.to_dict() for link in extras.community_links]
    # login→verify is intra-community, so only the two cross-community calls
    # survive; output is sorted by (from, to).
    assert links == [
        {"from": "auth-login", "to": "billing-charge", "weight": 1},
        {"from": "billing-charge", "to": "auth-login", "weight": 1},
    ]


@pytest.mark.unit
def test_community_cards_survive_without_a_symbol_graph() -> None:
    extras = build_viewer_extras(_scan(), _CARDS, None, None, root=_ROOT)
    assert [c.slug for c in extras.communities] == ["auth-login", "billing-charge"]
    assert extras.community_links == ()
    assert extras.expansion == ()


# ----- rendering + escape discipline ------------------------------------------


@pytest.mark.integration
def test_render_inlines_extras_when_artifacts_exist(tmp_path: Path) -> None:
    features_dir = _features_dir(tmp_path, cards=_CARDS, graph=_SYMBOL_GRAPH)
    html = render_viewer_html(_scan(), features_dir=features_dir)
    extras = _extras_island(html)
    assert [c["slug"] for c in extras["communities"]] == [
        "auth-login",
        "billing-charge",
    ]
    assert "login" in extras["expansion"]


@pytest.mark.unit
def test_render_without_features_dir_leaves_the_empty_placeholder() -> None:
    extras = _extras_island(render_viewer_html(_scan()))
    assert extras == {"communities": [], "communityLinks": [], "expansion": {}}


@pytest.mark.integration
def test_missing_artifacts_degrade_to_the_empty_placeholder(tmp_path: Path) -> None:
    """No communities file → tier 2 hidden; nothing to expand → tier 3 inert."""
    features_dir = _features_dir(tmp_path, cards=None, graph=None)
    extras = _extras_island(render_viewer_html(_scan(), features_dir=features_dir))
    assert extras == {"communities": [], "communityLinks": [], "expansion": {}}


@pytest.mark.integration
def test_extras_island_neutralizes_hostile_strings(tmp_path: Path) -> None:
    """Symbol labels and card summaries are untrusted at render time.

    Both sequences that can terminate the island early — `</script` and
    `<!--` — must round-trip inert, exactly like the scan island.
    """
    graph = json.loads(json.dumps(_SYMBOL_GRAPH))
    graph["nodes"][2]["label"] = "</script><script>alert(1)</script>"
    cards = json.loads(json.dumps(_CARDS))
    cards["communities"][0]["summary"] = "<!-- oops"
    features_dir = _features_dir(tmp_path, cards=cards, graph=graph)

    html = render_viewer_html(_scan(), features_dir=features_dir)

    # Three closing tags total: the scan island, the extras island, and the
    # viewer's own code — none smuggled in from either payload.
    assert html.count("</script>") == 3
    extras = _extras_island(html)
    hostile = [n for n in extras["expansion"]["login"] if n["id"] == "charge"]
    assert hostile[0]["label"] == "</script><script>alert(1)</script>"
    assert extras["communities"][0]["summary"] == "<!-- oops"


@pytest.mark.integration
def test_extras_keep_the_viewer_offline(tmp_path: Path) -> None:
    features_dir = _features_dir(tmp_path, cards=_CARDS, graph=_SYMBOL_GRAPH)
    html = render_viewer_html(_scan(), features_dir=features_dir)
    html = html.replace("http://www.w3.org/2000/svg", "")
    for forbidden in ("http://", "https://", "fetch(", "<link", "XMLHttpRequest"):
        assert forbidden not in html, f"viewer must not reference {forbidden!r}"


@pytest.mark.integration
def test_load_viewer_extras_reads_the_artifacts_from_disk(tmp_path: Path) -> None:
    features_dir = _features_dir(tmp_path, cards=_CARDS, graph=_SYMBOL_GRAPH)
    extras = load_viewer_extras(_scan(), features_dir)
    assert [c.slug for c in extras.communities] == ["auth-login", "billing-charge"]
    assert dict(extras.expansion), "expansion index built from the on-disk graph"


# ----- the JS side of the closed alphabets ------------------------------------


@pytest.mark.unit
def test_viewer_js_folds_evidence_onto_a_closed_alphabet() -> None:
    """`evidence` is model-authored and lands in a class name — same fold
    discipline as `safeKind`, never raw interpolation."""
    from dummyindex.context.output.viewer.tiers import VIEWER_TIERS_JS

    assert "safeEvidence" in VIEWER_TIERS_JS
    assert '"ev-" + ev' in VIEWER_TIERS_JS, "class built from the folded value"
    assert "ev-" + '" + n.evidence' not in VIEWER_TIERS_JS, "never from raw input"


@pytest.mark.unit
def test_viewer_js_folds_expansion_relations_onto_a_closed_alphabet() -> None:
    from dummyindex.context.output.viewer.tiers import VIEWER_TIERS_JS

    assert "safeRelation" in VIEWER_TIERS_JS
    assert "Object.prototype.hasOwnProperty.call(EXPANSION" in VIEWER_TIERS_JS, (
        "a symbolRef of __proto__ must not reach the prototype chain"
    )


@pytest.mark.unit
def test_viewer_js_hides_tier_two_without_communities() -> None:
    from dummyindex.context.output.viewer.tiers import VIEWER_TIERS_JS

    assert "if (COMMUNITIES.length)" in VIEWER_TIERS_JS, (
        "the mode toggle only appears when the artifact produced cards"
    )
