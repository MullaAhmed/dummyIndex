"""Checkout roots must not become graph identities or persistent source paths."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dummyindex.context.build.graph import build_graph
from dummyindex.context.build.portable_graph import normalize_extraction_paths
from dummyindex.pipeline.build import build_structure
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.extract.common import _make_id


def _extraction(root: Path) -> dict:
    source = root / "src" / "main.dart"
    file_id = _make_id(str(source))
    symbol_id = _make_id(str(source), "Worker")
    return {
        "nodes": [
            {
                "id": file_id,
                "label": "main.dart",
                "file_type": "code",
                "source_file": str(source),
            },
            {
                "id": symbol_id,
                "label": "Worker",
                "file_type": "code",
                "source_file": str(source),
            },
            {
                "id": "external_api",
                "label": "API",
                "file_type": "code",
                "source_file": "",
            },
        ],
        "edges": [
            {
                "source": file_id,
                "target": symbol_id,
                "relation": "contains",
                "confidence": "EXTRACTED",
                "source_file": str(source),
            },
            {
                "source": symbol_id,
                "target": "external_api",
                "relation": "calls",
                "confidence": "EXTRACTED",
                "source_file": str(source),
            },
        ],
        "hyperedges": [
            {
                "id": "work",
                "label": "Work",
                "nodes": [file_id, symbol_id],
                "members": [{"node_id": symbol_id, "role": "core"}],
                "sequence": [{"source": file_id, "target": symbol_id}],
            }
        ],
        "file_bytes": {str(source): b"class Worker {}"},
    }


@pytest.mark.unit
def test_normalizes_declared_paths_and_references_without_mutation(
    tmp_path: Path,
) -> None:
    extraction = _extraction(tmp_path)
    old_file_id, old_symbol_id = [n["id"] for n in extraction["nodes"][:2]]
    edge = extraction["edges"][0]
    edge.update(
        {
            "from": old_file_id,
            "to": old_symbol_id,
            "_src": old_file_id,
            "_tgt": old_symbol_id,
        }
    )
    extraction["nodes"][0]["path"] = str(tmp_path / "src" / "main.dart")
    extraction["links"] = [dict(edge)]
    original = copy.deepcopy(extraction)

    result = normalize_extraction_paths(extraction, tmp_path)

    assert extraction == original
    assert result["nodes"][0]["source_file"] == "src/main.dart"
    assert result["nodes"][0]["path"] == "src/main.dart"
    assert [n["id"] for n in result["nodes"]] == [
        "src_main_dart",
        "src_main_dart_worker",
        "external_api",
    ]
    for field in ("edges", "links"):
        assert result[field][0]["source_file"] == "src/main.dart"
        for key in ("source", "from", "_src"):
            assert result[field][0][key] == "src_main_dart"
        for key in ("target", "to", "_tgt"):
            assert result[field][0][key] == "src_main_dart_worker"
    hyperedge = result["hyperedges"][0]
    assert hyperedge["nodes"] == ["src_main_dart", "src_main_dart_worker"]
    assert hyperedge["members"][0]["node_id"] == "src_main_dart_worker"
    assert hyperedge["sequence"] == [
        {"source": "src_main_dart", "target": "src_main_dart_worker"}
    ]
    assert result["file_bytes"] == original["file_bytes"]
    assert normalize_extraction_paths(result, tmp_path) == result


@pytest.mark.unit
def test_preserves_external_paths_opaque_ids_and_attributes(tmp_path: Path) -> None:
    external = str(tmp_path.parent / "outside.py")
    internal = str(tmp_path / "src" / "main.dart")
    opaque_id = _make_id(internal) + "_not_a_filename_derived_id"
    extraction = {
        "nodes": [
            {"id": "external", "source_file": external, "path": "../outside.py"},
            {
                "id": opaque_id,
                "label": "opaque",
                "source_file": internal,
                "note": internal,
                "metadata": {"path": internal},
            },
            {"id": "foreign", "source_file": "/another-machine/source.py"},
            {"id": "uri", "source_file": "https://example.com/source.py"},
        ],
        "edges": [{"source": opaque_id, "target": "external", "description": internal}],
        "metadata": {"path": internal},
    }

    result = normalize_extraction_paths(extraction, tmp_path)

    assert result["nodes"][0] == extraction["nodes"][0]
    assert result["nodes"][1] == {
        **extraction["nodes"][1],
        "source_file": "src/main.dart",
    }
    assert result["nodes"][2:] == extraction["nodes"][2:]
    assert result["edges"] == extraction["edges"]
    assert result["metadata"] == extraction["metadata"]


@pytest.mark.unit
def test_normalizes_legacy_source_alias_and_relative_separators(tmp_path: Path) -> None:
    source = str(tmp_path / "src" / "one.py")
    extraction = {
        "nodes": [
            {"id": _make_id(source), "source": source},
            {"id": "two", "source_file": "src\\two.py"},
        ]
    }

    result = normalize_extraction_paths(extraction, tmp_path)

    assert result["nodes"] == [
        {"id": "src_one_py", "source": "src/one.py"},
        {"id": "two", "source_file": "src/two.py"},
    ]
    assert extraction["nodes"][0]["source"] == source


@pytest.mark.unit
def test_refuses_collisions_instead_of_merging_nodes(tmp_path: Path) -> None:
    extraction = _extraction(tmp_path)
    extraction["nodes"].append(
        {"id": "src_main_dart", "label": "opaque", "source_file": ""}
    )

    with pytest.raises(ValueError, match="Portable graph node ID collision"):
        normalize_extraction_paths(extraction, tmp_path)


@pytest.mark.integration
def test_unrelated_checkout_roots_produce_identical_graph_and_rank_artifacts(
    tmp_path: Path,
) -> None:
    roots = [tmp_path / "first-checkout", tmp_path / "unrelated" / "second-checkout"]
    outputs = []
    for root in roots:
        features = root / ".context" / "features"
        extraction = _extraction(root)
        original = copy.deepcopy(extraction)
        # No explicit root: only the standard .context/features layout infers it.
        build_graph(extraction, features)
        assert extraction == original
        outputs.append(features)

    for name in ("symbol-graph.json", "seed-rank.json", "graph-communities.json"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    graph = json.loads((outputs[0] / "symbol-graph.json").read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in graph["nodes"]}
    rank = json.loads((outputs[0] / "seed-rank.json").read_text(encoding="utf-8"))
    cards = json.loads(
        (outputs[0] / "graph-communities.json").read_text(encoding="utf-8")
    )
    assert {row["id"] for row in rank["ranked"]} <= node_ids
    assert {
        row["id"] for card in cards["communities"] for row in card["members"]
    } <= node_ids


@pytest.mark.integration
def test_file_identity_does_not_change_when_extraction_scope_expands(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "a.py"
    additional = tmp_path / "tests" / "b.py"
    for path in (source, additional):
        path.parent.mkdir(parents=True)
        path.write_text("def work():\n    return 1\n", encoding="utf-8")
    narrow = normalize_extraction_paths(
        extract([source], cache_root=tmp_path), tmp_path
    )
    expanded = normalize_extraction_paths(
        extract([source, additional], cache_root=tmp_path), tmp_path
    )
    for extraction in (narrow, expanded):
        file_node = next(n for n in extraction["nodes"] if n["label"] == "a.py")
        assert file_node["id"] == "src_a_py"
        assert file_node["source_file"] == "src/a.py"
        assert normalize_extraction_paths(extraction, tmp_path) == extraction
        structure = build_structure(
            extraction, [source], tmp_path, include_extras=False
        )
        assert any(
            n["id"] == "src_a_py" and n["kind"] == "file" for n in structure["nodes"]
        )


@pytest.mark.integration
def test_real_extraction_keeps_structure_graph_and_derived_ids_aligned(
    tmp_path: Path,
) -> None:
    outputs = []
    for name in ("checkout-one", "other-root"):
        root = tmp_path / name
        source = root / "src" / "main.dart"
        source.parent.mkdir(parents=True)
        source.write_text("class Worker {}\n", encoding="utf-8")
        extraction = normalize_extraction_paths(
            extract([source], cache_root=root), root
        )
        structure = build_structure(extraction, [source], root, include_extras=False)
        features = root / ".context" / "features"
        build_graph(extraction, features, root=root)
        graph = json.loads((features / "symbol-graph.json").read_text(encoding="utf-8"))
        ids = {n["id"] for n in graph["nodes"]}
        assert {n["id"] for n in structure["nodes"] if n["kind"] != "folder"} == ids
        assert {n["source_file"] for n in graph["nodes"]} == {"src/main.dart"}
        outputs.append(features)

    for name in ("symbol-graph.json", "seed-rank.json", "graph-communities.json"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()


@pytest.mark.integration
def test_custom_output_directory_does_not_guess_the_repository_root(
    tmp_path: Path,
) -> None:
    extraction = _extraction(tmp_path / "source")
    output = tmp_path / "custom-output"

    build_graph(extraction, output)

    graph = json.loads((output / "symbol-graph.json").read_text(encoding="utf-8"))
    assert {n["id"]: n["source_file"] for n in graph["nodes"]} == {
        n["id"]: n["source_file"] for n in extraction["nodes"]
    }
    assert {n["id"] for n in graph["nodes"]} == {n["id"] for n in extraction["nodes"]}
