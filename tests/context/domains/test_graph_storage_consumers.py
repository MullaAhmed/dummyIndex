"""Every disk consumer sees the same complete graph after storage migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.features import (
    rebuild_features_graph,
    scaffold_features,
)
from dummyindex.context.domains.features.indexes import _load_call_links
from dummyindex.context.domains.features.scan import (
    load_symbol_ref_index,
    validate_scan,
)
from dummyindex.context.domains.graph_query import (
    GraphArtifactInvalidError,
    callers_of,
    load_symbol_graph,
)
from dummyindex.context.domains.reality_check.verify import _load_call_edges
from dummyindex.context.output.viewer import render_viewer_html
from dummyindex.context.output.viewer.extras import load_viewer_extras
from dummyindex.export.storage import read_graph_payload, write_graph_payload
from tests.context.domains.test_graph_query import write_graph

pytestmark = pytest.mark.integration


def test_ambiguous_call_target_is_visible_and_does_not_imply_dead_code(tmp_path):
    from dummyindex.context.domains.graph_query import (
        callees_of,
        dead_code,
        resolve_symbol,
    )
    from dummyindex.context.domains.graph_query.errors import AmbiguousSymbolError
    from dummyindex.context.domains.graph_query.render import (
        render_json,
        render_markdown,
    )

    context = tmp_path / ".context"
    payload = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "caller",
                "label": "caller()",
                "file_type": "code",
                "source_file": "caller.py",
                "source_location": "L1",
            },
            {
                "id": "left",
                "label": "run()",
                "file_type": "code",
                "source_file": "left/dispatch.py",
                "source_location": "L2",
            },
            {
                "id": "right",
                "label": "run()",
                "file_type": "code",
                "source_file": "right/dispatch.py",
                "source_location": "L4",
            },
            {
                "id": "dispatch_run",
                "label": "Ambiguous dispatch_run",
                "file_type": "ambiguity",
                "resolution": "ambiguous",
                "candidate_ids": ["left", "right"],
            },
        ],
        "links": [
            {
                "source": "caller",
                "target": "dispatch_run",
                "_src": "caller",
                "_tgt": "dispatch_run",
                "relation": "calls",
            }
        ],
    }
    write_graph_payload(payload, context / "features/symbol-graph.json")
    graph = load_symbol_graph(context)
    with pytest.raises(AmbiguousSymbolError) as error:
        resolve_symbol(graph, "dispatch_run")
    assert error.value.total == 2
    assert resolve_symbol(graph, "left/dispatch.py:run") == "left"
    result = callees_of(graph, "caller")
    assert result.rows[0].resolution == "ambiguous"
    assert result.rows[0].citation == "unresolved reference"
    assert "left/dispatch.py:L2" in render_json(result)
    assert "Ambiguous reference" in render_markdown(result)
    assert {r.node_id for r in dead_code(graph).rows}.isdisjoint({"left", "right"})
    payload["nodes"][-1]["candidate_ids"] = 7
    write_graph_payload(payload, context / "features/symbol-graph.json")
    with pytest.raises(GraphArtifactInvalidError, match="ambiguity"):
        load_symbol_graph(context)


def test_extraction_schema_requires_real_ambiguity_candidates_without_fake_citation():
    from dummyindex.pipeline.build.validate import validate_extraction

    data = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "b.py"},
            {
                "id": "unknown",
                "label": "Ambiguous",
                "file_type": "ambiguity",
                "resolution": "ambiguous",
                "original_id": "legacy",
                "candidate_ids": ["a", "b"],
            },
        ],
        "edges": [],
    }
    assert validate_extraction(data) == []
    data["nodes"][-1]["source_file"] = "invented.py"
    assert any("citation" in error for error in validate_extraction(data))


def test_graph_render_budget_preserves_complete_records():
    from dummyindex.context.domains.graph_query.models import GraphQueryResult, GraphRow
    from dummyindex.context.domains.graph_query.render import (
        render_json,
        render_markdown,
    )

    result = GraphQueryResult(
        1,
        "neighbors",
        (),
        None,
        100,
        False,
        tuple(GraphRow(str(i), "符" * 500, "source.py:1", 0, 1) for i in range(100)),
    )
    encoded = render_json(result, max_bytes=4096)
    assert len(encoded.encode("utf-8")) <= 4096
    assert json.loads(encoded)["truncated"] is True
    assert len(render_markdown(result, max_bytes=4096).encode("utf-8")) <= 4096


def _snapshot(context: Path, scan: dict) -> dict:
    features = context / "features"
    graph = load_symbol_graph(context)
    refs = load_symbol_ref_index(features)
    assert refs is not None
    return {
        "query": callers_of(graph, "lib_util").to_dict(),
        "links": sorted(
            json.dumps(link, sort_keys=True)
            for link in _load_call_links(features / "symbol-graph.json")
        ),
        "refs": refs,
        "validation": validate_scan(scan, symbol_refs=refs),
        "calls": _load_call_edges(context, frozenset()),
        "extras": load_viewer_extras(scan, features).to_dict(),
        "html": render_viewer_html(scan, features_dir=features),
    }


def test_legacy_and_sharded_consumers_are_equivalent(tmp_path: Path) -> None:
    context = write_graph(tmp_path)
    features = context / "features"
    scan = {
        "schema_version": 2,
        "project": {"name": "repo", "slug": "repo"},
        "stats": {"agents": 0, "models": 0, "tools": 0, "integrations": 0},
        "graph": {
            "nodes": [
                {
                    "id": "application",
                    "label": "Application",
                    "kind": "service",
                    "symbolRef": "app_main",
                    "evidence": "EXTRACTED",
                }
            ],
            "edges": [],
        },
    }
    cards = {
        "communities": [
            {
                "slug": "application",
                "size": 6,
                "members": [{"id": "app_main", "label": "main()", "score": 1}],
            },
            {
                "slug": "library",
                "size": 3,
                "members": [{"id": "lib_util", "label": "util()", "score": 0.5}],
            },
        ]
    }
    (features / "graph-communities.json").write_text(
        json.dumps(cards), encoding="utf-8"
    )
    (features / "seed-rank.json").write_text(
        json.dumps({"ranked": [{"id": "lib_util", "score": 1}]}), encoding="utf-8"
    )
    before = _snapshot(context, scan)
    assert before["validation"] == ()
    assert before["extras"]["expansion"]["app_main"]
    assert before["extras"]["communityLinks"]
    assert ("main", "util") in before["calls"]
    assert ("util", "main") not in before["calls"]

    path = features / "symbol-graph.json"
    payload = read_graph_payload(path)
    write_graph_payload(payload, path, max_file_bytes=1800)
    assert "nodes" not in json.loads(path.read_text(encoding="utf-8"))
    assert _snapshot(context, scan) == before


def test_sharded_rebuild_preserves_the_scaffolded_feature_seed(tmp_path: Path) -> None:
    context = write_graph(tmp_path)
    features = context / "features"
    path = features / "symbol-graph.json"
    payload = read_graph_payload(path)
    scaffold_features(context, payload, root=tmp_path)
    (context / "meta.json").write_text(
        json.dumps({"root": str(tmp_path)}), encoding="utf-8"
    )
    before = json.loads((features / "graph.json").read_text(encoding="utf-8"))
    write_graph_payload(payload, path, max_file_bytes=1800)
    rebuild_features_graph(features)
    assert json.loads((features / "graph.json").read_text(encoding="utf-8")) == before


def test_corrupt_shard_is_not_a_valid_empty_query(tmp_path: Path) -> None:
    context = write_graph(tmp_path)
    path = context / "features" / "symbol-graph.json"
    existing = {p for p in path.parent.rglob("*") if p.is_file()}
    write_graph_payload(read_graph_payload(path), path, max_file_bytes=1800)
    shards = sorted(
        p for p in path.parent.rglob("*") if p.is_file() and p not in existing
    )
    assert shards, "fixture must exercise sharded storage"
    shards[0].write_bytes(b'{"tampered": true}\n')
    with pytest.raises(GraphArtifactInvalidError):
        load_symbol_graph(context)
    # Optional derived views retain their existing graceful-degradation policy.
    assert load_symbol_ref_index(path.parent) is None
    assert _load_call_links(path) == ()
    assert _load_call_edges(context, frozenset()) == frozenset()
