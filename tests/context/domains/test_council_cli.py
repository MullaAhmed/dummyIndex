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
from tests.paths import SAMPLE_REPO

_FIXTURE = SAMPLE_REPO


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
            (
                target / ".context" / "features" / entry["feature_id"] / "feature.json"
            ).read_text()
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

    append_log(
        features_dir,
        feature_id=feature_id,
        stage=1,
        agent="architect",
        status="started",
    )
    append_log(
        features_dir,
        feature_id=feature_id,
        stage=1,
        agent="architect",
        status="complete",
        note="all good",
    )

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
        append_log(
            features_dir,
            feature_id=feature_id,
            stage=1,
            agent="architect",
            status="winning",
        )


@pytest.mark.integration
def test_council_log_stage_complete_tracks_all_agents(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "council_log_stage")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    features_dir = target / ".context" / "features"

    # Two of three agents complete — stage NOT complete.
    for agent in ("architect", "dev"):
        append_log(
            features_dir, feature_id=feature_id, stage=1, agent=agent, status="complete"
        )
    append_log(
        features_dir,
        feature_id=feature_id,
        stage=1,
        agent="critic-database",
        status="started",
    )
    assert not is_stage_complete(features_dir, feature_id, 1)

    # Now finish the DBA critic.
    append_log(
        features_dir,
        feature_id=feature_id,
        stage=1,
        agent="critic-database",
        status="complete",
    )
    assert is_stage_complete(features_dir, feature_id, 1)


@pytest.mark.integration
def test_council_log_latest_status_returns_most_recent(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "council_log_latest")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]
    features_dir = target / ".context" / "features"

    append_log(
        features_dir, feature_id=feature_id, stage=2, agent="security", status="started"
    )
    append_log(
        features_dir, feature_id=feature_id, stage=2, agent="security", status="failed"
    )
    append_log(
        features_dir,
        feature_id=feature_id,
        stage=2,
        agent="security",
        status="complete",
    )
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
    src.write_text("# Concerns\nA short take.\n", encoding="utf-8")

    monkeypatch.chdir(target)
    capsys.readouterr()
    rc = dispatch(
        [
            "section-write",
            "--feature",
            feature_id,
            "--section",
            "concerns",
            "--from-file",
            str(src),
        ]
    )
    assert rc == 0
    out = (target / ".context" / "features" / feature_id / "concerns.md").read_text()
    assert "A short take" in out

    # v0.25.1: `--section security` no longer CREATES a stray sibling file on
    # a canonical-shaped feature — critique output belongs in concerns.md.
    rc = dispatch(
        [
            "section-write",
            "--feature",
            feature_id,
            "--section",
            "security",
            "--from-file",
            str(src),
        ]
    )
    capsys.readouterr()
    assert rc == 2
    assert not (target / ".context" / "features" / feature_id / "security.md").exists()


@pytest.mark.integration
def test_cli_council_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_council_log")
    idx = json.loads((target / ".context" / "features" / "INDEX.json").read_text())
    feature_id = idx["features"][0]["feature_id"]

    monkeypatch.chdir(target)
    capsys.readouterr()
    rc = dispatch(
        [
            "council-log",
            "--feature",
            feature_id,
            "--stage",
            "1",
            "--agent",
            "architect",
            "--status",
            "complete",
            "--note",
            "first pass",
        ]
    )
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
    rc = dispatch(
        [
            "council-log",
            "--feature",
            feature_id,
            "--stage",
            "1",
            "--agent",
            "architect",
            "--status",
            "winning",
        ]
    )
    assert rc == 2
    assert "status must be" in capsys.readouterr().err


# ----- council-log backfill --------------------------------------------------


