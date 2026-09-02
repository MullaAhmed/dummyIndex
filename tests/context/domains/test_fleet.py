"""Tests for ``context/domains/fleet.py`` — maintain run state.

Pure domain tests over hand-built ``.context/`` shapes under ``tmp_path``:
create → next → done → status progression, resume semantics (done units are
never repeated), ``maintain-`` prefix scoping, atomic persistence, and the
corrupt-state refusal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.fleet import (
    FLEET_DIR_REL,
    MAINTAIN_RUN_PREFIX,
    FleetRunError,
    UnitStatus,
    create_run,
    estimate_run,
    find_newest_run,
    load_run,
    mark_done,
    next_unit,
    resolve_run_dir,
    run_status,
)

_STAGES = ((1, "specify"), (2, "plan"), (3, "critique"))


def _make_run(tmp_path: Path, features: tuple[str, ...] = ("auth",)) -> object:
    context_dir = tmp_path / ".context"
    return create_run(
        context_dir,
        features,
        {fid: 3 for fid in features},
        mode="standard",
        anchor_sha="a" * 40,
        stages_for_feature={fid: _STAGES for fid in features},
    )


@pytest.mark.unit
def test_create_run_writes_committed_state_and_manifest(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    state_path = run.run_dir / "state.json"
    manifest_path = run.run_dir / "RUN.md"
    assert state_path.is_file() and manifest_path.is_file()
    assert run.run_dir.parent.name == FLEET_DIR_REL
    assert run.run_dir.name.startswith(MAINTAIN_RUN_PREFIX)

    raw = json.loads(state_path.read_text(encoding="utf-8"))
    assert raw["kind"] == "maintain"
    assert raw["anchor_sha"] == "a" * 40
    assert [f["feature_id"] for f in raw["features"]] == ["auth"]
    assert [s["stage"] for s in raw["features"][0]["stages"]] == [1, 2, 3]
    assert all(s["status"] == "pending" for s in raw["features"][0]["stages"])
    # RUN.md is a human-readable mirror of the same order.
    assert "auth" in manifest_path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_create_run_rejects_empty_feature_list(tmp_path: Path) -> None:
    with pytest.raises(FleetRunError):
        create_run(tmp_path / ".context", ())


@pytest.mark.unit
def test_next_unit_returns_earliest_stage_then_feature_order(tmp_path: Path) -> None:
    run = _make_run(tmp_path, ("auth", "db"))
    unit = next_unit(run)
    assert (unit.feature_id, unit.stage) == ("auth", 1)


@pytest.mark.unit
def test_done_and_next_walk_the_frontier_without_repeats(tmp_path: Path) -> None:
    run = _make_run(tmp_path, ("auth", "db"))
    run = mark_done(run, "auth", 1)
    unit = next_unit(run)
    # Stage 1 is still incomplete overall — db owns the frontier now.
    assert (unit.feature_id, unit.stage) == ("db", 1)
    run = mark_done(run, "db", 1)
    assert next_unit(run).stage == 2


@pytest.mark.unit
def test_mark_done_persists_atomically_and_is_idempotent(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    updated = mark_done(run, "auth", 2)
    on_disk = load_run(updated.run_dir)
    assert on_disk.features[0].stages[1].status is UnitStatus.DONE
    # Idempotent re-mark: same status → no-op run returned, file unchanged.
    again = mark_done(on_disk, "auth", 2)
    assert again.updated_at == on_disk.updated_at


@pytest.mark.unit
def test_mark_done_rejects_unknown_unit(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    with pytest.raises(FleetRunError):
        mark_done(run, "nope", 1)
    with pytest.raises(FleetRunError):
        mark_done(run, "auth", 9)


@pytest.mark.unit
def test_status_counts_elapsed_and_labelled_heuristic(tmp_path: Path) -> None:
    import datetime as dt

    run = _make_run(tmp_path)
    created = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)
    run = create_run(
        tmp_path / ".context",
        ("auth",),
        None,
        mode="light",
        anchor_sha=None,
        stages_for_feature={"auth": _STAGES},
        now=created,
    )
    run = mark_done(run, "auth", 1)
    counts = run_status(run)
    assert counts["total"] == 3
    assert counts["done"] == 1
    assert counts["pending"] == 2
    assert counts["skipped"] == 0
    assert counts["complete"] is False
    assert counts["elapsed_seconds"] >= 120
    # The remaining estimate is the labelled units x 90s heuristic only.
    assert counts["estimated_remaining_seconds_heuristic"] == 2 * 90


@pytest.mark.unit
def test_status_complete_when_every_unit_terminal(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    for stage in (1, 2, 3):
        run = mark_done(run, "auth", stage)
    counts = run_status(run)
    assert counts["pending"] == 0 and counts["complete"] is True
    assert next_unit(run) is None


@pytest.mark.unit
def test_resume_from_corrupt_state_never_repeats_done_units(
    tmp_path: Path,
) -> None:
    """Kill simulation: a later unit flipped back to pending must not rewind
    the frontier below already-done units."""
    run = _make_run(tmp_path)
    for stage in (1, 2, 3):
        run = mark_done(run, "auth", stage)
    state = run.run_dir / "state.json"
    payload = json.loads(state.read_text(encoding="utf-8"))
    payload["features"][0]["stages"][1]["status"] = "pending"
    state.write_text(json.dumps(payload), encoding="utf-8")

    resumed = load_run(run.run_dir)
    unit = next_unit(resumed)
    assert (unit.feature_id, unit.stage) == ("auth", 2)
    counts = run_status(resumed)
    assert counts["done"] == 2  # stage 1 stays done — never repeated
    assert counts["pending"] == 1


@pytest.mark.unit
def test_load_run_refuses_corrupt_json(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    (run.run_dir / "state.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(FleetRunError, match="not valid JSON"):
        load_run(run.run_dir)


@pytest.mark.unit
def test_load_run_refuses_unknown_status(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    state = run.run_dir / "state.json"
    payload = json.loads(state.read_text(encoding="utf-8"))
    payload["features"][0]["stages"][0]["status"] = "halfway"
    state.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FleetRunError, match="unknown status"):
        load_run(run.run_dir)


@pytest.mark.unit
def test_find_newest_run_is_prefix_scoped_and_tolerant(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    assert find_newest_run(context_dir) is None

    other = context_dir / FLEET_DIR_REL / "run-20260101-000000"
    other.mkdir(parents=True)
    (other / "state.json").write_text("{}", encoding="utf-8")  # fleet-runner's
    mine = _make_run(tmp_path)
    assert find_newest_run(context_dir) == mine.run_dir

    corrupt = context_dir / FLEET_DIR_REL / f"{MAINTAIN_RUN_PREFIX}99999999-999999"
    corrupt.mkdir(parents=True)
    (corrupt / "state.json").write_text("broken", encoding="utf-8")
    # A half-created / corrupt run is skipped by discovery, not fatal.
    assert find_newest_run(context_dir) == mine.run_dir


@pytest.mark.unit
def test_resolve_run_dir_explicit_name_and_absolute(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    context_dir = tmp_path / ".context"
    assert resolve_run_dir(context_dir, run.run_dir.name) == run.run_dir
    assert resolve_run_dir(context_dir, str(run.run_dir)) == run.run_dir
    with pytest.raises(FleetRunError):
        resolve_run_dir(context_dir, "maintain-does-not-exist")


# ----- estimator -------------------------------------------------------------


@pytest.mark.unit
def test_estimate_run_composes_build_plan_and_active_stages(tmp_path: Path) -> None:
    from dummyindex.context.domains.enrich import build_plan

    context_dir = tmp_path / ".context"
    feature_dir = context_dir / "features" / "auth"
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature.json").write_text(
        json.dumps({"feature_id": "auth", "files": ["auth.py"]}), encoding="utf-8"
    )
    tree = {
        "root": {
            "node_id": "p",
            "kind": "project",
            "title": "t",
            "confidence": "EXTRACTED",
            "children": [
                {
                    "node_id": "f1",
                    "kind": "file",
                    "title": "auth.py",
                    "path": "auth.py",
                    "confidence": "EXTRACTED",
                    "children": [
                        {
                            "node_id": "s1",
                            "kind": "symbol",
                            "title": "login",
                            "path": "auth.py",
                            "confidence": "EXTRACTED",
                        }
                    ],
                },
                {
                    # owned by nobody — never attributed to auth
                    "node_id": "f2",
                    "kind": "file",
                    "title": "other.py",
                    "path": "other.py",
                    "confidence": "EXTRACTED",
                },
            ],
        }
    }
    (context_dir / "tree.json").write_text(json.dumps(tree), encoding="utf-8")

    estimates = estimate_run(context_dir, ("auth",), "standard")

    plan = build_plan(context_dir)
    assert estimates["stages"] == ((1, "specify"), (2, "plan"), (3, "critique"),
                                  (4, "flow"), (5, "tree-enrich"))
    assert len(plan.nodes) >= 3  # reuse, not duplication: same walk is readable
    item = estimates["features"][0]
    assert item["feature_id"] == "auth"
    assert item["estimate_nodes"] == 2  # file node + its symbol; not other.py
    assert item["estimate_stages"] == 5
    assert item["estimate_units"] == 5
    assert estimates["total_units"] == 5
    assert estimates["heuristic_seconds"] == 5 * 90


@pytest.mark.unit
def test_estimate_run_survives_missing_tree(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    feature_dir = context_dir / "features" / "auth"
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature.json").write_text(
        json.dumps({"feature_id": "auth", "files": ["auth.py"]}), encoding="utf-8"
    )
    estimates = estimate_run(context_dir, ("auth",), "light")
    assert estimates["features"][0]["estimate_nodes"] == 0
    assert estimates["total_units"] > 0
