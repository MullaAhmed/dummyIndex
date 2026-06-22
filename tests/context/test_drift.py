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
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.features import PENDING_ENRICHMENT_MARKER
from dummyindex.context.drift import (
    DriftReport,
    DriftRow,
    compute_badge,
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


# ----- render: file vs (feature,file) row count -----------------------------


@pytest.mark.unit
def test_render_counts_unique_files_not_rows() -> None:
    """One shared file owned by 3 features renders '1 source file across 3
    features', not '3 source files'."""
    report = DriftReport(
        rows=(
            DriftRow(rel_path="shared.py", feature_id="a"),
            DriftRow(rel_path="shared.py", feature_id="b"),
            DriftRow(rel_path="shared.py", feature_id="c"),
        )
    )
    out = render_drift_summary(report)
    assert "1 source file across 3 features" in out


@pytest.mark.unit
def test_render_recouncil_hint_is_scoped(tmp_path: Path) -> None:
    """Rendered hints must point at the scoped, per-feature form / procedure,
    never the forbidden bare `/dummyindex --recouncil`."""
    report = DriftReport(rows=(), unassigned_new_files=("new/x.py",))
    out = render_drift_summary(report)
    assert "--recouncil <feature-id>" in out or "65-reconcile.md" in out


# ----- manifest content cross-check (git-operation false positives) ---------


def _write_manifest_for(project_root: Path, files: list[str]) -> None:
    """Record the current sha256/size/mtime of ``files`` in the manifest."""
    from dummyindex.context.build.manifest import write_manifest

    write_manifest(
        project_root / ".context",
        root=project_root,
        files=[project_root / f for f in files],
    )


@pytest.mark.integration
def test_no_mtime_row_when_sha_matches_manifest(tmp_path: Path) -> None:
    """A source whose mtime is newer than the docs but whose CONTENT is
    unchanged (sha matches the manifest) is NOT drift — kills the
    git-checkout/pull/rebase false-positive class."""
    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    feature_dir = _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    # Manifest captures the current content sha.
    _write_manifest_for(tmp_path, ["app/service.py"])
    # Now make the source mtime newer than every doc (simulating a git op that
    # rewrote the working tree) WITHOUT changing the bytes.
    _touch(feature_dir / "architecture.md", mtime=500.0)
    os.utime(src, (1_000.0, 1_000.0))

    report = compute_drift(tmp_path)
    assert not report.has_drift


@pytest.mark.integration
def test_mtime_row_kept_when_content_changed(tmp_path: Path) -> None:
    """When the bytes actually changed, the manifest sha differs and the row
    survives the cross-check."""
    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    feature_dir = _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    _write_manifest_for(tmp_path, ["app/service.py"])
    # Real content change after the manifest was written.
    src.write_text("def f(): return 2\n", encoding="utf-8")
    _touch(feature_dir / "architecture.md", mtime=500.0)
    os.utime(src, (1_000.0, 1_000.0))

    report = compute_drift(tmp_path)
    assert report.rows == (
        DriftRow(rel_path="app/service.py", feature_id="service-loop"),
    )


@pytest.mark.integration
def test_absent_manifest_preserves_legacy_mtime_behavior(tmp_path: Path) -> None:
    """With no manifest, the mtime heuristic stands alone (back-compat)."""
    src = tmp_path / "app" / "service.py"
    _touch(src, mtime=1000.0)
    feature_dir = _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    _touch(feature_dir / "architecture.md", mtime=500.0)
    # No manifest written.
    report = compute_drift(tmp_path)
    assert report.rows == (
        DriftRow(rel_path="app/service.py", feature_id="service-loop"),
    )


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


# ----- compute_badge (pure statusline string) ----------------------------


@pytest.mark.unit
def test_compute_badge_fresh_when_no_drift() -> None:
    """An empty report renders the fresh badge — no count."""
    assert compute_badge(DriftReport(rows=())) == "[ctx ✓]"


@pytest.mark.unit
def test_compute_badge_counts_distinct_files_not_rows() -> None:
    """Two distinct drifted files spread across several (feature, file) pairings
    count once each — mirrors `_render_mtime_section`'s distinct-file count."""
    report = DriftReport(
        rows=(
            DriftRow(rel_path="a.py", feature_id="feat-x"),
            DriftRow(rel_path="a.py", feature_id="feat-y"),  # same file, 2nd feature
            DriftRow(rel_path="b.py", feature_id="feat-x"),
        )
    )
    assert compute_badge(report) == "[ctx: 2 drift]"


@pytest.mark.unit
def test_compute_badge_includes_unassigned_and_awaiting() -> None:
    """Unassigned new files and awaiting-enrichment features each add to N."""
    report = DriftReport(
        rows=(DriftRow(rel_path="a.py", feature_id="feat-x"),),
        unassigned_new_files=("pkg/new.py",),
        awaiting_enrichment=("placed-feat",),
    )
    assert compute_badge(report) == "[ctx: 3 drift]"


# ----- drifted_features propagation (commit-anchored, F6) ------------------


def _stamp_real_anchor(project_root: Path) -> str:
    """Stand up a REAL stamped, anchored ``.context/`` over a git repo and
    return the stamped sha (the exact write path the ``reconcile-stamp`` verb
    drives, via ``stamp_reconciled``)."""
    from dummyindex.context.build.meta import new_meta, write_meta
    from dummyindex.context.build.reconcile import stamp_reconciled

    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "t@t.t")
    _git(project_root, "config", "user.name", "t")
    (project_root / "auth.py").write_text("def login(): return 1\n", encoding="utf-8")
    _git(project_root, "add", "-A")
    _git(project_root, "commit", "-qm", "init")

    context_dir = project_root / ".context"
    feat = _make_feature(project_root, "auth", files=["auth.py"], docs=("spec.md",))
    del feat
    write_meta(context_dir / "meta.json", new_meta(project_root, "0.28.0"))

    result = stamp_reconciled(context_dir, project_root)
    assert result.stamped_commit is not None and not result.refused
    return result.stamped_commit


