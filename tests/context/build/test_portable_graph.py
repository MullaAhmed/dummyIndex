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


def _colliding_extraction(root: Path) -> dict:
    paths = [root / "a/dispatch.py", root / "b/dispatch.py"]
    nodes, edges = [], []
    for index, path in enumerate(paths):
        file_id = _make_id(str(path))
        nodes.extend(
            [
                {
                    "id": file_id,
                    "label": "dispatch.py",
                    "source_file": str(path),
                    "file_type": "code",
                },
                {
                    "id": "dispatch_run",
                    "label": "run",
                    "source_file": str(path),
                    "source_location": f"L{index + 2}",
                    "file_type": "code",
                    "note": f"kept-{index}",
                },
                {
                    "id": "dispatch_rationale_1",
                    "label": f"Module documentation {index}",
                    "source_file": str(path),
                    "source_location": "L1",
                    "file_type": "rationale",
                },
            ]
        )
        edges.extend(
            [
                {
                    "source": file_id,
                    "target": "dispatch_run",
                    "relation": "contains",
                    "source_file": str(path),
                },
                {
                    "source": "dispatch_rationale_1",
                    "target": file_id,
                    "relation": "rationale_for",
                    "source_file": str(path),
                },
                {
                    "source": "dispatch_run",
                    "target": "dispatch_run",
                    "relation": "calls",
                    "source_file": str(path),
                    "target_source_file": str(path),
                },
            ]
        )
    edges.append(
        {
            "source": "dispatch_run",
            "target": "dispatch_run",
            "relation": "calls",
            "source_file": str(paths[0]),
            "confidence": "INFERRED",
            "note": "unknown imported target",
        }
    )
    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": [
            {
                "id": "flow",
                "nodes": ["dispatch_run"],
                "members": [
                    {
                        "node_id": "dispatch_run",
                        "source_file": str(paths[1]),
                        "role": "kept",
                    }
                ],
                "sequence": [
                    {
                        "source": "dispatch_run",
                        "target": "dispatch_run",
                        "source_file": str(paths[0]),
                    }
                ],
            }
        ],
    }


@pytest.mark.unit
def test_source_collisions_keep_definitions_attributes_and_contextual_edges(tmp_path):
    original = _colliding_extraction(tmp_path)
    before = copy.deepcopy(original)
    result = normalize_extraction_paths(original, tmp_path)
    real = [node for node in result["nodes"] if node.get("file_type") != "ambiguity"]
    assert len(real) == len(original["nodes"])
    assert len({node["id"] for node in result["nodes"]}) == len(result["nodes"])
    functions = {
        node["source_file"]: node for node in real if node.get("label") == "run"
    }
    assert {node["note"] for node in functions.values()} == {"kept-0", "kept-1"}
    assert functions["a/dispatch.py"]["source_location"] == "L2"
    assert functions["b/dispatch.py"]["source_location"] == "L3"
    for edge in result["edges"][:-1]:
        indexed = {node["id"]: node for node in real}
        assert indexed[edge["source"]]["source_file"] == edge["source_file"]
        assert indexed[edge["target"]]["source_file"] == edge["source_file"]
    uncertain = result["edges"][-1]
    placeholder = next(
        node for node in result["nodes"] if node["id"] == uncertain["target"]
    )
    assert placeholder["resolution"] == "ambiguous"
    assert placeholder["candidate_ids"] == sorted(
        node["id"] for node in functions.values()
    )
    assert "source_file" not in placeholder and "source_location" not in placeholder
    assert uncertain["source"] == functions["a/dispatch.py"]["id"]
    assert uncertain["note"] == "unknown imported target"
    hyperedge = result["hyperedges"][0]
    assert hyperedge["nodes"] == [placeholder["id"]]
    assert hyperedge["members"][0]["node_id"] == functions["b/dispatch.py"]["id"]
    assert hyperedge["members"][0]["role"] == "kept"
    assert hyperedge["sequence"][0]["source"] == functions["a/dispatch.py"]["id"]
    assert hyperedge["sequence"][0]["target"] == placeholder["id"]
    assert original == before
    assert normalize_extraction_paths(result, tmp_path) == result


