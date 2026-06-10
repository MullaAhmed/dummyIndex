from dummyindex.context.domains.council_batch import (
    CouncilStage,
    CouncilMode,
    active_stages,
)


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


# --- Task 2: relocated domain helpers ---

import json
from dummyindex.context.domains.dev_pick import (
    harvest_dep_tokens,
    read_feature_files,
)


def _make_feature(features_dir, feature_id, files):
    fdir = features_dir / feature_id
    fdir.mkdir(parents=True)
    (fdir / "feature.json").write_text(
        json.dumps({"feature_id": feature_id, "files": list(files)}),
        encoding="utf-8",
    )
    return fdir


def test_read_feature_files_returns_tuple(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "auth", ["src/auth.py", "src/login.py"])
    assert read_feature_files(features_dir, "auth") == ("src/auth.py", "src/login.py")


def test_read_feature_files_missing_raises(tmp_path):
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    import pytest
    with pytest.raises(FileNotFoundError):
        read_feature_files(features_dir, "ghost")


def test_harvest_dep_tokens_reads_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["fastapi", "sqlalchemy"]\n', encoding="utf-8"
    )
    tokens = harvest_dep_tokens(tmp_path)
    assert "fastapi" in tokens
    assert "sqlalchemy" in tokens


# --- Task 3: earliest_incomplete_stage ---

from dummyindex.context.domains.council_batch import earliest_incomplete_stage
from dummyindex.context.domains.council import append_log


def _log(features_dir, feature_id, stage, agent, status):
    append_log(features_dir, feature_id=feature_id, stage=stage, agent=agent, status=status)


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
