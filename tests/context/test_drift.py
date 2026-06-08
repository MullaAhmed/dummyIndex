"""Tests for the SessionStart drift detector and the `plan-update` CLI verb.

The drift detector compares the mtime of every source file in
``.context/features/<id>/feature.json#files`` against the mtime of the
feature's prose docs (``architecture.md``, ``data-model.md``, …). A
source is "drifting" when it's newer than every prose doc in its
feature folder. Editing a doc updates its mtime and naturally clears
the drift signal (heuristic decay — no explicit stamp needed).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.features import PENDING_ENRICHMENT_MARKER
from dummyindex.context.drift import (
    DriftReport,
    DriftRow,
    compute_drift,
    render_drift_summary,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(path), check=True, capture_output=True, text=True
    ).stdout


def _seed_meta(project_root: Path, indexed_commit: str) -> None:
    (project_root / ".context" / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dummyindex_version": "0.15.3",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "root": str(project_root),
                "indexed_commit": indexed_commit,
            }
        ),
        encoding="utf-8",
    )


def _make_feature(
    project_root: Path,
    feature_id: str,
    *,
    files: list[str],
    docs: tuple[str, ...] = ("architecture.md",),
) -> Path:
    """Stand up a minimal .context/features/<feature_id>/ folder."""
    feature_dir = project_root / ".context" / "features" / feature_id
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "feature.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_id": feature_id,
                "kind": "community",
                "name": feature_id,
                "files": files,
                "members": [],
                "entry_points": [],
                "flow_ids": [],
            }
        ),
        encoding="utf-8",
    )
    for name in docs:
        (feature_dir / name).write_text(f"# {feature_id} {name}\n", encoding="utf-8")
    return feature_dir


def _touch(path: Path, *, mtime: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# placeholder\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))


# ----- compute_drift -------------------------------------------------------


@pytest.mark.integration
def test_empty_report_when_no_context_dir(tmp_path: Path) -> None:
    report = compute_drift(tmp_path)
    assert report == DriftReport(rows=())
    assert not report.has_drift


@pytest.mark.integration
def test_empty_report_when_no_features(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    report = compute_drift(tmp_path)
    assert not report.has_drift


@pytest.mark.integration
def test_drift_when_source_newer_than_arch_doc(tmp_path: Path) -> None:
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=1000.0)
    feature_dir = _make_feature(
        tmp_path, "service-loop", files=["app/service.py"]
    )
    _touch(feature_dir / "architecture.md", mtime=500.0)

    report = compute_drift(tmp_path)
    assert report.rows == (DriftRow(rel_path="app/service.py", feature_id="service-loop"),)


@pytest.mark.integration
def test_no_drift_when_doc_newer_than_source(tmp_path: Path) -> None:
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=500.0)
    feature_dir = _make_feature(
        tmp_path, "service-loop", files=["app/service.py"]
    )
    _touch(feature_dir / "architecture.md", mtime=1000.0)

    report = compute_drift(tmp_path)
    assert not report.has_drift


@pytest.mark.integration
def test_any_feature_doc_suppresses_drift(tmp_path: Path) -> None:
    """A fresh security.md is enough — we take the max mtime across docs."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=500.0)
    feature_dir = _make_feature(
        tmp_path,
        "service-loop",
        files=["app/service.py"],
        docs=("architecture.md", "security.md"),
    )
    _touch(feature_dir / "architecture.md", mtime=200.0)
    _touch(feature_dir / "security.md", mtime=1000.0)

    report = compute_drift(tmp_path)
    assert not report.has_drift


@pytest.mark.integration
def test_v014_spec_or_plan_suppresses_drift(tmp_path: Path) -> None:
    """A fresh `spec.md`/`plan.md` (the v0.14 doc names) clears drift just
    like the legacy essay docs — they were added to _FEATURE_DOC_NAMES."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=500.0)
    feature_dir = _make_feature(
        tmp_path,
        "service-loop",
        files=["app/service.py"],
        docs=("spec.md", "plan.md"),
    )
    _touch(feature_dir / "spec.md", mtime=200.0)
    _touch(feature_dir / "plan.md", mtime=1000.0)

    report = compute_drift(tmp_path)
    assert not report.has_drift


@pytest.mark.integration
def test_drift_when_feature_has_no_docs(tmp_path: Path) -> None:
    """A scaffolded feature with no prose docs yet → every source is drift."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=1000.0)
    _make_feature(
        tmp_path, "service-loop", files=["app/service.py"], docs=()
    )
    report = compute_drift(tmp_path)
    assert report.has_drift


@pytest.mark.integration
def test_drift_one_file_two_features(tmp_path: Path) -> None:
    """When a file lives in two features, drift is reported per feature."""
    src = tmp_path / "shared.py"
    _touch(src, mtime=1000.0)
    feat_a = _make_feature(tmp_path, "feat-a", files=["shared.py"])
    feat_b = _make_feature(tmp_path, "feat-b", files=["shared.py"])
    _touch(feat_a / "architecture.md", mtime=500.0)
    _touch(feat_b / "architecture.md", mtime=500.0)

    report = compute_drift(tmp_path)
    feature_ids = {r.feature_id for r in report.rows}
    assert feature_ids == {"feat-a", "feat-b"}


