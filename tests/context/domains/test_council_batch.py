import json

import pytest

from dummyindex.context.domains.council import (
    append_log,
    append_reset_marker,
    backfill_log_from_artifacts,
    is_stage_complete,
    read_log,
)
from dummyindex.context.domains.council_batch import (
    CRITIC_ROSTER,
    CouncilMode,
    CouncilStage,
    active_stages,
    earliest_incomplete_stage,
    force_recouncil,
    next_batch,
)
from dummyindex.context.domains.dev_pick import (
    SubagentType,
    harvest_dep_tokens,
    read_feature_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(features_dir, feature_id, files):
    fdir = features_dir / feature_id
    fdir.mkdir(parents=True)
    (fdir / "feature.json").write_text(
        json.dumps({"feature_id": feature_id, "files": list(files)}),
        encoding="utf-8",
    )
    return fdir


def _log(features_dir, feature_id, stage, agent, status):
    append_log(features_dir, feature_id=feature_id, stage=stage, agent=agent, status=status)


def _complete_through_plan(features_dir, fid):
    for stage, agent in ((1, "dev"), (2, "architect")):
        _log(features_dir, fid, stage, agent, "started")
        _log(features_dir, fid, stage, agent, "complete")


# ---------------------------------------------------------------------------
# Task 1: CouncilStage / CouncilMode basics
# ---------------------------------------------------------------------------


def test_council_stage_numbers_match_log_convention():
    assert CouncilStage.SPECIFY == 1
    assert CouncilStage.PLAN == 2
    assert CouncilStage.CRITIQUE == 3
    assert CouncilStage.FLOW == 4
    assert CouncilStage.TREE == 5


def test_active_stages_light_skips_plan_and_critique():
    assert active_stages(CouncilMode.LIGHT, tree_enrich=False) == (
        CouncilStage.SPECIFY,
        CouncilStage.FLOW,
    )


def test_active_stages_standard_is_full_minus_tree():
    assert active_stages(CouncilMode.STANDARD, tree_enrich=False) == (
        CouncilStage.SPECIFY,
        CouncilStage.PLAN,
        CouncilStage.CRITIQUE,
        CouncilStage.FLOW,
    )


def test_active_stages_deep_with_tree_includes_tree_last():
    assert active_stages(CouncilMode.DEEP, tree_enrich=True) == (
        CouncilStage.SPECIFY,
        CouncilStage.PLAN,
        CouncilStage.CRITIQUE,
        CouncilStage.FLOW,
        CouncilStage.TREE,
    )


def test_active_stages_deep_without_tree():
    assert active_stages(CouncilMode.DEEP, tree_enrich=False) == (
        CouncilStage.SPECIFY,
        CouncilStage.PLAN,
        CouncilStage.CRITIQUE,
        CouncilStage.FLOW,
    )


# ---------------------------------------------------------------------------
# Task 2: relocated domain helpers
# ---------------------------------------------------------------------------


def test_read_feature_files_returns_tuple(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "auth", ["src/auth.py", "src/login.py"])
    assert read_feature_files(features_dir, "auth") == ("src/auth.py", "src/login.py")


def test_read_feature_files_missing_raises(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        read_feature_files(features_dir, "ghost")


def test_harvest_dep_tokens_reads_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["fastapi", "sqlalchemy"]\n', encoding="utf-8"
    )
    tokens = harvest_dep_tokens(tmp_path)
    assert "fastapi" in tokens
    assert "sqlalchemy" in tokens


# ---------------------------------------------------------------------------
# Task 3: earliest_incomplete_stage
# ---------------------------------------------------------------------------


def test_earliest_stage_is_specify_when_nothing_logged(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    stage = earliest_incomplete_stage(
        features_dir, ("a", "b"), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage == CouncilStage.SPECIFY


def test_earliest_stage_advances_to_plan_once_all_specify_done(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    for fid in ("a", "b"):
        _log(features_dir, fid, 1, "dev", "started")
        _log(features_dir, fid, 1, "dev", "complete")
    stage = earliest_incomplete_stage(
        features_dir, ("a", "b"), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage == CouncilStage.PLAN


def test_earliest_stage_stays_at_specify_if_one_feature_incomplete(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    _log(features_dir, "a", 1, "dev", "started")
    _log(features_dir, "a", 1, "dev", "complete")
    # b never started specify
    stage = earliest_incomplete_stage(
        features_dir, ("a", "b"), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage == CouncilStage.SPECIFY


def test_earliest_stage_none_when_all_active_stages_done(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    for stage, agent in ((1, "dev"), (4, "dev")):  # light mode active stages
        _log(features_dir, "a", stage, agent, "started")
        _log(features_dir, "a", stage, agent, "complete")
    stage = earliest_incomplete_stage(
        features_dir, ("a",), mode=CouncilMode.LIGHT, tree_enrich=False
    )
    assert stage is None


# ---------------------------------------------------------------------------
# Task 4: next_batch for dev + architect stages
# ---------------------------------------------------------------------------


def test_next_batch_specify_emits_one_dev_unit_per_feature(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    batch = next_batch(
        features_dir, repo_root, ("a", "b"),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.complete is False
    assert batch.stage == CouncilStage.SPECIFY
    assert [u.feature_id for u in batch.units] == ["a", "b"]
    assert all(u.role == "dev" for u in batch.units)
    # dev subagent_type resolved via pick_dev (Senior Developer fallback here)
    assert all(u.subagent_type for u in batch.units)
    assert all(u.stage == 1 for u in batch.units)


def test_next_batch_plan_emits_architect_units(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _log(features_dir, "a", 1, "dev", "started")
    _log(features_dir, "a", 1, "dev", "complete")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.PLAN
    assert len(batch.units) == 1
    unit = batch.units[0]
    assert unit.role == "architect"
    assert unit.subagent_type == "Backend Architect"
    assert unit.framework is None


def test_next_batch_complete_when_all_done(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    for stage, agent in ((1, "dev"), (4, "dev")):
        _log(features_dir, "a", stage, agent, "started")
        _log(features_dir, "a", stage, agent, "complete")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.LIGHT, cap=8, tree_enrich=False,
    )
    assert batch.complete is True
    assert batch.stage is None
    assert batch.units == ()


# ---------------------------------------------------------------------------
# Task 5: CRITIC_ROSTER + critique-stage expansion
# ---------------------------------------------------------------------------


def test_critic_roster_sizes_per_mode():
    assert CRITIC_ROSTER[CouncilMode.LIGHT] == ()
    assert len(CRITIC_ROSTER[CouncilMode.STANDARD]) == 1
    assert len(CRITIC_ROSTER[CouncilMode.DEEP]) == 3


def test_critique_deep_emits_one_unit_per_feature_per_critic(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_through_plan(features_dir, "a")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.DEEP, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.CRITIQUE
    roles = sorted(u.role for u in batch.units)
    assert roles == ["critic-database", "critic-product", "critic-security"]
    subs = {u.role: u.subagent_type for u in batch.units}
    assert subs["critic-database"] == "Data Engineer"
    assert subs["critic-security"] == "Security Engineer"
    assert subs["critic-product"] == "general-purpose"


def test_cap_counts_agents_across_features(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    for fid in ("a", "b", "c"):
        _make_feature(features_dir, fid, [f"{fid}.py"])
        _complete_through_plan(features_dir, fid)
    # deep critique = 3 agents/feature; cap=4 => only the first feature fits
    batch = next_batch(
        features_dir, repo_root, ("a", "b", "c"),
        mode=CouncilMode.DEEP, cap=4, tree_enrich=False,
    )
    assert len({u.feature_id for u in batch.units}) == 1
    assert len(batch.units) == 3


def test_single_feature_critics_never_split_even_under_cap(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_through_plan(features_dir, "a")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.DEEP, cap=2, tree_enrich=False,  # cap < roster size
    )
    assert len(batch.units) == 3  # the one feature's full roster, never split


# ---------------------------------------------------------------------------
# New: _dev_unit missing-feature.json fallback
# ---------------------------------------------------------------------------


def test_dev_unit_fallback_when_no_feature_json(tmp_path):
    """next_batch emits a dev DispatchUnit even when feature.json is absent.

    The directory exists (so readiness passes), but there is no feature.json.
    _dev_unit catches FileNotFoundError and falls back to pick_dev with
    files=(), which resolves to the Senior Developer / generic persona.
    """
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    # Create the feature directory WITHOUT feature.json
    fdir = features_dir / "no-json"
    fdir.mkdir(parents=True)
    # SPECIFY is the first active stage; no prior stage required
    batch = next_batch(
        features_dir, repo_root, ("no-json",),
        mode=CouncilMode.LIGHT, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.SPECIFY
    assert len(batch.units) == 1
    unit = batch.units[0]
    assert unit.role == "dev"
    assert unit.subagent_type  # some non-empty subagent resolved


# ---------------------------------------------------------------------------
# New: FLOW stage via next_batch (STANDARD mode)
# ---------------------------------------------------------------------------


def _complete_standard_through_critique(features_dir, fid):
    """Complete specify → plan → critique (standard = one critic-security)."""
    _complete_through_plan(features_dir, fid)
    _log(features_dir, fid, 3, "critic-security", "started")
    _log(features_dir, fid, 3, "critic-security", "complete")


def test_next_batch_flow_stage_standard(tmp_path):
    """After specify+plan+critique complete, next_batch yields FLOW with role=dev."""
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_standard_through_critique(features_dir, "a")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.FLOW
    assert len(batch.units) == 1
    assert batch.units[0].role == "dev"
    assert batch.units[0].feature_id == "a"


# ---------------------------------------------------------------------------
# New: TREE stage via next_batch (DEEP mode with tree_enrich=True)
# ---------------------------------------------------------------------------


def _complete_deep_through_flow(features_dir, fid):
    """Complete stages 1–4 for deep mode (all three critics for stage 3)."""
    _complete_through_plan(features_dir, fid)
    for critic in ("critic-database", "critic-security", "critic-product"):
        _log(features_dir, fid, 3, critic, "started")
        _log(features_dir, fid, 3, critic, "complete")
    _log(features_dir, fid, 4, "dev", "started")
    _log(features_dir, fid, 4, "dev", "complete")


def test_next_batch_tree_stage_deep(tmp_path):
    """After stages 1–4 complete in DEEP mode, next_batch yields TREE with role=dev."""
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_deep_through_flow(features_dir, "a")
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.DEEP, cap=8, tree_enrich=True,
    )
    assert batch.stage == CouncilStage.TREE
    assert len(batch.units) == 1
    assert batch.units[0].role == "dev"
    assert batch.units[0].feature_id == "a"


# ---------------------------------------------------------------------------
# Task 8: Integration — drive to completion + resumption
# ---------------------------------------------------------------------------


def _complete_units(features_dir, batch):
    """Simulate every unit in a batch reaching `complete`."""
    for u in batch.units:
        _log(features_dir, u.feature_id, u.stage, u.role, "started")
        _log(features_dir, u.feature_id, u.stage, u.role, "complete")


def test_full_drive_standard_mode_reaches_complete(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    for fid in ("a", "b", "c"):
        _make_feature(features_dir, fid, [f"{fid}.py"])

    seen_stages = []
    for _ in range(50):  # generous guard against an infinite loop
        batch = next_batch(
            features_dir, repo_root, ("a", "b", "c"),
            mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
        )
        if batch.complete:
            break
        seen_stages.append(int(batch.stage))
        _complete_units(features_dir, batch)
    else:
        raise AssertionError("did not converge")

    assert batch.complete is True
    # standard active stages are 1,2,3,4 — each must have appeared
    assert set(seen_stages) == {1, 2, 3, 4}


def test_critique_partial_keeps_frontier_at_stage_3(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_through_plan(features_dir, "a")
    _log(features_dir, "a", 3, "critic-database", "started")
    _log(features_dir, "a", 3, "critic-database", "complete")
    _log(features_dir, "a", 3, "critic-security", "started")
    _log(features_dir, "a", 3, "critic-security", "complete")
    _log(features_dir, "a", 3, "critic-product", "started")  # never completed
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.DEEP, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.CRITIQUE
    assert len(batch.units) == 3


def test_resume_after_partial_specify(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    # only `a` finishes specify
    _log(features_dir, "a", 1, "dev", "started")
    _log(features_dir, "a", 1, "dev", "complete")

    batch = next_batch(
        features_dir, repo_root, ("a", "b"),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    # frontier is still SPECIFY, and only `b` is dispatched (a already done)
    assert batch.stage == CouncilStage.SPECIFY
    assert [u.feature_id for u in batch.units] == ["b"]


# ---------------------------------------------------------------------------
# Dev units carry the wire agent name, never the Python enum repr
# ---------------------------------------------------------------------------


def test_dev_unit_subagent_type_is_wire_value_not_enum_repr(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    unit = batch.units[0]
    assert unit.subagent_type == SubagentType.SENIOR.value  # "Senior Developer"
    assert not unit.subagent_type.startswith("SubagentType.")
    assert unit.subagent_type in {m.value for m in SubagentType}


def test_dev_unit_frontend_fixture_resolves_exact_agent_name(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "ui", ["src/App.tsx"])
    batch = next_batch(
        features_dir, repo_root, ("ui",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.units[0].subagent_type == "Frontend Developer"


# ---------------------------------------------------------------------------
# Outcome-C standalone features are done by design — never rescheduled
# ---------------------------------------------------------------------------


def _log_note(features_dir, feature_id, stage, agent, status, note):
    append_log(
        features_dir, feature_id=feature_id, stage=stage,
        agent=agent, status=status, note=note,
    )


def test_standalone_feature_excluded_from_frontier_and_batches(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "tiny-util", ["util.py"])
    _log_note(
        features_dir, "tiny-util", 0, "architect", "complete",
        "standalone; checked-parents=a; no dominant caller",
    )

    stage = earliest_incomplete_stage(
        features_dir, ("tiny-util",), mode=CouncilMode.STANDARD, tree_enrich=False
    )
    assert stage is None

    batch = next_batch(
        features_dir, repo_root, ("a", "tiny-util"),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert [u.feature_id for u in batch.units] == ["a"]

    only = next_batch(
        features_dir, repo_root, ("tiny-util",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert only.complete is True


def test_promoted_stage0_feature_still_runs_pipeline(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "promoted-one", ["p.py"])
    _log_note(
        features_dir, "promoted-one", 0, "architect", "complete",
        "promoted; rationale=real feature",
    )
    batch = next_batch(
        features_dir, repo_root, ("promoted-one",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.SPECIFY
    assert [u.feature_id for u in batch.units] == ["promoted-one"]


# ---------------------------------------------------------------------------
# Forced re-council: reset markers re-surface completed features
# ---------------------------------------------------------------------------


def _complete_light(features_dir, fid):
    for stage in (1, 4):
        _log(features_dir, fid, stage, "dev", "started")
        _log(features_dir, fid, stage, "dev", "complete")


def test_reset_marker_clears_completion(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_light(features_dir, "a")
    assert is_stage_complete(features_dir, "a", 1) is True
    append_reset_marker(features_dir, "a")
    assert is_stage_complete(features_dir, "a", 1) is False
    # New completions after the marker count again.
    _log(features_dir, "a", 1, "dev", "complete")
    assert is_stage_complete(features_dir, "a", 1) is True


def test_force_recouncil_resurfaces_complete_feature(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_light(features_dir, "a")

    reset = force_recouncil(
        features_dir, ("a",), mode=CouncilMode.LIGHT, tree_enrich=False
    )
    assert reset == ("a",)

    batch = next_batch(
        features_dir, repo_root, ("a",),
        mode=CouncilMode.LIGHT, cap=8, tree_enrich=False,
    )
    assert batch.complete is False
    assert batch.stage == CouncilStage.SPECIFY
    assert [u.feature_id for u in batch.units] == ["a"]


def test_force_recouncil_is_noop_mid_run(tmp_path):
    """Forcing a feature that is already incomplete appends nothing — the
    documented loop may keep passing --force without restarting forever."""
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _log(features_dir, "a", 1, "dev", "started")
    before = len(read_log(features_dir, "a"))

    reset = force_recouncil(
        features_dir, ("a",), mode=CouncilMode.LIGHT, tree_enrich=False
    )
    assert reset == ()
    assert len(read_log(features_dir, "a")) == before


def test_force_recouncil_then_recomplete_converges(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _complete_light(features_dir, "a")
    force_recouncil(features_dir, ("a",), mode=CouncilMode.LIGHT, tree_enrich=False)

    for _ in range(10):
        batch = next_batch(
            features_dir, repo_root, ("a",),
            mode=CouncilMode.LIGHT, cap=8, tree_enrich=False,
        )
        if batch.complete:
            break
        for u in batch.units:
            _log(features_dir, u.feature_id, u.stage, u.role, "started")
            _log(features_dir, u.feature_id, u.stage, u.role, "complete")
    assert batch.complete is True


# ---------------------------------------------------------------------------
# Backfill: synthetic complete entries from pre-existing enrichment artifacts
# ---------------------------------------------------------------------------


def _enrich_on_disk(features_dir, fid, *, spec=True, plan=True, concerns=True):
    fdir = features_dir / fid
    if spec:
        (fdir / "spec.md").write_text("# Real spec\n\nProse.\n", encoding="utf-8")
    if plan:
        (fdir / "plan.md").write_text("# Real plan\n", encoding="utf-8")
    if concerns:
        (fdir / "concerns.md").write_text("# Concerns\n", encoding="utf-8")


def test_backfill_from_artifacts_marks_enriched_stages(tmp_path):
    repo_root = tmp_path
    features_dir = repo_root / ".context" / "features"
    _make_feature(features_dir, "legacy", ["l.py"])
    _enrich_on_disk(features_dir, "legacy")

    stages = backfill_log_from_artifacts(features_dir, "legacy")
    assert stages == (1, 2, 3)

    batch = next_batch(
        features_dir, repo_root, ("legacy",),
        mode=CouncilMode.STANDARD, cap=8, tree_enrich=False,
    )
    assert batch.stage == CouncilStage.FLOW  # plan.md never re-clobbered


def test_backfill_skips_deterministic_stub_spec(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "fresh", ["f.py"])
    (features_dir / "fresh" / "spec.md").write_text(
        "# Feature: fresh\n\n_Deterministic stub (`confidence: EXTRACTED`). "
        "The `/dummyindex` skill will rewrite this `spec.md`._\n",
        encoding="utf-8",
    )
    assert backfill_log_from_artifacts(features_dir, "fresh") == ()


def test_backfill_never_touches_stage_with_existing_entries(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "partial", ["p.py"])
    _enrich_on_disk(features_dir, "partial")
    _log(features_dir, "partial", 2, "architect", "failed")

    stages = backfill_log_from_artifacts(features_dir, "partial")
    assert stages == (1, 3)
    statuses = [
        e.status for e in read_log(features_dir, "partial") if e.stage == 2
    ]
    assert statuses == ["failed"]


def test_backfill_is_idempotent(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "legacy", ["l.py"])
    _enrich_on_disk(features_dir, "legacy")
    assert backfill_log_from_artifacts(features_dir, "legacy") == (1, 2, 3)
    assert backfill_log_from_artifacts(features_dir, "legacy") == ()


def test_backfill_stage4_only_for_enriched_flows(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "flowy", ["f.py"])
    flows = features_dir / "flowy" / "flows"
    flows.mkdir()
    (flows / "f1.md").write_text(
        "# Flow: f1\n\n_Deterministic trace from a BFS over `calls` edges._\n",
        encoding="utf-8",
    )
    assert backfill_log_from_artifacts(features_dir, "flowy") == ()

    (flows / "f1.md").write_text(
        "# Flow: f1\n\nA real narrative of the request path.\n", encoding="utf-8"
    )
    assert backfill_log_from_artifacts(features_dir, "flowy") == (4,)
