"""Unit tests for `context.domains.graph_query` on a synthetic node-link fixture.

The fixture mirrors the real `features/symbol-graph.json` wire shape:
undirected node-link JSON where every link carries the true direction in
``_src``/``_tgt`` (networkx normalises ``source``/``target``), a ``relation``,
and a per-link ``source_file``/``source_location`` site. The fixture
deliberately scrambles ``source``/``target`` so a loader that reads them
instead of ``_src``/``_tgt`` fails these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.features.communities import rollup_communities
from dummyindex.context.domains.graph_query import (
    AmbiguousSymbolError,
    GraphArtifactInvalidError,
    GraphArtifactMissingError,
    SymbolGraph,
    UnknownSymbolError,
    callees_of,
    callers_of,
    community,
    dead_code,
    impact,
    load_symbol_graph,
    neighbors,
    path_between,
    render_json,
    render_markdown,
    resolve_symbol,
)


def _node(
    nid: str,
    label: str,
    comm: int,
    file: str,
    loc: str,
    *,
    file_type: str = "code",
) -> dict:
    return {
        "id": nid,
        "label": label,
        "norm_label": label.lower(),
        "community": comm,
        "file_type": file_type,
        "source_file": file,
        "source_location": loc,
    }


def _link(src: str, tgt: str, relation: str, file: str, loc: str) -> dict:
    return {
        # True direction lives in _src/_tgt; source/target are scrambled on
        # purpose (the undirected node-link export normalises them).
        "_src": src,
        "_tgt": tgt,
        "source": tgt,
        "target": src,
        "relation": relation,
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": file,
        "source_location": loc,
        "weight": 1.0,
    }


def write_graph(root: Path) -> Path:
    """Write the synthetic artifact under ``root/.context`` and return that dir."""
    app = str(root / "src" / "app.py")
    lib = str(root / "src" / "lib.py")
    other = str(root / "src" / "other.py")
    isl = str(root / "src" / "island.py")
    nodes = [
        _node("app_py", "app.py", 0, app, "L1"),
        _node("app_main", "main()", 0, app, "L10"),
        _node("app_helper", "helper()", 0, app, "L20"),
        _node("app_sub", "Sub", 0, app, "L40"),
        _node("app_sub_run", ".run()", 0, app, "L42"),
        _node(
            "app_rationale_10",
            "Entry point of the app.",
            0,
            app,
            "L10",
            file_type="rationale",
        ),
        _node("other_util", "util()", 0, other, "L8"),
        _node("lib_py", "lib.py", 1, lib, "L1"),
        _node("lib_util", "util()", 1, lib, "L5"),
        _node("lib_dead", "orphan()", 1, lib, "L50"),
        _node("lib_base", "Base", 1, lib, "L60"),
        _node("island", "island()", 2, isl, "L1"),
    ]
    links = [
        _link("app_main", "app_helper", "calls", app, "L12"),
        _link("app_main", "lib_util", "calls", app, "L14"),
        _link("app_helper", "lib_base", "uses", app, "L22"),
        _link("app_sub", "lib_base", "inherits", app, "L40"),
        _link("app_py", "app_main", "contains", app, "L10"),
        _link("app_py", "app_helper", "contains", app, "L20"),
        _link("app_sub", "app_sub_run", "method", app, "L42"),
        _link("app_py", "lib_py", "imports_from", app, "L2"),
        _link("app_rationale_10", "app_main", "rationale_for", app, "L10"),
    ]
    payload = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "hyperedges": [],
        "nodes": nodes,
        "links": links,
    }
    context_dir = root / ".context"
    (context_dir / "features").mkdir(parents=True)
    (context_dir / "features" / "symbol-graph.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return context_dir


@pytest.fixture()
def graph(tmp_path: Path) -> SymbolGraph:
    return load_symbol_graph(write_graph(tmp_path))


# ----- loading --------------------------------------------------------------


@pytest.mark.unit
def test_missing_artifact_raises_typed_error(tmp_path: Path) -> None:
    with pytest.raises(GraphArtifactMissingError) as exc:
        load_symbol_graph(tmp_path / ".context")
    assert "symbol-graph.json" in str(exc.value)


@pytest.mark.unit
def test_invalid_json_raises_typed_error(tmp_path: Path) -> None:
    features = tmp_path / ".context" / "features"
    features.mkdir(parents=True)
    (features / "symbol-graph.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(GraphArtifactInvalidError):
        load_symbol_graph(tmp_path / ".context")


@pytest.mark.unit
def test_non_node_link_payload_raises_typed_error(tmp_path: Path) -> None:
    features = tmp_path / ".context" / "features"
    features.mkdir(parents=True)
    (features / "symbol-graph.json").write_text('{"nodes": 3}', encoding="utf-8")
    with pytest.raises(GraphArtifactInvalidError):
        load_symbol_graph(tmp_path / ".context")


# ----- symbol resolution ----------------------------------------------------


@pytest.mark.unit
def test_resolve_exact_node_id(graph: SymbolGraph) -> None:
    assert resolve_symbol(graph, "app_main") == "app_main"


@pytest.mark.unit
def test_resolve_unique_bare_name(graph: SymbolGraph) -> None:
    assert resolve_symbol(graph, "helper") == "app_helper"
    # Method labels (".run()") resolve by bare method name.
    assert resolve_symbol(graph, "run") == "app_sub_run"
    # Module labels keep their full stem ("app.py"), never a ".py" bare name.
    assert resolve_symbol(graph, "app.py") == "app_py"


@pytest.mark.unit
def test_resolve_bare_name_is_case_insensitive(graph: SymbolGraph) -> None:
    assert resolve_symbol(graph, "SUB") == "app_sub"


@pytest.mark.unit
def test_resolve_ambiguous_bare_name_lists_candidates(graph: SymbolGraph) -> None:
    with pytest.raises(AmbiguousSymbolError) as exc:
        resolve_symbol(graph, "util")
    assert exc.value.total == 2
    joined = "\n".join(exc.value.candidates)
    assert "lib_util" in joined
    assert "other_util" in joined
    assert "src/lib.py:L5" in joined  # candidates are cited


@pytest.mark.unit
def test_resolve_path_name_suffix(graph: SymbolGraph) -> None:
    assert resolve_symbol(graph, "lib.py:util") == "lib_util"
    assert resolve_symbol(graph, "src/other.py:util") == "other_util"


@pytest.mark.unit
def test_resolve_unambiguous_prefix(graph: SymbolGraph) -> None:
    assert resolve_symbol(graph, "app_hel") == "app_helper"


@pytest.mark.unit
def test_resolve_unknown_symbol_raises(graph: SymbolGraph) -> None:
    with pytest.raises(UnknownSymbolError):
        resolve_symbol(graph, "does_not_exist")


@pytest.mark.unit
def test_resolve_never_returns_a_rationale_node(graph: SymbolGraph) -> None:
    # "Entry point of the app." would bare-match "entry point of the app."
    # only via the rationale node — rationale nodes are not lookup targets.
    with pytest.raises(UnknownSymbolError):
        resolve_symbol(graph, "Entry point of the app.")


# ----- callers-of / callees-of ----------------------------------------------


@pytest.mark.unit
def test_callers_of_cites_definition_and_call_site(graph: SymbolGraph) -> None:
    result = callers_of(graph, "lib_util")
    assert result.verb == "callers-of"
    assert [r.node_id for r in result.rows] == ["app_main"]
    row = result.rows[0]
    assert row.citation == "src/app.py:L10"  # caller's definition site
    assert row.site == "src/app.py:L14"  # the call site itself
    assert row.relation == "calls"
    assert row.direction == "in"
    assert row.depth == 1
    # Docstring from the co-located rationale_for node.
    assert row.docstring == "Entry point of the app."


@pytest.mark.unit
def test_callees_of_orders_rows_deterministically(graph: SymbolGraph) -> None:
    result = callees_of(graph, "app_main")
    assert [r.node_id for r in result.rows] == ["app_helper", "lib_util"]
    assert all(r.direction == "out" for r in result.rows)
    assert result.subject is not None
    assert result.subject.node_id == "app_main"
    assert result.subject.docstring == "Entry point of the app."


@pytest.mark.unit
def test_callers_of_zero_callers_is_a_valid_answer(graph: SymbolGraph) -> None:
    result = callers_of(graph, "app_main")
    assert result.rows == ()
    assert result.total == 0
    assert not result.truncated


# ----- impact ---------------------------------------------------------------


@pytest.mark.unit
def test_impact_walks_reverse_dependency_edges(graph: SymbolGraph) -> None:
    result = impact(graph, "lib_base", depth=2)
    got = [(r.node_id, r.depth, r.relation) for r in result.rows]
    assert got == [
        ("app_helper", 1, "uses"),
        ("app_sub", 1, "inherits"),
        ("app_main", 2, "calls"),
    ]


@pytest.mark.unit
def test_impact_depth_one_stops_early(graph: SymbolGraph) -> None:
    result = impact(graph, "lib_base", depth=1)
    assert [r.node_id for r in result.rows] == ["app_helper", "app_sub"]


@pytest.mark.unit
def test_impact_limit_truncates_and_reports_total(graph: SymbolGraph) -> None:
    result = impact(graph, "lib_base", depth=2, limit=1)
    assert len(result.rows) == 1
    assert result.total == 3
    assert result.truncated


# ----- path -----------------------------------------------------------------


@pytest.mark.unit
def test_path_annotates_relations_and_directions(graph: SymbolGraph) -> None:
    result = path_between(graph, "app_helper", "lib_py")
    assert [r.node_id for r in result.rows] == ["app_helper", "app_py", "lib_py"]
    hops = [(r.relation, r.direction) for r in result.rows]
    assert hops[0] == (None, None)  # the starting node has no inbound hop
    assert hops[1] == ("contains", "in")  # app_py contains app_helper
    assert hops[2] == ("imports_from", "out")  # app_py imports_from lib_py


@pytest.mark.unit
def test_path_none_returns_empty_rows_with_note(graph: SymbolGraph) -> None:
    result = path_between(graph, "island", "app_main")
    assert result.rows == ()
    assert result.total == 0
    assert result.note is not None
    assert "no path" in result.note


@pytest.mark.unit
def test_path_never_routes_through_rationale_edges(graph: SymbolGraph) -> None:
    # The only edge touching the rationale node is rationale_for; a path to
    # it must not exist.
    result = path_between(graph, "app_rationale_10", "app_main")
    assert result.rows == ()


# ----- neighbors ------------------------------------------------------------


@pytest.mark.unit
def test_neighbors_one_hop_both_directions(graph: SymbolGraph) -> None:
    result = neighbors(graph, "lib_base", hops=1)
    got = {(r.node_id, r.relation, r.direction) for r in result.rows}
    assert got == {
        ("app_helper", "uses", "in"),
        ("app_sub", "inherits", "in"),
    }


@pytest.mark.unit
def test_neighbors_two_hops_excludes_rationale_nodes(graph: SymbolGraph) -> None:
    result = neighbors(graph, "lib_base", hops=2)
    ids = {r.node_id for r in result.rows}
    assert ids == {"app_helper", "app_sub", "app_main", "app_py", "app_sub_run"}
    assert "app_rationale_10" not in ids
    depths = {r.node_id: r.depth for r in result.rows}
    assert depths["app_helper"] == 1
    assert depths["app_main"] == 2


# ----- dead-code ------------------------------------------------------------


@pytest.mark.unit
def test_dead_code_is_purely_graph_driven(graph: SymbolGraph) -> None:
    result = dead_code(graph)
    ids = [r.node_id for r in result.rows]
    # Zero incoming calls/uses/imports_from/inherits; contains/method/
    # rationale_for never count as usage. Ordered by file, then line.
    assert ids == [
        "app_py",
        "app_main",
        "app_sub",
        "app_sub_run",
        "island",
        "lib_dead",
        "other_util",
    ]
    # Alive nodes and rationale nodes never appear.
    assert "app_helper" not in ids
    assert "lib_util" not in ids
    assert "lib_base" not in ids
    assert "lib_py" not in ids
    assert "app_rationale_10" not in ids


@pytest.mark.unit
def test_dead_code_limit_truncates(graph: SymbolGraph) -> None:
    result = dead_code(graph, limit=2)
    assert len(result.rows) == 2
    assert result.total == 7
    assert result.truncated


# ----- community ------------------------------------------------------------


@pytest.mark.unit
def test_community_by_id_ranks_by_dependency_degree(graph: SymbolGraph) -> None:
    result = community(graph, "0")
    ids = [r.node_id for r in result.rows]
    # app_helper and app_main tie on degree 2 → id order; then degree 1; then 0.
    assert ids == [
        "app_helper",
        "app_main",
        "app_py",
        "app_sub",
        "app_sub_run",
        "other_util",
    ]
    assert result.note is not None
    assert "community 0" in result.note


@pytest.mark.unit
def test_community_by_symbol_name_falls_back_to_its_community(
    graph: SymbolGraph,
) -> None:
    result = community(graph, "helper")
    assert {r.node_id for r in result.rows} >= {"app_helper", "app_main"}


@pytest.mark.unit
def test_community_by_slug_reads_graph_communities_artifact(
    tmp_path: Path,
) -> None:
    """The slug resolves against the *real* A2 wire shape.

    ``rollup_communities`` deliberately drops the partition int from the
    card, so the reader must recover it from the card's members — an
    artifact fixture with a synthetic ``community`` key would false-green
    a reader that only probes for an int that never rides the wire.
    """
    context_dir = write_graph(tmp_path)
    graph = load_symbol_graph(context_dir)
    payload = rollup_communities(
        graph.nodes,
        {1: ["lib_py", "lib_util", "lib_dead", "lib_base"]},
        {"lib_util": 0.9, "lib_base": 0.5},
        owner_of_symbol={"lib_util": "lib-core"},
    ).to_dict()
    card = payload["communities"][0]
    assert card["slug"] == "lib-core-util"
    assert "community" not in card  # the partition int never rides the wire
    (context_dir / "features" / "graph-communities.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    result = community(graph, "lib-core-util")
    assert {r.node_id for r in result.rows} == {
        "lib_base",
        "lib_dead",
        "lib_py",
        "lib_util",
    }
    assert result.note is not None
    assert "community 1" in result.note


@pytest.mark.unit
def test_community_slug_skips_stale_members(tmp_path: Path) -> None:
    """A member id that no longer exists in the graph never breaks the card."""
    context_dir = write_graph(tmp_path)
    card = {
        "slug": "lib-core",
        "size": 2,
        "members": [
            {"id": "renamed_away", "label": "gone()", "score": 1.0},
            {"id": "lib_util", "label": "util()", "score": 0.5},
        ],
    }
    (context_dir / "features" / "graph-communities.json").write_text(
        json.dumps({"communities": [card]}), encoding="utf-8"
    )
    result = community(load_symbol_graph(context_dir), "lib-core")
    assert {r.node_id for r in result.rows} == {
        "lib_base",
        "lib_dead",
        "lib_py",
        "lib_util",
    }


@pytest.mark.unit
def test_community_unknown_id_is_empty(graph: SymbolGraph) -> None:
    result = community(graph, "99")
    assert result.rows == ()
    assert result.total == 0


# ----- wire format + rendering ----------------------------------------------


@pytest.mark.unit
def test_to_dict_optional_means_absent(graph: SymbolGraph) -> None:
    result = callers_of(graph, "lib_util")
    payload = result.to_dict()
    row = payload["rows"][0]
    assert row["relation"] == "calls"
    assert "docstring" in row  # app_main has one
    dead = dead_code(graph).to_dict()
    first = dead["rows"][0]
    # No relation/direction/site/docstring on a dead-code row → keys absent.
    assert "relation" not in first
    assert "direction" not in first
    assert "site" not in first
    assert "note" not in callers_of(graph, "lib_util").to_dict()


@pytest.mark.unit
def test_render_json_round_trips(graph: SymbolGraph) -> None:
    result = callees_of(graph, "app_main")
    payload = json.loads(render_json(result))
    assert payload["verb"] == "callees-of"
    assert payload["subject"]["node_id"] == "app_main"
    assert [r["node_id"] for r in payload["rows"]] == ["app_helper", "lib_util"]


@pytest.mark.unit
def test_render_markdown_cites_every_row(graph: SymbolGraph) -> None:
    text = render_markdown(callers_of(graph, "lib_util"))
    assert "# graph callers-of" in text
    assert "src/app.py:L10" in text  # definition citation
    assert "src/app.py:L14" in text  # call site
    assert "Entry point of the app." in text  # attached docstring
