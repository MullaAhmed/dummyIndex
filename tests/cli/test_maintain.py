"""Tests for ``context maintain`` — verb wiring, scope guard, ``--all``.

Drives the real dispatcher over a hand-built throwaway git repo (the same
fixture style as ``tests/context/build/test_reconcile.py``): two committed,
feature-owned source files get modified so the reconcile report shows drift,
then every verb is exercised against it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture()
def drifted_repo(tmp_path: Path) -> Path:
    """A git repo whose two committed files are owned by two features and now
    modified — the reconcile report lists both as drifted."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    (tmp_path / "db.py").write_text("def query(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")

    context_dir = tmp_path / ".context"
    meta = {
        "schema_version": 1,
        "dummyindex_version": "0.0.0-test",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "root": str(tmp_path),
        "indexed_commit": _git(tmp_path, "rev-parse", "HEAD").strip(),
    }
    context_dir.mkdir(parents=True)
    (context_dir / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    for fid, owned in (("auth", "auth.py"), ("db", "db.py")):
        fdir = context_dir / "features" / fid
        fdir.mkdir(parents=True)
        (fdir / "feature.json").write_text(
            json.dumps({"schema_version": 1, "feature_id": fid, "files": [owned]}),
            encoding="utf-8",
        )

    (tmp_path / "auth.py").write_text("def login(): return True\n", encoding="utf-8")
    (tmp_path / "db.py").write_text("def query(): return []\n", encoding="utf-8")
    return tmp_path


def _run(root: Path, *args: str) -> tuple[int, str, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = dispatch(["maintain", *args, "--root", str(root)])
    return rc, out.getvalue(), err.getvalue()


@pytest.mark.unit
def test_plan_prints_ordered_features_with_estimates(drifted_repo: Path) -> None:
    rc, out, _ = _run(drifted_repo, "plan")
    assert rc == 0
    assert "ordered work list" in out
    # Execution order: drifted features in report order.
    assert out.index("auth") < out.index("db")
    assert "estimate:" in out
    assert "heuristic" in out  # clearly-labelled, never a wall-clock promise


@pytest.mark.unit
def test_plan_max_features_truncates_and_flags_it(drifted_repo: Path) -> None:
    rc, out, _ = _run(drifted_repo, "plan", "--max-features", "1")
    assert rc == 0
    assert "truncated by --max-features" in out


@pytest.mark.unit
def test_begin_refuses_without_scope_or_all(drifted_repo: Path) -> None:
    rc, _, err = _run(drifted_repo, "begin")
    assert rc == 2
    assert "--max-features" in err and "--all" in err
    assert not (drifted_repo / ".context" / "fleet").exists()


@pytest.mark.unit
def test_begin_writes_run_state_and_manifest(drifted_repo: Path) -> None:
    rc, out, _ = _run(drifted_repo, "begin", "--all")
    assert rc == 0
    run_dirs = list((drifted_repo / ".context" / "fleet").glob("maintain-*"))
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "RUN.md").is_file()
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert [f["feature_id"] for f in payload["features"]] == ["auth", "db"]


@pytest.mark.unit
def test_begin_json_reports_created_run(drifted_repo: Path) -> None:
    rc, out, _ = _run(drifted_repo, "begin", "--max-features", "1", "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["created"] is True
    assert payload["total"] == 5  # one feature x standard's five active stages


@pytest.mark.unit
def test_next_returns_earliest_incomplete_unit(drifted_repo: Path) -> None:
    _rc, _out, _err = _run(drifted_repo, "begin", "--all")
    rc, out, _ = _run(drifted_repo, "next", "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["complete"] is False
    assert payload["unit"]["stage"] == 1
    assert payload["counts"]["pending"] == 10  # 2 features x 5 stages


@pytest.mark.unit
def test_done_then_status_advance_counts(drifted_repo: Path) -> None:
    _rc, _out, _err = _run(drifted_repo, "begin", "--all")
    rc, out, _ = _run(drifted_repo, "done", "--feature", "auth", "--stage", "1")
    assert rc == 0
    rc, out, _ = _run(drifted_repo, "status", "--json")
    assert rc == 0
    counts = json.loads(out)
    assert counts["done"] == 1
    assert counts["pending"] == 9


@pytest.mark.unit
def test_done_without_stage_takes_earliest_pending(drifted_repo: Path) -> None:
    _rc, _out, _err = _run(drifted_repo, "begin", "--all")
    _run(drifted_repo, "done", "--feature", "auth")  # stage 1 implied
    _rc, out, _ = _run(drifted_repo, "next", "--json")
    payload = json.loads(out)
    # db/stage 1 wins the stage-major frontier over auth/stage 2.
    assert (payload["unit"]["feature_id"], payload["unit"]["stage"]) == ("db", 1)


@pytest.mark.unit
def test_stamp_wraps_reconcile_stamp_and_ticks_units(drifted_repo: Path) -> None:
    _rc, _out, _err = _run(drifted_repo, "begin", "--max-features", "1")
    rc, out, _ = _run(drifted_repo, "stamp", "--feature", "auth")
    assert rc == 0
    assert "ticked" in out
    # The anchor really advanced (stamp wrapped reconcile-stamp).
    meta = json.loads((drifted_repo / ".context" / "meta.json").read_text("utf-8"))
    head = _git(drifted_repo, "rev-parse", "HEAD").strip()
    assert meta["indexed_commit"] == head
    # The feature's units are all done in persisted state.
    run_dir = next((drifted_repo / ".context" / "fleet").glob("maintain-*"))
    payload = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    statuses = [s["status"] for s in payload["features"][0]["stages"]]
    assert statuses == ["done"] * len(statuses)


@pytest.mark.unit
def test_resume_via_default_newest_run(drifted_repo: Path) -> None:
    _rc, _out, _err = _run(drifted_repo, "begin", "--all")
    _run(drifted_repo, "done", "--feature", "auth", "--stage", "1")
    # No --run anywhere: discovery picks the newest maintain-* dir.
    rc, out, _ = _run(drifted_repo, "next")
    assert rc == 0
    assert "db/stage 1" in out  # auth/stage 1 done; frontier moved on


@pytest.mark.unit
def test_unknown_verb_is_a_usage_error() -> None:
    rc, _, _ = _run(Path("."), "frobnicate")
    assert rc == 2


@pytest.mark.unit
def test_missing_context_errors(tmp_path: Path) -> None:
    rc, _, err = _run(tmp_path, "status")
    assert rc == 2
    assert "not found" in err
