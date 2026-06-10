"""Tests for ``context/build/reconcile.py`` — read-only drift detection.

Builds a tiny ``.context/`` + throwaway git repo under ``tmp_path`` by hand
so the mapping logic (changed file → owning feature, net-new → unassigned)
is exercised in isolation, without a full build_all.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.build.reconcile import (
    ReconcileReport,
    compute_reconcile_report,
    stamp_reconciled,
)
from dummyindex.context.domains.features import PENDING_ENRICHMENT_MARKER


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_index(context_dir: Path, indexed_commit: str | None) -> None:
    """Minimal meta.json + one feature owning ``auth.py``."""
    meta = {
        "schema_version": 1,
        "dummyindex_version": "0.15.2",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "root": str(context_dir.parent),
    }
    if indexed_commit is not None:
        meta["indexed_commit"] = indexed_commit
    _write_json(context_dir / "meta.json", meta)
    _write_json(
        context_dir / "features" / "auth" / "feature.json",
        {
            "schema_version": 1,
            "feature_id": "auth",
            "kind": "community",
            "name": "Authentication",
            "files": ["auth.py"],
        },
    )


@pytest.mark.unit
def test_no_indexed_commit_yields_empty_report(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    report = compute_reconcile_report(context_dir, tmp_path)
    assert report == ReconcileReport(indexed_commit=None)
    assert report.has_drift is False


@pytest.mark.unit
def test_non_git_with_anchor_degrades_to_empty(tmp_path: Path) -> None:
    # An anchor is recorded but the dir isn't a git repo → changed_paths
    # returns None → empty report, no raise.
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit="deadbeef")
    report = compute_reconcile_report(context_dir, tmp_path)
    assert report.drifted_features == ()
    assert report.unassigned_new_files == ()
    assert report.indexed_commit == "deadbeef"


@pytest.mark.unit
def test_changed_file_maps_to_owning_feature(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)

    # Modify the owned file and add a net-new file owned by nobody.
    (tmp_path / "auth.py").write_text("def login(): return True\n", encoding="utf-8")
    (tmp_path / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    report = compute_reconcile_report(context_dir, tmp_path)
    assert "auth" in report.drifted_features
    assert "newthing.py" in report.unassigned_new_files
    assert report.indexed_commit == anchor


@pytest.mark.unit
def test_pending_enrichment_marker_surfaces_independently_of_git(
    tmp_path: Path,
) -> None:
    """A placed-but-unenriched feature is reported even off-git / sans anchor.

    The ``awaiting_enrichment`` set drives the ``reconcile-stamp`` guard, so it
    must be visible regardless of the git delta (which short-circuits to empty
    when there's no anchor). ``has_drift`` flips True so the report reads as
    "work pending".
    """
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    marker = context_dir / "features" / "auth" / PENDING_ENRICHMENT_MARKER
    marker.write_text("awaiting enrichment\n", encoding="utf-8")

    report = compute_reconcile_report(context_dir, tmp_path)
    assert report.awaiting_enrichment == ("auth",)
    assert report.has_drift is True


@pytest.mark.unit
def test_removed_owned_file_drifts_feature_and_lists_removal(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)

    (tmp_path / "auth.py").unlink()

    report = compute_reconcile_report(context_dir, tmp_path)
    assert "auth" in report.drifted_features
    assert "auth.py" in report.removed_files


# ----- stamp_reconciled (the transactional boundary) ------------------------


def _committed_repo(tmp_path: Path) -> tuple[Path, str]:
    """A git repo with ``auth.py`` committed; returns ``(root, head_sha)``."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD").strip()


def _anchor(context_dir: Path) -> str | None:
    return json.loads((context_dir / "meta.json").read_text(encoding="utf-8")).get(
        "indexed_commit"
    )


@pytest.mark.unit
def test_stamp_advances_anchor_when_clean(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    # Seed a stale/unknown anchor so the report is empty (delta None) and the
    # stamp has a real HEAD to advance to.
    _seed_index(context_dir, indexed_commit="0" * 40)

    result = stamp_reconciled(context_dir, root)
    assert result.refused is False
    assert result.off_git is False
    assert result.stamped_commit == head
    assert _anchor(context_dir) == head


@pytest.mark.unit
def test_stamp_refused_on_unassigned_then_forced(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    # A net-new untracked file owned by nobody → unassigned → blocks.
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    refused = stamp_reconciled(context_dir, root)
    assert refused.refused is True
    assert refused.stamped_commit is None
    assert "newthing.py" in refused.report.unassigned_new_files
    assert _anchor(context_dir) == head  # unchanged

    forced = stamp_reconciled(context_dir, root, force=True)
    assert forced.refused is False
    assert forced.stamped_commit == head


@pytest.mark.unit
def test_stamp_refused_on_awaiting_enrichment(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (context_dir / "features" / "auth" / PENDING_ENRICHMENT_MARKER).write_text(
        "pending\n", encoding="utf-8"
    )

    result = stamp_reconciled(context_dir, root)
    assert result.refused is True
    assert "auth" in result.report.awaiting_enrichment


@pytest.mark.unit
def test_stamp_does_not_block_on_drift_only(tmp_path: Path) -> None:
    """Drift alone never blocks the stamp — only the stamp clears drift."""
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    # Modify the owned file → drifts `auth`, but no unassigned / awaiting.
    (root / "auth.py").write_text("def login(): return True\n", encoding="utf-8")

    result = stamp_reconciled(context_dir, root)
    assert result.refused is False
    assert result.stamped_commit == head
    assert "auth" in result.report.drifted_features
    assert result.dirty_source is True  # uncommitted source edit


@pytest.mark.unit
def test_stamp_off_git_is_noop(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    result = stamp_reconciled(context_dir, tmp_path)
    assert result.off_git is True
    assert result.stamped_commit is None
    assert _anchor(context_dir) is None


# ----- CLI front-ends -------------------------------------------------------


@pytest.mark.integration
def test_cli_reconcile_json_lists_unassigned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile", str(root), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["indexed_commit"] == head
    assert "newthing.py" in payload["unassigned_new_files"]
    assert payload["has_drift"] is True


@pytest.mark.integration
def test_cli_reconcile_stamp_refuses_then_forces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile-stamp", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err and "newthing.py" in err
    assert _anchor(context_dir) == head  # unchanged

    rc = dispatch(["reconcile-stamp", str(root), "--force"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "anchor advanced" in out
    assert "WARNING" in out  # forced past unassigned
