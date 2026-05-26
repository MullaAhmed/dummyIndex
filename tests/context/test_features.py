"""Tests for dummyindex.context.features and the `features-rename` CLI.

Covers:
- scaffold_features detects communities + entry points, BFS-traces flows.
- INDEX.json / feature.json / flow.json schema.
- HTML viewer is emitted with graph.json + graph.html.
- rename_feature atomically updates folder + every JSON reference.
- The CLI subcommand front-end (`dummyindex context features-rename`).
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.features import (
    FeatureRenameError,
    merge_feature,
    rename_feature,
    scaffold_features,
)


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


def _ingested(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(_FIXTURE, target)
    assert dispatch(["init", str(target)]) == 0
    return target


# Minimal hand-crafted graph fixture so we don't rely on the sample repo's
# exact community structure.
_GRAPH = {
    "nodes": [
        {"id": "f1", "label": "f1()", "community": 0, "source_file": "/repo/a.py", "source_location": "L1"},
        {"id": "f2", "label": "f2()", "community": 0, "source_file": "/repo/a.py", "source_location": "L5"},
        {"id": "f3", "label": "f3()", "community": 0, "source_file": "/repo/a.py", "source_location": "L9"},
        {"id": "g1", "label": "g1()", "community": 1, "source_file": "/repo/b.py", "source_location": "L1"},
        {"id": "g2", "label": "g2()", "community": 1, "source_file": "/repo/b.py", "source_location": "L5"},
    ],
    "links": [
        {"source": "f1", "target": "f2", "relation": "calls"},
        {"source": "f1", "target": "f3", "relation": "calls"},
        {"source": "g1", "target": "g2", "relation": "calls"},
    ],
}


# ----- scaffold_features ----------------------------------------------------


@pytest.mark.unit
def test_scaffold_emits_one_feature_per_community(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    feature_ids = sorted(f.feature_id for f in result.features)
    assert feature_ids == ["community-0", "community-1"]
    assert (context_dir / "features" / "INDEX.json").exists()
    assert (context_dir / "features" / "community-0" / "feature.json").exists()
    assert (context_dir / "features" / "community-1" / "feature.json").exists()


@pytest.mark.unit
def test_scaffold_writes_spec_md_entry_point(tmp_path: Path) -> None:
    """v0.14: the deterministic scaffold writes `spec.md` (not README.md)."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    feat_dir = context_dir / "features" / "community-0"
    assert (feat_dir / "spec.md").is_file()
    assert not (feat_dir / "README.md").exists()
    assert "features/community-0/spec.md" in result.written


@pytest.mark.unit
def test_scaffold_detects_entry_points_by_in_degree(tmp_path: Path) -> None:
    """f1 and g1 are called by nothing → entry points; f2/f3/g2 aren't."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    by_id = {f.feature_id: f for f in result.features}
    assert by_id["community-0"].entry_points == ("f1",)
    assert by_id["community-1"].entry_points == ("g1",)


@pytest.mark.unit
def test_scaffold_traces_flow_via_bfs(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    flows_by_feature = {f.feature_id: [fl for fl in result.flows if fl.feature_id == f.feature_id] for f in result.features}
    assert len(flows_by_feature["community-0"]) == 1
    flow = flows_by_feature["community-0"][0]
    # f1 at depth 0, f2 and f3 at depth 1.
    step_ids = [s.node_id for s in flow.steps]
    assert step_ids[0] == "f1"
    assert set(step_ids[1:]) == {"f2", "f3"}
    assert {s.depth for s in flow.steps[1:]} == {1}


@pytest.mark.unit
def test_scaffold_writes_relative_paths(tmp_path: Path) -> None:
    """source_file values from the graph (absolute) get rewritten relative to root."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    for feat in result.features:
        for fp in feat.files:
            assert not fp.startswith("/"), f"{fp} should be repo-relative"


