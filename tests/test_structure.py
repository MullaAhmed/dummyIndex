import json
from pathlib import Path

from dummyindex.pipeline.export import to_structure_html, to_structure_json
from dummyindex.pipeline.extract import collect_files, extract
from dummyindex.pipeline.structure import build_structure


def _write_fixture_tree(root: Path) -> None:
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "service.py").write_text(
        "SERVICE_NAME = 'demo'\n\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return helper()\n\n"
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (pkg / "worker.py").write_text(
        "from .service import helper\n\n"
        "def execute():\n"
        "    return helper()\n",
        encoding="utf-8",
    )


def test_build_structure_adds_folder_nodes(tmp_path):
    _write_fixture_tree(tmp_path)
    paths = collect_files(tmp_path)
    structure = build_structure(extract(paths), paths, tmp_path)

    kinds = {n["kind"] for n in structure["nodes"]}
    assert "folder" in kinds
    assert "file" in kinds
    assert any(n["label"] == "pkg" and n["kind"] == "folder" for n in structure["nodes"])


def test_build_structure_classifies_units(tmp_path):
    _write_fixture_tree(tmp_path)
    paths = collect_files(tmp_path)
    structure = build_structure(extract(paths), paths, tmp_path)

    by_label = {n["label"]: n for n in structure["nodes"]}
    assert by_label["service.py"]["kind"] == "file"
    assert by_label["Service"]["kind"] == "class"
    assert by_label["helper()"]["kind"] == "function"
    assert by_label[".run()"]["kind"] == "method"


def test_build_structure_preserves_cross_edges(tmp_path):
    _write_fixture_tree(tmp_path)
    paths = collect_files(tmp_path)
    structure = build_structure(extract(paths), paths, tmp_path)

    relations = {e["relation"] for e in structure["cross_edges"]}
    # worker.py imports helper from service.py
    assert any(rel in relations for rel in ("imports", "imports_from", "calls"))

    # hierarchy edges only ever carry hierarchy relations
    hier_relations = {e["relation"] for e in structure["hierarchy_edges"]}
    assert hier_relations.issubset({"folder_contains", "contains", "method"})


def test_structure_export_json_roundtrip(tmp_path):
    _write_fixture_tree(tmp_path)
    paths = collect_files(tmp_path)
    structure = build_structure(extract(paths), paths, tmp_path)

    out_json = tmp_path / "structure_graph.json"
    to_structure_json(structure, str(out_json))
    data = json.loads(out_json.read_text(encoding="utf-8"))

    assert data["schema_version"] == "2.0"
    assert data["root_id"].startswith("folder__")
    assert any(n["kind"] == "folder" and n["parent"] is None for n in data["nodes"])
    assert any(e["relation"] == "folder_contains" for e in data["hierarchy_edges"])


def test_structure_export_html_contains_payload(tmp_path):
    _write_fixture_tree(tmp_path)
    paths = collect_files(tmp_path)
    structure = build_structure(extract(paths), paths, tmp_path)

    out_html = tmp_path / "structure_graph.html"
    to_structure_html(structure, str(out_html))
    html = out_html.read_text(encoding="utf-8")

    assert "Structure Graph" in html
    assert "vis-network" in html
    assert "hierarchy_edges" in html  # payload is embedded
    assert "cross_edges" in html


def test_build_structure_does_not_mutate_extraction(tmp_path):
    _write_fixture_tree(tmp_path)
    paths = collect_files(tmp_path)
    extraction = extract(paths)
    before_nodes = len(extraction["nodes"])
    before_edges = len(extraction["edges"])

    build_structure(extraction, paths, tmp_path)

    assert len(extraction["nodes"]) == before_nodes
    assert len(extraction["edges"]) == before_edges
    # none of the structure-only kinds leaked back onto the extraction dict
    assert all("kind" not in n for n in extraction["nodes"])