@pytest.mark.integration
def test_drift_clears_after_doc_edit(tmp_path: Path) -> None:
    """Editing a feature doc bumps its mtime → drift signal goes quiet."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=1000.0)
    feature_dir = _make_feature(
        tmp_path, "service-loop", files=["app/service.py"]
    )
    _touch(feature_dir / "architecture.md", mtime=500.0)
    assert compute_drift(tmp_path).has_drift

    # Agent updates the doc.
    _touch(feature_dir / "architecture.md", mtime=1500.0)
    assert not compute_drift(tmp_path).has_drift


# ----- commit-anchored signals (augment mtime drift) ----------------------


@pytest.mark.integration
def test_compute_drift_surfaces_unassigned_and_awaiting(tmp_path: Path) -> None:
    """When the index has an anchor, drift gains the two signals mtime can't
    see: net-new files owned by no feature, and placed-but-unenriched features."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    head = _git(tmp_path, "rev-parse", "HEAD").strip()

    _make_feature(tmp_path, "auth", files=["auth.py"], docs=("spec.md",))
    _seed_meta(tmp_path, head)
    # A net-new untracked file (owned by no feature) + a placed-but-unenriched
    # feature carrying the marker.
    (tmp_path / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")
    (tmp_path / ".context" / "features" / "auth" / PENDING_ENRICHMENT_MARKER).write_text(
        "pending\n", encoding="utf-8"
    )

    report = compute_drift(tmp_path)
    assert "newthing.py" in report.unassigned_new_files
    assert "auth" in report.awaiting_enrichment
    assert report.has_drift is True


@pytest.mark.integration
def test_compute_drift_off_git_has_no_unassigned(tmp_path: Path) -> None:
    """Off-git (no anchor): mtime drift only; unassigned needs a git diff."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=1000.0)
    feature_dir = _make_feature(tmp_path, "svc", files=["app/service.py"])
    _touch(feature_dir / "architecture.md", mtime=500.0)

    report = compute_drift(tmp_path)
    assert report.has_drift is True  # mtime drift
    assert report.unassigned_new_files == ()


@pytest.mark.integration
def test_compute_drift_off_git_still_sees_awaiting_marker(tmp_path: Path) -> None:
    """awaiting_enrichment is marker-based, so it works even off-git / sans anchor."""
    feature_dir = _make_feature(tmp_path, "placed", files=["app/x.py"], docs=("spec.md",))
    (feature_dir / PENDING_ENRICHMENT_MARKER).write_text("pending\n", encoding="utf-8")

    report = compute_drift(tmp_path)
    assert report.awaiting_enrichment == ("placed",)
    assert report.unassigned_new_files == ()  # needs a git diff — none off-git


# ----- render_drift_summary ----------------------------------------------


def test_render_empty_report_returns_empty_string() -> None:
    assert render_drift_summary(DriftReport(rows=())) == ""


def test_render_includes_unassigned_and_awaiting_sections() -> None:
    report = DriftReport(
        rows=(),
        unassigned_new_files=("pkg/new.py",),
        awaiting_enrichment=("placed-feat",),
    )
    text = render_drift_summary(report)
    assert text  # signals-only report still renders
    assert "pkg/new.py" in text
    assert "placed-feat" in text
    assert "--recouncil" in text
    # No run of ≥2 blank lines (signals-only path collapses header+section gap).
    assert "\n\n\n" not in text


def test_render_combined_mtime_and_signals_has_all_sections() -> None:
    """All three signals together → all three sections + the reconcile note."""
    report = DriftReport(
        rows=(DriftRow(rel_path="a.py", feature_id="feat-x"),),
        unassigned_new_files=("pkg/new.py",),
        awaiting_enrichment=("placed-feat",),
    )
    text = render_drift_summary(report)
    assert "feat-x" in text and "a.py" in text          # mtime section
    assert "New files not yet in any feature" in text     # unassigned section
    assert "Features awaiting enrichment" in text          # awaiting section
    assert "--recouncil" in text                           # trailing note
    assert "\n\n\n" not in text


def test_render_groups_by_feature() -> None:
    report = DriftReport(rows=(
        DriftRow(rel_path="a.py", feature_id="feat-x"),
        DriftRow(rel_path="b.py", feature_id="feat-x"),
        DriftRow(rel_path="c.py", feature_id="feat-y"),
    ))
    text = render_drift_summary(report)
    assert "drift report" in text
    assert "feat-x" in text and "a.py, b.py" in text
    assert "feat-y" in text and "c.py" in text


# ----- CLI dispatch -------------------------------------------------------


@pytest.mark.integration
def test_plan_update_silent_when_no_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """SessionStart hook contract: empty stdout when nothing is stale."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=500.0)
    feature_dir = _make_feature(
        tmp_path, "service-loop", files=["app/service.py"]
    )
    _touch(feature_dir / "architecture.md", mtime=1000.0)

    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.integration
def test_plan_update_prints_when_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=1000.0)
    feature_dir = _make_feature(
        tmp_path, "service-loop", files=["app/service.py"]
    )
    _touch(feature_dir / "architecture.md", mtime=500.0)

    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "drift report" in out
    assert "service-loop" in out
    assert "app/service.py" in out


@pytest.mark.integration
def test_plan_update_silent_when_no_context_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Random repo with no .context/ → no-op exit 0, no output."""
    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.integration
def test_plan_update_rejects_unknown_arg(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(["plan-update", "--root", str(tmp_path), "--unknown"])
    assert rc == 2
    assert "unknown argument" in capsys.readouterr().err
