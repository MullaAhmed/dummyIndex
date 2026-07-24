"""`scan/refs.py` — the id universe a `symbolRef` may resolve into.

The loader walks a registry of extraction artifacts under `features/`
(`symbol-graph.json` today; A2's `graph-communities.json` registers itself
alongside). Degradation is the contract under test: a missing or unreadable
artifact contributes nothing, and when none could be read at all the loader
returns ``None`` so `validate_scan` warns instead of erroring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.features.scan import (
    SymbolRefIndex,
    load_symbol_ref_index,
)


def _write_symbol_graph(features_dir: Path, payload: object) -> None:
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "symbol-graph.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


@pytest.mark.unit
def test_no_artifacts_means_no_index(tmp_path: Path) -> None:
    assert load_symbol_ref_index(tmp_path) is None


@pytest.mark.unit
def test_loads_node_ids_from_the_symbol_graph(tmp_path: Path) -> None:
    _write_symbol_graph(
        tmp_path,
        {
            "directed": True,
            "multigraph": False,
            "graph": {},
            "nodes": [{"id": "sym_a"}, {"id": "sym_b"}],
            "links": [],
        },
    )
    index = load_symbol_ref_index(tmp_path)
    assert index is not None
    assert index.resolves("sym_a")
    assert index.resolves("sym_b")
    assert not index.resolves("ghost")
    assert index.sources == ("symbol-graph.json",)


@pytest.mark.unit
def test_an_unreadable_artifact_degrades_to_absent(tmp_path: Path) -> None:
    """Corrupt JSON is the rebuild's problem, not the scan author's."""
    features_dir = tmp_path
    features_dir.mkdir(exist_ok=True)
    (features_dir / "symbol-graph.json").write_text("{ not json", encoding="utf-8")
    assert load_symbol_ref_index(features_dir) is None


@pytest.mark.unit
def test_malformed_nodes_contribute_no_ids(tmp_path: Path) -> None:
    """A present-but-empty artifact still counts as a source: refs must resolve."""
    _write_symbol_graph(
        tmp_path, {"nodes": [{"label": "no id"}, "junk", {"id": 7}], "links": []}
    )
    index = load_symbol_ref_index(tmp_path)
    assert index is not None
    assert index.ids == frozenset()
    assert index.sources == ("symbol-graph.json",)


@pytest.mark.unit
def test_index_is_frozen_data() -> None:
    index = SymbolRefIndex(ids=frozenset({"a"}), sources=("symbol-graph.json",))
    with pytest.raises(AttributeError):
        index.ids = frozenset()  # type: ignore[misc]