@pytest.mark.unit
def test_same_path_distinct_records_are_not_coalesced_and_exact_duplicates_dedupe(
    tmp_path,
):
    a = {
        "id": "same",
        "label": "work",
        "source_file": "one.py",
        "source_location": "L2",
    }
    b = {**a, "source_location": "L9", "note": "different definition"}
    result = normalize_extraction_paths({"nodes": [a, copy.deepcopy(a), b]}, tmp_path)
    assert len(result["nodes"]) == 2
    assert len({node["id"] for node in result["nodes"]}) == 2
    assert {node["source_location"] for node in result["nodes"]} == {"L2", "L9"}
    assert normalize_extraction_paths(result, tmp_path) == result


@pytest.mark.integration
def test_init_and_dunder_init_files_keep_separate_structure_and_symbols(tmp_path):
    paths = [tmp_path / "pkg/__init__.py", tmp_path / "pkg/init.py"]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n" * index + "def run():\n    return 1\n", encoding="utf-8")
    result = normalize_extraction_paths(extract(paths, cache_root=tmp_path), tmp_path)
    file_nodes = [
        node
        for node in result["nodes"]
        if node.get("label") in {"__init__.py", "init.py"}
    ]
    assert len({node["id"] for node in file_nodes}) == 2
    structure = build_structure(result, paths, tmp_path, include_extras=False)
    assert {
        node["source_file"] for node in structure["nodes"] if node["kind"] == "file"
    } == {"pkg/__init__.py", "pkg/init.py"}
    assert {
        node["source_file"] for node in structure["nodes"] if node["kind"] == "function"
    } == {"pkg/__init__.py", "pkg/init.py"}
    assert {
        node["source_file"]: node["source_location"]
        for node in structure["nodes"]
        if node["kind"] == "function"
    } == {"pkg/__init__.py": "L1", "pkg/init.py": "L2"}


@pytest.mark.integration
def test_same_basename_classes_methods_and_rationales_keep_both_sources(tmp_path):
    paths = [tmp_path / "a/dispatch.py", tmp_path / "b/dispatch.py"]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True)
        path.write_text(
            '"""Long module documentation kept for this source."""\n'
            + "\n" * index
            + "class Worker:\n    def run(self): return 1\n",
            encoding="utf-8",
        )
    raw = extract(paths, cache_root=tmp_path)
    normalized = normalize_extraction_paths(raw, tmp_path)
    for file_type in ("code", "rationale"):
        assert len(
            [node for node in normalized["nodes"] if node.get("file_type") == file_type]
        ) == len([node for node in raw["nodes"] if node.get("file_type") == file_type])
    structure = build_structure(normalized, paths, tmp_path, include_extras=False)
    for kind in ("class", "method"):
        assert {
            node["source_file"] for node in structure["nodes"] if node["kind"] == kind
        } == {"a/dispatch.py", "b/dispatch.py"}


@pytest.mark.unit
def test_collision_identities_are_root_portable_and_input_order_independent(tmp_path):
    left, right = tmp_path / "left", tmp_path / "other/right"
    first = normalize_extraction_paths(_colliding_extraction(left), left)
    reordered = _colliding_extraction(right)
    reordered["nodes"].reverse()
    second = normalize_extraction_paths(reordered, right)
    assert {node["id"]: node for node in first["nodes"]} == {
        node["id"]: node for node in second["nodes"]
    }
    assert first["edges"] == second["edges"]
    assert first["hyperedges"] == second["hyperedges"]
    assert first["identity_ambiguities"] == second["identity_ambiguities"]


def _sourceless_stub(label: str) -> dict:
    """The placeholder the extractor emits for a name it cannot resolve in-file."""
    return {
        "id": "fakeconn",
        "label": label,
        "file_type": "code",
        "source_file": "",
        "source_location": "",
    }