@pytest.mark.unit
def test_scaffold_emits_viewer_artifacts(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    assert (context_dir / "features" / "graph.json").exists()
    assert (context_dir / "features" / "graph.html").exists()
    html = (context_dir / "features" / "graph.html").read_text(encoding="utf-8")
    assert "d3" in html.lower()


@pytest.mark.unit
def test_graph_view_has_all_four_node_kinds(tmp_path: Path) -> None:
    """folder · file · feature · flow should all show up in graph.json."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    gv = json.loads((context_dir / "features" / "graph.json").read_text())
    kinds = {n["kind"] for n in gv["nodes"]}
    assert kinds == {"folder", "file", "feature", "flow"}


@pytest.mark.unit
def test_graph_view_builds_folder_hierarchy(tmp_path: Path) -> None:
    """Every file gets a chain of parent folders back to the repo root."""
    nested = {
        "nodes": [
            {"id": "n1", "label": "f()", "community": 0,
             "source_file": "/repo/app/core/auth.py", "source_location": "L1"},
            {"id": "n2", "label": "g()", "community": 0,
             "source_file": "/repo/app/core/auth.py", "source_location": "L5"},
        ],
        "links": [{"source": "n1", "target": "n2", "relation": "calls"}],
    }
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, nested, root=Path("/repo"))
    gv = json.loads((context_dir / "features" / "graph.json").read_text())
    folders = {n["path"] for n in gv["nodes"] if n["kind"] == "folder"}
    assert folders == {".", "app", "app/core"}
    # parent edges chain root → app → app/core
    parent_edges = {
        (e["source"], e["target"]) for e in gv["edges"] if e["relation"] == "parent"
    }
    assert ("folder::.", "folder::app") in parent_edges
    assert ("folder::app", "folder::app/core") in parent_edges
    # The leaf file is contained by its parent folder.
    contains = {
        (e["source"], e["target"]) for e in gv["edges"] if e["relation"] == "contains"
    }
    assert ("folder::app/core", "file::app/core/auth.py") in contains


@pytest.mark.unit
def test_graph_view_root_folder_is_dot(tmp_path: Path) -> None:
    """A file at repo root should sit directly under folder::."""
    flat = {
        "nodes": [{"id": "n1", "label": "f()", "community": 0,
                   "source_file": "/repo/main.py", "source_location": "L1"}],
        "links": [],
    }
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, flat, root=Path("/repo"))
    gv = json.loads((context_dir / "features" / "graph.json").read_text())
    contains = {
        (e["source"], e["target"]) for e in gv["edges"] if e["relation"] == "contains"
    }
    assert ("folder::.", "file::main.py") in contains


@pytest.mark.unit
def test_scaffold_handles_empty_graph(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, {"nodes": [], "links": []})
    assert result.features == ()
    assert result.flows == ()


# ----- rename_feature -------------------------------------------------------


@pytest.mark.unit
def test_rename_moves_folder_and_updates_metadata(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    res = rename_feature(
        context_dir / "features",
        from_id="community-0",
        to_id="authentication",
        new_name="Authentication",
        new_summary="Login flow.",
    )
    assert res.from_id == "community-0"
    assert res.to_id == "authentication"
    assert not (context_dir / "features" / "community-0").exists()
    assert (context_dir / "features" / "authentication" / "feature.json").exists()

    feat = json.loads(
        (context_dir / "features" / "authentication" / "feature.json").read_text()
    )
    assert feat["feature_id"] == "authentication"
    assert feat["name"] == "Authentication"
    assert feat["summary"] == "Login flow."
    assert feat["confidence"] == ConfidenceLevel.INFERRED


@pytest.mark.unit
def test_rename_updates_flow_feature_id(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    rename_feature(
        context_dir / "features",
        from_id="community-0",
        to_id="authentication",
    )
    flows_dir = context_dir / "features" / "authentication" / "flows"
    for fp in flows_dir.glob("*.json"):
        flow = json.loads(fp.read_text())
        assert flow["feature_id"] == "authentication"


@pytest.mark.unit
def test_rename_updates_index_json(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    rename_feature(
        context_dir / "features",
        from_id="community-0",
        to_id="authentication",
        new_name="Authentication",
    )
    idx = json.loads(
        (context_dir / "features" / "INDEX.json").read_text()
    )
    by_id = {e["feature_id"]: e for e in idx["features"]}
    assert "authentication" in by_id
    assert "community-0" not in by_id
    assert by_id["authentication"]["name"] == "Authentication"
    assert by_id["authentication"]["path"] == "features/authentication/"


@pytest.mark.unit
def test_rename_regenerates_features_index_md(tmp_path: Path) -> None:
    """After rename, features/INDEX.md must reference the new id, not the old."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    rename_feature(
        context_dir / "features",
        from_id="community-0",
        to_id="authentication",
        new_name="Authentication",
    )
    index_md = (context_dir / "features" / "INDEX.md").read_text(encoding="utf-8")
    assert "authentication" in index_md
    assert "[`Authentication`](./authentication/)" in index_md
    # The old stub id must NOT appear in any link or row.
    assert "(./community-0/)" not in index_md