def _hand_built_feature(tmp_path: Path, feature_id: str, *, enriched: bool) -> Path:
    """A minimal features dir + one feature, no ingest needed."""
    features_dir = tmp_path / ".context" / "features"
    fdir = features_dir / feature_id
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "feature.json").write_text(
        json.dumps({"feature_id": feature_id, "files": ["x.py"]}), encoding="utf-8"
    )
    if enriched:
        (fdir / "spec.md").write_text("# Real spec\n\nProse.\n", encoding="utf-8")
        (fdir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    index_path = features_dir / "INDEX.json"
    existing = (
        json.loads(index_path.read_text(encoding="utf-8"))["features"]
        if index_path.exists()
        else []
    )
    index_path.write_text(
        json.dumps({"features": existing + [{"feature_id": feature_id}]}),
        encoding="utf-8",
    )
    return features_dir


def test_cli_council_log_backfill_single_feature(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    features_dir = _hand_built_feature(tmp_path, "legacy", enriched=True)
    rc = dispatch(
        [
            "council-log",
            "backfill",
            "--feature",
            "legacy",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert "legacy" in capsys.readouterr().out
    entries = read_log(features_dir, "legacy")
    assert [(e.stage, e.agent, e.status) for e in entries] == [
        (1, "backfill", "complete"),
        (2, "backfill", "complete"),
    ]
    assert all(e.note == "backfilled-from-artifacts" for e in entries)


def test_cli_council_log_backfill_all_features_from_index(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _hand_built_feature(tmp_path, "legacy-a", enriched=True)
    features_dir = _hand_built_feature(tmp_path, "fresh-b", enriched=False)
    rc = dispatch(["council-log", "backfill", "--root", str(tmp_path)])
    capsys.readouterr()
    assert rc == 0
    assert len(read_log(features_dir, "legacy-a")) == 2
    assert read_log(features_dir, "fresh-b") == []


def test_cli_council_log_backfill_unknown_feature_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _hand_built_feature(tmp_path, "legacy", enriched=True)
    rc = dispatch(
        [
            "council-log",
            "backfill",
            "--feature",
            "ghost",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 2
    assert "ghost" in capsys.readouterr().err


# ----- section-write canonical-name guard ------------------------------------


def _section_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A hand-built repo root + a source markdown for section-write tests."""
    features_dir = tmp_path / ".context" / "features"
    (features_dir / "feat-x").mkdir(parents=True)
    src = tmp_path / "draft.md"
    src.write_text("# Draft\n\nBody.\n", encoding="utf-8")
    return tmp_path, src


def test_cli_section_write_canonical_section_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, src = _section_repo(tmp_path)
    rc = dispatch(
        [
            "section-write",
            "--feature",
            "feat-x",
            "--section",
            "concerns",
            "--from-file",
            str(src),
            "--root",
            str(root),
        ]
    )
    capsys.readouterr()
    assert rc == 0
    assert (root / ".context" / "features" / "feat-x" / "concerns.md").is_file()


def test_cli_section_write_rejects_new_legacy_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--section security` must not CREATE a stray sibling next to
    concerns.md — the canonical home for critique output is concerns."""
    root, src = _section_repo(tmp_path)
    rc = dispatch(
        [
            "section-write",
            "--feature",
            "feat-x",
            "--section",
            "security",
            "--from-file",
            str(src),
            "--root",
            str(root),
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "concerns" in err
    assert not (root / ".context" / "features" / "feat-x" / "security.md").exists()


def test_cli_section_write_updates_existing_legacy_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, src = _section_repo(tmp_path)
    legacy = root / ".context" / "features" / "feat-x" / "security.md"
    legacy.write_text("old\n", encoding="utf-8")
    rc = dispatch(
        [
            "section-write",
            "--feature",
            "feat-x",
            "--section",
            "security",
            "--from-file",
            str(src),
            "--root",
            str(root),
        ]
    )
    capsys.readouterr()
    assert rc == 0
    assert "Body." in legacy.read_text(encoding="utf-8")


def test_cli_section_write_rejects_arbitrary_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, src = _section_repo(tmp_path)
    rc = dispatch(
        [
            "section-write",
            "--feature",
            "feat-x",
            "--section",
            "notes",
            "--from-file",
            str(src),
            "--root",
            str(root),
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "spec" in err and "plan" in err and "concerns" in err
    assert not (root / ".context" / "features" / "feat-x" / "notes.md").exists()


def test_cli_section_write_allow_new_section_overrides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, src = _section_repo(tmp_path)
    rc = dispatch(
        [
            "section-write",
            "--feature",
            "feat-x",
            "--section",
            "notes",
            "--from-file",
            str(src),
            "--root",
            str(root),
            "--allow-new-section",
        ]
    )
    capsys.readouterr()
    assert rc == 0
    assert (root / ".context" / "features" / "feat-x" / "notes.md").is_file()