@pytest.mark.integration
def test_compute_drift_populates_drifted_features(tmp_path: Path) -> None:
    """On a genuinely stamped, anchored repo, a committed modification of a file
    owned by a feature surfaces in ``DriftReport.drifted_features`` — the
    commit-anchored signal mtime cannot see on an anchored repo (F6)."""
    _stamp_real_anchor(tmp_path)

    # Modify + commit the owned file → drift against the stamped anchor.
    (tmp_path / "auth.py").write_text("def login(): return 2\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "change auth")

    report = compute_drift(tmp_path)
    assert "auth" in report.drifted_features
    assert report.has_drift is True


@pytest.mark.unit
def test_has_drift_true_when_only_drifted_features() -> None:
    """``has_drift`` is True when ONLY ``drifted_features`` is set (no mtime
    rows, no unassigned, no awaiting)."""
    report = DriftReport(rows=(), drifted_features=("auth",))
    assert report.has_drift is True


@pytest.mark.unit
def test_compute_badge_dedupes_drifted_against_mtime() -> None:
    """A feature named by BOTH an mtime row and ``drifted_features`` is counted
    once — the badge de-duplicates drifted_features against ``by_feature()``."""
    # auth.py is the only distinct mtime file; feature "auth" is also drifted.
    report = DriftReport(
        rows=(DriftRow(rel_path="auth.py", feature_id="auth"),),
        drifted_features=("auth",),
    )
    # 1 distinct mtime file + 0 extra drifted (auth already in by_feature) = 1.
    assert compute_badge(report) == "[ctx: 1 drift]"


@pytest.mark.unit
def test_compute_badge_counts_extra_drifted_feature() -> None:
    """A drifted feature NOT already surfaced by an mtime row adds to the count."""
    report = DriftReport(
        rows=(DriftRow(rel_path="auth.py", feature_id="auth"),),
        drifted_features=("auth", "billing"),  # billing is extra
    )
    # 1 distinct mtime file + 1 extra drifted (billing) = 2.
    assert compute_badge(report) == "[ctx: 2 drift]"


@pytest.mark.unit
def test_render_drift_summary_dedupes_drifted_against_mtime() -> None:
    """``render_drift_summary`` does not print a separate committed-modifications
    entry for a feature already named by the mtime section (de-duplicated)."""
    report = DriftReport(
        rows=(DriftRow(rel_path="auth.py", feature_id="auth"),),
        drifted_features=("auth",),
    )
    text = render_drift_summary(report)
    assert "auth" in text
    # The feature is in the mtime section, not double-listed under committed mods.
    assert "Features with committed modifications" not in text


@pytest.mark.unit
def test_render_drift_summary_renders_extra_drifted_feature() -> None:
    """A drifted feature NOT named by the mtime section gets its own
    committed-modifications entry."""
    report = DriftReport(
        rows=(DriftRow(rel_path="auth.py", feature_id="auth"),),
        drifted_features=("auth", "billing"),
    )
    text = render_drift_summary(report)
    assert "Features with committed modifications" in text
    assert "billing" in text


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