@pytest.mark.unit
def test_rename_updates_viewer_graph(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))

    rename_feature(
        context_dir / "features",
        from_id="community-0",
        to_id="authentication",
    )
    gv = json.loads((context_dir / "features" / "graph.json").read_text())
    feature_ids = [n["id"] for n in gv["nodes"] if n["kind"] == "feature"]
    assert "authentication" in feature_ids
    assert "community-0" not in feature_ids
    # Every flow node's feature_id was rewritten too.
    flow_features = {
        n["feature_id"] for n in gv["nodes"] if n["kind"] == "flow"
    }
    assert "community-0" not in flow_features


@pytest.mark.unit
def test_rename_rejects_bad_id(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    with pytest.raises(FeatureRenameError):
        rename_feature(
            context_dir / "features",
            from_id="community-0",
            to_id="Has Spaces!",
        )


@pytest.mark.unit
def test_rename_rejects_missing_source(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    with pytest.raises(FeatureRenameError):
        rename_feature(
            context_dir / "features",
            from_id="not-a-real-id",
            to_id="x",
        )


@pytest.mark.unit
def test_rename_rejects_existing_target(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    with pytest.raises(FeatureRenameError):
        rename_feature(
            context_dir / "features",
            from_id="community-0",
            to_id="community-1",  # already exists
        )


@pytest.mark.unit
def test_rename_idempotent_same_id_just_refreshes_metadata(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    res = rename_feature(
        context_dir / "features",
        from_id="community-0",
        to_id="community-0",
        new_summary="Same id, new summary.",
    )
    assert res.from_id == res.to_id == "community-0"
    feat = json.loads(
        (context_dir / "features" / "community-0" / "feature.json").read_text()
    )
    assert feat["summary"] == "Same id, new summary."
    assert feat["confidence"] == ConfidenceLevel.INFERRED


# ----- CLI front-end --------------------------------------------------------


@pytest.mark.integration
def test_cli_features_rename_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_rename")
    capsys.readouterr()
    # Pick a feature_id that actually exists.
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    from_id = idx["features"][0]["feature_id"]

    monkeypatch.chdir(target)
    rc = dispatch(
        [
            "features-rename",
            "--from",
            from_id,
            "--to",
            "renamed-feature",
            "--name",
            "Renamed Feature",
            "--summary",
            "A test rename.",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "renamed-feature" in out
    feat = json.loads(
        (target / ".context" / "features" / "renamed-feature" / "feature.json").read_text()
    )
    assert feat["name"] == "Renamed Feature"
    assert feat["confidence"] == ConfidenceLevel.INFERRED


@pytest.mark.integration
def test_cli_features_rename_requires_from_and_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_rename_missing_flags")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["features-rename", "--from", "community-0"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--from" in err and "--to" in err


@pytest.mark.integration
def test_ingest_writes_features_folder(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "ingest_features")
    feats = target / ".context" / "features"
    assert (feats / "INDEX.json").is_file()
    assert (feats / "HOW_TO_NAVIGATE.md").is_file()
    assert (feats / "graph.json").is_file()
    assert (feats / "graph.html").is_file()


# ----- merge_feature --------------------------------------------------------


def _two_feature_scaffold(tmp_path: Path) -> Path:
    """Build a deterministic two-feature scaffold so merge tests don't depend
    on the sample repo's exact Leiden output."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    scaffold_features(context_dir, _GRAPH, root=Path("/repo"))
    return context_dir / "features"


@pytest.mark.integration
def test_merge_feature_appends_section_and_removes_source(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)

    src_spec = (features_dir / "community-1" / "spec.md").read_text(
        encoding="utf-8"
    )

    result = merge_feature(
        features_dir,
        from_id="community-1",
        into_id="community-0",
        as_section="supporting",
    )

    # Source folder gone.
    assert not (features_dir / "community-1").exists()
    assert result.from_id == "community-1"
    assert result.to_id == "community-0"

    # Target now has a supporting.md with the source's spec content woven in.
    supporting = features_dir / "community-0" / "supporting.md"
    assert supporting.exists()
    body = supporting.read_text(encoding="utf-8")
    assert "community-1" in body  # source attribution present
    # At least one bullet from the source spec should have made it across
    # (file list or member count line).
    assert any(line.strip() for line in body.splitlines())
    assert src_spec  # sanity: source had content to merge


@pytest.mark.integration
def test_merge_feature_merges_members_files_entry_points(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)

    merge_feature(
        features_dir,
        from_id="community-1",
        into_id="community-0",
        as_section="supporting",
    )

    target = json.loads(
        (features_dir / "community-0" / "feature.json").read_text(encoding="utf-8")
    )
    # members include both source and target members.
    assert "g1" in target["members"]
    assert "g2" in target["members"]
    assert "f1" in target["members"]
    # files merged.
    assert "a.py" in target["files"]
    assert "b.py" in target["files"]
    # entry points merged.
    assert "g1" in target["entry_points"]
    assert "f1" in target["entry_points"]
    # confidence bumped — chairman touched it.
    assert target["confidence"] == ConfidenceLevel.INFERRED


@pytest.mark.integration
def test_merge_feature_drops_source_from_index(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)

    merge_feature(
        features_dir,
        from_id="community-1",
        into_id="community-0",
        as_section="supporting",
    )

    idx = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    feature_ids = [e["feature_id"] for e in idx["features"]]
    assert "community-1" not in feature_ids
    assert "community-0" in feature_ids


@pytest.mark.integration
def test_merge_feature_drops_source_from_graph(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)

    merge_feature(
        features_dir,
        from_id="community-1",
        into_id="community-0",
        as_section="supporting",
    )

    graph = json.loads((features_dir / "graph.json").read_text(encoding="utf-8"))
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "community-1" not in node_ids
    # Edges that referenced the source must be gone or rerouted.
    for e in graph.get("edges", []):
        assert e.get("source") != "community-1"
        assert e.get("target") != "community-1"


@pytest.mark.unit
def test_merge_feature_rejects_unknown_source(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)
    with pytest.raises(FeatureRenameError, match="not found"):
        merge_feature(
            features_dir,
            from_id="nope",
            into_id="community-0",
            as_section="supporting",
        )


@pytest.mark.unit
def test_merge_feature_rejects_unknown_target(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)
    with pytest.raises(FeatureRenameError, match="not found"):
        merge_feature(
            features_dir,
            from_id="community-1",
            into_id="nope",
            as_section="supporting",
        )


@pytest.mark.unit
def test_merge_feature_rejects_self_merge(tmp_path: Path) -> None:
    features_dir = _two_feature_scaffold(tmp_path)
    with pytest.raises(FeatureRenameError, match="into itself"):
        merge_feature(
            features_dir,
            from_id="community-0",
            into_id="community-0",
            as_section="supporting",
        )


@pytest.mark.integration
def test_merge_feature_appends_to_existing_section(tmp_path: Path) -> None:
    """A second merge into the same `as_section` appends rather than clobbers."""
    features_dir = _two_feature_scaffold(tmp_path)

    # Manually scaffold a third feature so we can merge twice.
    third = {
        "nodes": [
            {"id": "h1", "label": "h1()", "community": 2, "source_file": "/repo/c.py", "source_location": "L1"},
        ],
        "links": [],
    }
    context_dir = tmp_path / ".context"
    scaffold_features(context_dir, third, root=Path("/repo"))

    merge_feature(
        features_dir, from_id="community-1", into_id="community-0",
        as_section="supporting",
    )
    body_after_first = (features_dir / "community-0" / "supporting.md").read_text(
        encoding="utf-8"
    )

    merge_feature(
        features_dir, from_id="community-2", into_id="community-0",
        as_section="supporting",
    )
    body_after_second = (features_dir / "community-0" / "supporting.md").read_text(
        encoding="utf-8"
    )

    # Old content stayed; new content was appended (no clobber).
    assert "community-1" in body_after_second
    assert "community-2" in body_after_second
    assert len(body_after_second) > len(body_after_first)


@pytest.mark.integration
def test_cli_features_merge_happy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `dummyindex context features-merge` CLI wires merge_feature in."""
    target = _ingested(tmp_path, "cli_merge")
    capsys.readouterr()

    idx = json.loads(
        (target / ".context" / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    if len(idx["features"]) < 2:
        pytest.skip("fixture has fewer than two features; can't exercise merge")
    src = idx["features"][0]["feature_id"]
    dst = idx["features"][1]["feature_id"]

    monkeypatch.chdir(target)
    rc = dispatch(
        [
            "features-merge",
            "--from", src,
            "--into", dst,
            "--as-section", "supporting",
        ]
    )
    assert rc == 0
    assert not (target / ".context" / "features" / src).exists()
    assert (target / ".context" / "features" / dst / "supporting.md").exists()


@pytest.mark.integration
def test_cli_features_merge_requires_from_into_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_merge_missing_flags")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["features-merge", "--from", "community-0"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--from" in err
    assert "--into" in err


# ----- guards added in 0.13.2 -----------------------------------------------
# Regression coverage for the consolidation-pass failure mode where 21
# parser-artifact "features" got bulk-merged into unrelated parents under an
# invented `noise-absorbed` section with no chairman audit trail. These tests
# pin each of the three guards.


@pytest.mark.unit
def test_merge_feature_rejects_unknown_section(tmp_path: Path) -> None:
    """`as_section` outside the allowlist is rejected before any I/O."""
    features_dir = _two_feature_scaffold(tmp_path)
    with pytest.raises(FeatureRenameError, match="invalid section"):
        merge_feature(
            features_dir,
            from_id="community-1",
            into_id="community-0",
            as_section="noise-absorbed",
        )
    # Source folder untouched — validation happened before deletion.
    assert (features_dir / "community-1").exists()


@pytest.mark.integration
def test_merge_feature_appends_chairman_council_log(tmp_path: Path) -> None:
    """Every successful merge auto-appends a stage-0 chairman entry to the
    target's council log, so the audit trail can't be skipped."""
    features_dir = _two_feature_scaffold(tmp_path)

    merge_feature(
        features_dir,
        from_id="community-1",
        into_id="community-0",
        as_section="supporting",
    )

    log_path = (
        features_dir / "community-0" / "council" / "_council-log.json"
    )
    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    entries = payload["entries"]
    chairman_entries = [e for e in entries if e["agent"] == "chairman"]
    assert chairman_entries, "expected at least one chairman entry on target"
    last = chairman_entries[-1]
    assert last["stage"] == 0
    assert last["status"] == "complete"
    assert "community-1" in last["note"]  # default note carries source id


@pytest.mark.integration
def test_merge_feature_honours_explicit_note(tmp_path: Path) -> None:
    """Caller-supplied `note` lands verbatim on the target's council log."""
    features_dir = _two_feature_scaffold(tmp_path)

    merge_feature(
        features_dir,
        from_id="community-1",
        into_id="community-0",
        as_section="supporting",
        note="merged-from:community-1 rationale=imported by community-0 entry points",
    )

    payload = json.loads(
        (features_dir / "community-0" / "council" / "_council-log.json").read_text(
            encoding="utf-8"
        )
    )
    last = payload["entries"][-1]
    assert "rationale=imported" in last["note"]


@pytest.mark.unit
def test_scaffold_features_skips_empty_init_communities(tmp_path: Path) -> None:
    """Communities made up entirely of empty `__init__.py` files with no
    entry points are dropped at scaffold time so neither the trivial filter
    nor the chairman has to handle them."""
    graph = {
        "nodes": [
            # Community 0: a real feature with an entry point.
            {
                "id": "real",
                "label": "real()",
                "community": 0,
                "source_file": "/repo/app/handler.py",
                "source_location": "L1",
            },
            {
                "id": "callee",
                "label": "callee()",
                "community": 0,
                "source_file": "/repo/app/handler.py",
                "source_location": "L5",
            },
            # Community 1: noise — a single empty __init__.py with no
            # callable definitions (no out-edges means no entry point).
            {
                "id": "noise_init_pkg_a",
                "label": "pkg_a",
                "community": 1,
                "source_file": "/repo/app/pkg_a/__init__.py",
                "source_location": "L1",
            },
            # Community 2: two empty __init__.py files Leiden grouped.
            {
                "id": "noise_init_pkg_b",
                "label": "pkg_b",
                "community": 2,
                "source_file": "/repo/app/pkg_b/__init__.py",
                "source_location": "L1",
            },
            {
                "id": "noise_init_pkg_c",
                "label": "pkg_c",
                "community": 2,
                "source_file": "/repo/app/pkg_c/__init__.py",
                "source_location": "L1",
            },
        ],
        "links": [
            # Only the real community has a call edge — gives `real` an
            # entry point. Noise communities have no edges at all.
            {"source": "real", "target": "callee", "relation": "calls"},
        ],
    }

    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, graph, root=Path("/repo"))

    feature_ids = {f.feature_id for f in result.features}
    assert "community-0" in feature_ids
    assert "community-1" not in feature_ids
    assert "community-2" not in feature_ids

    # And they're not silently still on disk either.
    assert not (context_dir / "features" / "community-1").exists()
    assert not (context_dir / "features" / "community-2").exists()

    idx = json.loads(
        (context_dir / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    ids_in_index = {e["feature_id"] for e in idx["features"]}
    assert "community-1" not in ids_in_index
    assert "community-2" not in ids_in_index


@pytest.mark.integration
def test_cli_features_merge_passes_note_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--note "..."` makes it through `_parse_kv_flags` and lands verbatim
    in the target's council-log. Catches the case where the procedure tells
    operators to pass a flag that the CLI doesn't actually accept."""
    target = _ingested(tmp_path, "cli_merge_note")
    capsys.readouterr()

    idx = json.loads(
        (target / ".context" / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    if len(idx["features"]) < 2:
        pytest.skip("fixture has fewer than two features; can't exercise merge")
    src = idx["features"][0]["feature_id"]
    dst = idx["features"][1]["feature_id"]

    monkeypatch.chdir(target)
    note = "rationale=imported by dst entry points; checked-callers=none-other"
    rc = dispatch(
        [
            "features-merge",
            "--from", src,
            "--into", dst,
            "--as-section", "supporting",
            "--note", note,
        ]
    )
    assert rc == 0

    payload = json.loads(
        (target / ".context" / "features" / dst / "council" / "_council-log.json").read_text(
            encoding="utf-8"
        )
    )
    chairman_entries = [e for e in payload["entries"] if e["agent"] == "chairman"]
    assert chairman_entries, "expected at least one chairman entry on target"
    assert chairman_entries[-1]["note"] == note


@pytest.mark.integration
def test_cli_features_merge_rejects_unknown_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI surface enforces the section allowlist — `noise-absorbed` etc.
    fail at the boundary, not silently produce ad-hoc audit files."""
    target = _ingested(tmp_path, "cli_merge_bad_section")
    capsys.readouterr()

    idx = json.loads(
        (target / ".context" / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    if len(idx["features"]) < 2:
        pytest.skip("fixture has fewer than two features; can't exercise merge")
    src = idx["features"][0]["feature_id"]
    dst = idx["features"][1]["feature_id"]

    monkeypatch.chdir(target)
    rc = dispatch(
        [
            "features-merge",
            "--from", src,
            "--into", dst,
            "--as-section", "noise-absorbed",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "invalid section" in err
    # Source folder must still be present — validation happened pre-I/O.
    assert (target / ".context" / "features" / src).exists()


@pytest.mark.unit
def test_scaffold_features_keeps_init_with_real_callable(tmp_path: Path) -> None:
    """An `__init__.py` that defines a real callable still becomes a
    feature — the parser-artifact filter must not eat legitimate package
    APIs."""
    graph = {
        "nodes": [
            {
                "id": "pkg_entry",
                "label": "pkg_entry()",
                "community": 5,
                "source_file": "/repo/app/pkg/__init__.py",
                "source_location": "L1",
            },
            {
                "id": "pkg_helper",
                "label": "pkg_helper()",
                "community": 5,
                "source_file": "/repo/app/pkg/__init__.py",
                "source_location": "L5",
            },
        ],
        "links": [
            {"source": "pkg_entry", "target": "pkg_helper", "relation": "calls"},
        ],
    }

    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    result = scaffold_features(context_dir, graph, root=Path("/repo"))

    feature_ids = {f.feature_id for f in result.features}
    assert "community-5" in feature_ids
