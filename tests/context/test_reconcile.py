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

from dummyindex.context.build.reconcile import (
    ReconcileReport,
    compute_reconcile_report,
)


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
