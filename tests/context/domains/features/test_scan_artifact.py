"""`features/graph.json` + `graph.html` as they land on disk.

The seed/curate split is the load-bearing behaviour here: a rebuild has to
regenerate a deterministic (`EXTRACTED`) scan and must never touch a
curated (`INFERRED`) one, because the curated scan is the only artifact in
`.context/` that no amount of re-extraction can reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.features import (
    rebuild_features_graph,
    scaffold_features,
)
from dummyindex.context.domains.features.constants import SCAN_SCHEMA_VERSION
from dummyindex.context.domains.features.scan import validate_scan
from dummyindex.pipeline.enums import ConfidenceLevel

_GRAPH = {
    "nodes": [
        {
            "id": "n1",
            "label": "login()",
            "community": 0,
            "source_file": "/repo/app/auth.py",
            "source_location": "L1",
        },
        {
            "id": "n2",
            "label": "verify()",
            "community": 0,
            "source_file": "/repo/app/auth.py",
            "source_location": "L20",
        },
        {
            "id": "n3",
            "label": "charge()",
            "community": 1,
            "source_file": "/repo/app/billing.py",
            "source_location": "L1",
        },
    ],
    "links": [
        {"source": "n1", "target": "n2", "relation": "calls"},
        {"source": "n1", "target": "n3", "relation": "calls"},
    ],
}


def _scaffolded(tmp_path: Path) -> Path:
    """Scaffold with a `root` that is deliberately NOT the context dir's parent.

    That mismatch is the realistic case (`ingest --root`), and it is what
    catches a rebuild inventing a different project name than scaffolding did.
    """
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    # ingest writes meta.json after scaffolding; a rebuild reads the root back
    # out of it, so the two paths agree on what the project is called.
    (context_dir / "meta.json").write_text(
        json.dumps({"root": "/repo", "schema_version": 1}), encoding="utf-8"
    )
    return context_dir / "features"


def _read(features_dir: Path) -> dict:
    return json.loads((features_dir / "graph.json").read_text(encoding="utf-8"))


# ----- what scaffolding writes ----------------------------------------------


@pytest.mark.integration
def test_scaffold_writes_a_valid_scan(tmp_path: Path) -> None:
    payload = _read(_scaffolded(tmp_path))
    assert payload["schema_version"] == SCAN_SCHEMA_VERSION
    assert validate_scan(payload) == ()


@pytest.mark.integration
def test_scaffold_scan_is_a_map_not_a_dump(tmp_path: Path) -> None:
    """v1 emitted every folder, file, class and method. v2 emits a map."""
    payload = _read(_scaffolded(tmp_path))
    kinds = {n["kind"] for n in payload["graph"]["nodes"]}
    assert kinds <= {"service", "entry"}
    assert "folder" not in kinds and "file" not in kinds


@pytest.mark.integration
def test_scaffold_names_the_project_from_the_repo_root(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo/My Cool App"))
    payload = _read(context_dir / "features")
    assert payload["project"]["name"] == "My Cool App"
    assert payload["project"]["slug"] == "my-cool-app"


@pytest.mark.integration
def test_scaffolded_scan_is_marked_extracted(tmp_path: Path) -> None:
    assert _read(_scaffolded(tmp_path))["confidence"] == ConfidenceLevel.EXTRACTED


@pytest.mark.integration
def test_scaffold_omits_the_date_so_rebuilds_stay_byte_stable(tmp_path: Path) -> None:
    assert "date" not in _read(_scaffolded(tmp_path))["project"]


# ----- rebuild: regenerate vs preserve ---------------------------------------


@pytest.mark.integration
def test_rebuild_regenerates_an_extracted_scan(tmp_path: Path) -> None:
    features_dir = _scaffolded(tmp_path)
    (features_dir / "graph.json").write_text(
        json.dumps({"schema_version": SCAN_SCHEMA_VERSION, "confidence": "EXTRACTED"}),
        encoding="utf-8",
    )
    rebuild_features_graph(features_dir)
    assert validate_scan(_read(features_dir)) == ()


@pytest.mark.integration
def test_rebuild_preserves_a_curated_scan(tmp_path: Path) -> None:
    features_dir = _scaffolded(tmp_path)
    curated = _read(features_dir)
    curated["confidence"] = ConfidenceLevel.INFERRED
    curated["project"]["tagline"] = "hand written, do not clobber"
    curated["stats"]["agents"] = 3
    (features_dir / "graph.json").write_text(json.dumps(curated), encoding="utf-8")

    rebuild_features_graph(features_dir)

    after = _read(features_dir)
    assert after["project"]["tagline"] == "hand written, do not clobber"
    assert after["stats"]["agents"] == 3


@pytest.mark.integration
def test_rebuild_preserves_a_curated_scan_even_when_it_fails_validation(
    tmp_path: Path,
) -> None:
    """Curation is unreproducible; a cap violation is not a reason to delete it."""
    features_dir = _scaffolded(tmp_path)
    broken = _read(features_dir)
    broken["confidence"] = ConfidenceLevel.INFERRED
    broken["graph"]["nodes"].append(
        {"id": "oops", "label": "x" * 90, "kind": "not-a-kind"}
    )
    (features_dir / "graph.json").write_text(json.dumps(broken), encoding="utf-8")

    rebuild_features_graph(features_dir)

    assert any(n["id"] == "oops" for n in _read(features_dir)["graph"]["nodes"])


@pytest.mark.integration
def test_rebuild_regenerates_over_unparseable_json(tmp_path: Path) -> None:
    features_dir = _scaffolded(tmp_path)
    (features_dir / "graph.json").write_text("{ not json", encoding="utf-8")
    rebuild_features_graph(features_dir)
    assert validate_scan(_read(features_dir)) == ()


@pytest.mark.integration
def test_rebuild_regenerates_a_legacy_v1_graph(tmp_path: Path) -> None:
    """A pre-v2 hairball has no `confidence` — it is generated, so replace it."""
    features_dir = _scaffolded(tmp_path)
    (features_dir / "graph.json").write_text(
        json.dumps({"schema_version": 1, "nodes": [], "edges": []}), encoding="utf-8"
    )
    rebuild_features_graph(features_dir)
    payload = _read(features_dir)
    assert payload["schema_version"] == SCAN_SCHEMA_VERSION
    assert validate_scan(payload) == ()


# ----- the viewer -------------------------------------------------------------


@pytest.mark.integration
def test_viewer_inlines_the_scan_so_it_opens_over_file_urls(tmp_path: Path) -> None:
    features_dir = _scaffolded(tmp_path)
    html = (features_dir / "graph.html").read_text(encoding="utf-8")
    start = html.index('<script type="application/json" id="scan-data">') + len(
        '<script type="application/json" id="scan-data">'
    )
    embedded = json.loads(html[start : html.index("</script>", start)])
    assert embedded["graph"]["nodes"] == _read(features_dir)["graph"]["nodes"]


@pytest.mark.integration
def test_viewer_makes_no_external_requests(tmp_path: Path) -> None:
    """Offline by construction: no CDN, no favicon service, no fetch.

    The one permitted `http://` is the SVG XML namespace, which is an
    identifier and is never dereferenced — so it is stripped before the
    check rather than weakening the check.
    """
    html = (_scaffolded(tmp_path) / "graph.html").read_text(encoding="utf-8")
    html = html.replace("http://www.w3.org/2000/svg", "")
    for forbidden in (
        "http://",
        "https://",
        "fetch(",
        "<link",
        "XMLHttpRequest",
        "//unpkg",
    ):
        assert forbidden not in html, f"viewer must not reference {forbidden!r}"


@pytest.mark.integration
def test_viewer_reflects_a_curated_scan_after_rebuild(tmp_path: Path) -> None:
    features_dir = _scaffolded(tmp_path)
    curated = _read(features_dir)
    curated["confidence"] = ConfidenceLevel.INFERRED
    curated["project"]["name"] = "Curated Name"
    (features_dir / "graph.json").write_text(json.dumps(curated), encoding="utf-8")

    rebuild_features_graph(features_dir)

    assert "Curated Name" in (features_dir / "graph.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_viewer_neutralizes_a_script_close_tag_in_scan_text() -> None:
    from dummyindex.context.output.viewer import render_viewer_html

    html = render_viewer_html(
        {
            "schema_version": SCAN_SCHEMA_VERSION,
            "graph": {
                "nodes": [{"id": "a", "label": "</script><img>", "kind": "service"}],
                "edges": [],
            },
        }
    )
    start = html.index('id="scan-data">') + len('id="scan-data">')
    end = html.index("</script>", start)
    assert json.loads(html[start:end])["graph"]["nodes"][0]["label"] == "</script><img>"


@pytest.mark.unit
def test_viewer_html_is_the_only_server_side_escape_point() -> None:
    """A curated scan is model-authored, so it is untrusted at render time.

    Everything else in the document is a constant; the data island is the
    single place a scan-derived string is written by Python rather than by
    the viewer's own `esc()`. Both sequences that can end a `<script>` early
    have to survive a round trip inert.
    """
    from dummyindex.context.output.viewer import render_viewer_html

    hostile = {
        "schema_version": SCAN_SCHEMA_VERSION,
        "project": {"name": "<!-- oops", "slug": "x"},
        "graph": {
            "nodes": [
                {
                    "id": "a",
                    "label": "</script><script>alert(1)</script>",
                    "kind": "service",
                }
            ],
            "edges": [],
        },
    }
    html = render_viewer_html(hostile)

    # Only `</script` can close a script element — an opening tag inside one
    # is inert text. So the invariant is the count of *closing* tags: two,
    # the data island's and the viewer's, and none smuggled in from the scan.
    assert html.count("</script>") == 2
    start = html.index('id="scan-data">') + len('id="scan-data">')
    parsed = json.loads(html[start : html.index("</script>", start)])
    assert parsed["graph"]["nodes"][0]["label"] == "</script><script>alert(1)</script>"
    assert parsed["project"]["name"] == "<!-- oops"


@pytest.mark.unit
def test_viewer_folds_an_unknown_node_kind_onto_the_alphabet() -> None:
    """`kind` reaches a class name and a CSS custom property, so it is bounded.

    Without the fold, a kind of `x);color:red;--y:(` would be written straight
    into `style.cssText`.
    """
    from dummyindex.context.output.viewer.script import VIEWER_JS

    assert "safeKind" in VIEWER_JS
    assert "--kind:var(--k-${kind})" in VIEWER_JS, "styled from the folded kind"
    assert "--kind:var(--k-${n.kind})" not in VIEWER_JS, "never from raw input"


@pytest.mark.integration
def test_scaffold_connects_features_that_call_each_other(tmp_path: Path) -> None:
    """`login()` calls `charge()` across a community boundary — that's an edge."""
    payload = _read(_scaffolded(tmp_path))
    calls = [e for e in payload["graph"]["edges"] if e["kind"] == "calls"]
    assert calls, "a seed with cross-community calls must not be disconnected"
    ids = {n["id"] for n in payload["graph"]["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in payload["graph"]["edges"])


@pytest.mark.integration
def test_rebuild_reproduces_the_scaffolded_seed_exactly(tmp_path: Path) -> None:
    """Scaffold and rebuild must agree, or a refresh silently degrades the map.

    They read different sources for the same fact — scaffold has the graph in
    memory, rebuild re-reads `symbol-graph.json` — so this is the test that
    keeps the two paths honest.
    """
    features_dir = _scaffolded(tmp_path)
    before = _read(features_dir)

    rebuild_features_graph(features_dir)

    assert _read(features_dir) == before


@pytest.mark.integration
def test_rebuild_without_meta_falls_back_without_crashing(tmp_path: Path) -> None:
    """An older `.context/` has no recorded root — degrade, don't fail."""
    features_dir = _scaffolded(tmp_path)
    (features_dir.parent / "meta.json").unlink()
    rebuild_features_graph(features_dir)
    assert validate_scan(_read(features_dir)) == ()


@pytest.mark.unit
def test_viewer_wraps_a_tall_tier_into_several_columns() -> None:
    """The seed's worst case is every node one kind — one 26-deep column.

    Wrapping is what keeps that legible, and only *named* groups are exempt
    from being split (a group is a claim that those nodes belong together;
    a pile of ungrouped nodes is not).
    """
    from dummyindex.context.output.viewer.script import VIEWER_JS

    assert "MAX_COL_ROWS" in VIEWER_JS
    assert "function wrap(blocks)" in VIEWER_JS
    assert "if (b.name) { units.push(b); continue; }" in VIEWER_JS