@pytest.mark.unit
def test_sourceless_stubs_sharing_a_slug_stay_distinct_and_edges_stay_ambiguous(
    tmp_path,
):
    source = tmp_path / "src" / "a.py"
    child = _make_id(str(source), "Child")
    extraction = {
        "nodes": [
            {
                "id": child,
                "label": "Child",
                "file_type": "code",
                "source_file": str(source),
            },
            _sourceless_stub("_FakeConn"),
            _sourceless_stub("FakeConn"),
        ],
        "edges": [
            {
                "source": child,
                "target": "fakeconn",
                "relation": "inherits",
                "confidence": "EXTRACTED",
                "source_file": str(source),
            }
        ],
    }
    before = copy.deepcopy(extraction)

    result = normalize_extraction_paths(extraction, tmp_path)

    stubs = [n for n in result["nodes"] if n.get("label") in {"_FakeConn", "FakeConn"}]
    assert {n["label"] for n in stubs} == {"_FakeConn", "FakeConn"}
    assert len({n["id"] for n in result["nodes"]}) == len(result["nodes"])
    assert {n["original_id"] for n in stubs} == {"fakeconn"}
    target = next(n for n in result["nodes"] if n["id"] == result["edges"][0]["target"])
    assert target["resolution"] == "ambiguous"
    assert target["candidate_ids"] == sorted(n["id"] for n in stubs)
    assert extraction == before
    assert normalize_extraction_paths(result, tmp_path) == result


@pytest.mark.unit
def test_sourceless_stub_collisions_are_input_order_independent(tmp_path):
    def run(labels: list[str]) -> dict:
        nodes = [_sourceless_stub(label) for label in labels]
        return normalize_extraction_paths({"nodes": nodes}, tmp_path)

    forward = run(["_FakeConn", "FakeConn"])
    backward = run(["FakeConn", "_FakeConn"])

    assert {n["id"]: n for n in forward["nodes"]} == {
        n["id"]: n for n in backward["nodes"]
    }
    assert forward["identity_ambiguities"] == backward["identity_ambiguities"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "foreign", ["/another-machine/fake.py", "https://example.com/fake.py"]
)
def test_sourceless_stub_colliding_with_a_foreign_path_is_still_refused(
    tmp_path, foreign
):
    extraction = {
        "nodes": [
            _sourceless_stub("_FakeConn"),
            {**_sourceless_stub("FakeConn"), "source_file": foreign},
        ]
    }

    with pytest.raises(ValueError, match="Portable graph node ID collision"):
        normalize_extraction_paths(extraction, tmp_path)


@pytest.mark.integration
def test_real_extraction_of_underscore_and_plain_base_class_names_builds_a_graph(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    package = root / "pkg"
    package.mkdir(parents=True)
    sources = []
    for name, text in {
        "shared.py": "class _FakeConn:\n    pass\n\n\nclass FakeConn:\n    pass\n",
        "a.py": "from pkg.shared import _FakeConn\n\n\n"
        "class UnauthorizedConn(_FakeConn):\n    pass\n",
        "b.py": "from pkg.shared import FakeConn\n\n\n"
        "class OtherConn(FakeConn):\n    pass\n",
    }.items():
        path = package / name
        path.write_text(text, encoding="utf-8")
        sources.append(path)

    extraction = normalize_extraction_paths(extract(sources, cache_root=root), root)
    features = root / ".context" / "features"
    build_graph(extraction, features, root=root)
    graph = json.loads((features / "symbol-graph.json").read_text(encoding="utf-8"))

    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(set(ids))
    assert all(
        link["source"] in ids and link["target"] in ids for link in graph["links"]
    )
    stub_labels = {n["label"] for n in graph["nodes"] if not n.get("source_file")}
    assert {"_FakeConn", "FakeConn"} <= stub_labels
