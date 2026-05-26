"""Tests for the v0.7 council CLI helpers: flow-remove, section-write, council-log."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.council import (
    CouncilLogError,
    append_log,
    is_stage_complete,
    latest_status,
    read_log,
)
from dummyindex.context.domains.features import (
    FeatureRenameError,
    remove_flow,
    write_section,
)


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


def _ingested(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(_FIXTURE, target)
    assert dispatch(["init", str(target), "--no-hooks"]) == 0
    return target


def _first_feature_with_flow(target: Path) -> tuple[str, str]:
    """Return (feature_id, flow_id) for the first feature that has a flow."""
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    for entry in idx.get("features", []):
        feat = json.loads(
            (target / ".context" / "features" / entry["feature_id"] / "feature.json").read_text()
        )
        if feat.get("flow_ids"):
            return entry["feature_id"], feat["flow_ids"][0]
    pytest.skip("fixture has no flows to remove")
    raise AssertionError("unreachable")


# ----- remove_flow ----------------------------------------------------------


@pytest.mark.integration
def test_remove_flow_drops_files_and_updates_json(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "flow_remove")
    feature_id, flow_id = _first_feature_with_flow(target)
    features_dir = target / ".context" / "features"

    result = remove_flow(features_dir, feature_id=feature_id, flow_id=flow_id)

    assert not (features_dir / feature_id / "flows" / f"{flow_id}.json").exists()
    assert not (features_dir / feature_id / "flows" / f"{flow_id}.md").exists()

    feat = json.loads((features_dir / feature_id / "feature.json").read_text())
    assert flow_id not in feat.get("flow_ids", [])

    idx = json.loads((features_dir / "INDEX.json").read_text())
    entry = next(e for e in idx["features"] if e["feature_id"] == feature_id)
    assert entry["flow_count"] == len(feat["flow_ids"])

    assert result.files_touched, "rename result should list every touched file"


@pytest.mark.integration
def test_remove_flow_updates_graph(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "flow_remove_graph")
    feature_id, flow_id = _first_feature_with_flow(target)
    features_dir = target / ".context" / "features"

    remove_flow(features_dir, feature_id=feature_id, flow_id=flow_id)
    gv = json.loads((features_dir / "graph.json").read_text())
    assert flow_id not in {n["id"] for n in gv["nodes"]}
    for e in gv["edges"]:
        assert e["source"] != flow_id and e["target"] != flow_id


@pytest.mark.integration
def test_remove_flow_idempotent_when_already_gone(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "flow_remove_idempotent")
    feature_id, flow_id = _first_feature_with_flow(target)
    features_dir = target / ".context" / "features"

    remove_flow(features_dir, feature_id=feature_id, flow_id=flow_id)
    # Second call: flow files don't exist, no-op.
    result = remove_flow(features_dir, feature_id=feature_id, flow_id=flow_id)
    assert result.files_touched == ()


@pytest.mark.integration
def test_remove_flow_rejects_unknown_feature(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "flow_remove_unknown_feat")
    features_dir = target / ".context" / "features"
    with pytest.raises(FeatureRenameError):
        remove_flow(features_dir, feature_id="does-not-exist", flow_id="flow-001")


# ----- write_section --------------------------------------------------------


@pytest.mark.integration
def test_write_section_creates_named_md(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "section_write")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]

    src = tmp_path / "src.md"
    src.write_text("# Architecture\n\nIt's a thing.\n", encoding="utf-8")

    out = write_section(
        target / ".context" / "features",
        feature_id=feature_id,
        section="architecture",
        source_file=src,
    )
    assert out == target / ".context" / "features" / feature_id / "architecture.md"
    assert out.read_text() == src.read_text()


@pytest.mark.integration
def test_write_section_accepts_md_suffix(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "section_write_md_suffix")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]

    src = tmp_path / "src.md"
    src.write_text("# Implementation\n", encoding="utf-8")

    out = write_section(
        target / ".context" / "features",
        feature_id=feature_id,
        section="implementation.md",
        source_file=src,
    )
    assert out.name == "implementation.md"


@pytest.mark.integration
def test_write_section_rejects_bad_names(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "section_write_bad_name")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    src = tmp_path / "src.md"
    src.write_text("x", encoding="utf-8")

    for bad in ("", "../escape", ".hidden", "with/slash"):
        with pytest.raises(FeatureRenameError):
            write_section(
                target / ".context" / "features",
                feature_id=feature_id,
                section=bad,
                source_file=src,
            )


# ----- council log ----------------------------------------------------------


@pytest.mark.integration
def test_council_log_append_and_read(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "council_log_basic")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    features_dir = target / ".context" / "features"

    append_log(features_dir, feature_id=feature_id, stage=1, agent="architect", status="started")
    append_log(features_dir, feature_id=feature_id, stage=1, agent="architect", status="complete", note="all good")

    entries = read_log(features_dir, feature_id)
    assert len(entries) == 2
    assert entries[0].status == "started"
    assert entries[1].status == "complete"
    assert entries[1].note == "all good"


@pytest.mark.integration
def test_council_log_rejects_invalid_status(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "council_log_invalid")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    features_dir = target / ".context" / "features"
    with pytest.raises(CouncilLogError):
        append_log(features_dir, feature_id=feature_id, stage=1, agent="architect", status="winning")


@pytest.mark.integration
def test_council_log_stage_complete_tracks_all_agents(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "council_log_stage")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    features_dir = target / ".context" / "features"

    # Two of three agents complete — stage NOT complete.
    for agent in ("architect", "dev"):
        append_log(features_dir, feature_id=feature_id, stage=1, agent=agent, status="complete")
    append_log(features_dir, feature_id=feature_id, stage=1, agent="critic-database", status="started")
    assert not is_stage_complete(features_dir, feature_id, 1)

    # Now finish the DBA critic.
    append_log(features_dir, feature_id=feature_id, stage=1, agent="critic-database", status="complete")
    assert is_stage_complete(features_dir, feature_id, 1)


@pytest.mark.integration
def test_council_log_latest_status_returns_most_recent(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "council_log_latest")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    features_dir = target / ".context" / "features"

    append_log(features_dir, feature_id=feature_id, stage=2, agent="security", status="started")
    append_log(features_dir, feature_id=feature_id, stage=2, agent="security", status="failed")
    append_log(features_dir, feature_id=feature_id, stage=2, agent="security", status="complete")
    assert latest_status(features_dir, feature_id, 2, "security") == "complete"


# ----- CLI dispatch ---------------------------------------------------------


@pytest.mark.integration
def test_cli_flow_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_flow_remove")
    feature_id, flow_id = _first_feature_with_flow(target)
    monkeypatch.chdir(target)
    capsys.readouterr()

    rc = dispatch(["flow-remove", "--feature", feature_id, "--flow", flow_id])
    assert rc == 0
    assert "dropped" in capsys.readouterr().out


@pytest.mark.integration
def test_cli_flow_remove_requires_both_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_flow_remove_missing")
    monkeypatch.chdir(target)
    rc = dispatch(["flow-remove", "--feature", "x"])
    assert rc == 2
    assert "required" in capsys.readouterr().err


@pytest.mark.integration
def test_cli_section_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_section_write")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]

    src = tmp_path / "section.md"
    src.write_text("# Security\nA short take.\n", encoding="utf-8")

    monkeypatch.chdir(target)
    capsys.readouterr()
    rc = dispatch([
        "section-write",
        "--feature", feature_id,
        "--section", "security",
        "--from-file", str(src),
    ])
    assert rc == 0
    out = (target / ".context" / "features" / feature_id / "security.md").read_text()
    assert "A short take" in out


@pytest.mark.integration
def test_cli_council_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_council_log")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]

    monkeypatch.chdir(target)
    capsys.readouterr()
    rc = dispatch([
        "council-log",
        "--feature", feature_id,
        "--stage", "1",
        "--agent", "architect",
        "--status", "complete",
        "--note", "first pass",
    ])
    assert rc == 0
    log_path = (
        target / ".context" / "features" / feature_id / "council" / "_council-log.json"
    )
    assert log_path.exists()
    payload = json.loads(log_path.read_text())
    assert payload["entries"][-1]["agent"] == "architect"
    assert payload["entries"][-1]["status"] == "complete"
    assert payload["entries"][-1]["note"] == "first pass"


@pytest.mark.integration
def test_cli_council_log_rejects_bad_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_council_log_bad")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    monkeypatch.chdir(target)
    rc = dispatch([
        "council-log",
        "--feature", feature_id,
        "--stage", "1",
        "--agent", "architect",
        "--status", "winning",
    ])
    assert rc == 2
    assert "status must be" in capsys.readouterr().err
