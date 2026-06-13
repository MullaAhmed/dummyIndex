# tests/context/domains/test_council_batch_cli.py
import json

from dummyindex.cli import dispatch
from dummyindex.cli.help import USAGE
from dummyindex.context.domains.council import append_log


def _make_feature(features_dir, feature_id, files):
    fdir = features_dir / feature_id
    fdir.mkdir(parents=True)
    (fdir / "feature.json").write_text(
        json.dumps({"feature_id": feature_id, "files": list(files)}),
        encoding="utf-8",
    )


def test_council_batch_next_json(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}, {"feature_id": "b"}]}),
        encoding="utf-8",
    )

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is False
    assert payload["stage"] == 1
    assert [u["feature_id"] for u in payload["units"]] == ["a", "b"]
    assert all(u["subagent_type"] for u in payload["units"])


def test_council_batch_complete_json(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    for stage, agent in ((1, "dev"), (4, "dev")):
        append_log(features_dir, feature_id="a", stage=stage, agent=agent, status="started")
        append_log(features_dir, feature_id="a", stage=stage, agent=agent, status="complete")

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--mode", "light", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is True
    assert payload["units"] == []


def test_council_batch_missing_features_dir_errors(tmp_path, capsys):
    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_council_batch_bad_cap_errors(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--cap", "0"])
    assert rc == 2
    assert "cap" in capsys.readouterr().err


def test_usage_documents_council_batch():
    assert "council-batch" in USAGE


def test_council_batch_malformed_index_json_errors(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text("{not json", encoding="utf-8")

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 2
    assert "error" in capsys.readouterr().err


def test_council_batch_complete_human_readable(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    for stage, agent in ((1, "dev"), (4, "dev")):
        append_log(features_dir, feature_id="a", stage=stage, agent=agent, status="started")
        append_log(features_dir, feature_id="a", stage=stage, agent=agent, status="complete")

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--mode", "light"])
    assert rc == 0
    assert "complete" in capsys.readouterr().out


def test_council_batch_non_integer_cap_errors(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--cap", "foo"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "integer" in err or "--cap" in err


def test_council_batch_non_complete_human_readable(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "auth", ["auth.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "auth"}]}),
        encoding="utf-8",
    )

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "stage 1" in out
    assert "auth" in out


def test_council_batch_missing_next_flag_errors(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "a"}]}), encoding="utf-8"
    )
    rc = dispatch(["council-batch", "--root", str(tmp_path), "--json"])
    assert rc == 2
    assert "--next" in capsys.readouterr().err


def _index(features_dir, *ids):
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": i} for i in ids]}),
        encoding="utf-8",
    )


def _complete_light_stages(features_dir, fid):
    from dummyindex.context.domains.council import append_log

    for stage in (1, 4):
        append_log(features_dir, feature_id=fid, stage=stage, agent="dev", status="started")
        append_log(features_dir, feature_id=fid, stage=stage, agent="dev", status="complete")


def test_council_batch_feature_flag_scopes_units(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _make_feature(features_dir, "b", ["b.py"])
    _index(features_dir, "a", "b")

    rc = dispatch([
        "council-batch", "--next", "--root", str(tmp_path),
        "--feature", "b", "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [u["feature_id"] for u in payload["units"]] == ["b"]


def test_council_batch_unknown_feature_errors(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _index(features_dir, "a")

    rc = dispatch([
        "council-batch", "--next", "--root", str(tmp_path),
        "--feature", "ghost", "--json",
    ])
    assert rc == 2
    assert "ghost" in capsys.readouterr().err


def test_council_batch_force_requires_feature(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _index(features_dir, "a")

    rc = dispatch([
        "council-batch", "--next", "--root", str(tmp_path), "--force", "--json",
    ])
    assert rc == 2
    assert "--feature" in capsys.readouterr().err


def test_council_batch_force_resurfaces_completed_feature(tmp_path, capsys):
    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _index(features_dir, "a")
    _complete_light_stages(features_dir, "a")

    rc = dispatch([
        "council-batch", "--next", "--root", str(tmp_path),
        "--mode", "light", "--feature", "a", "--force", "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is False
    assert payload["stage"] == 1
    assert payload["forced"] == ["a"]
    assert [u["feature_id"] for u in payload["units"]] == ["a"]


def test_council_batch_json_subagents_are_dispatchable_names(tmp_path, capsys):
    from dummyindex.context.domains.council_batch import CRITIC_ROSTER
    from dummyindex.context.domains.dev_pick import SubagentType

    features_dir = tmp_path / ".context" / "features"
    _make_feature(features_dir, "a", ["a.py"])
    _index(features_dir, "a")

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    allowed = {m.value for m in SubagentType} | {
        sub for roster in CRITIC_ROSTER.values() for _, sub in roster
    }
    for unit in payload["units"]:
        assert not unit["subagent_type"].startswith("SubagentType.")
        assert unit["subagent_type"] in allowed


def test_council_batch_warns_when_most_logs_need_backfill(tmp_path, capsys):
    """An index enriched before the council-batch convention (artifacts on
    disk, empty logs) gets a one-line stderr pointer at backfill."""
    features_dir = tmp_path / ".context" / "features"
    for fid in ("a", "b"):
        _make_feature(features_dir, fid, [f"{fid}.py"])
        (features_dir / fid / "spec.md").write_text(
            "# Real spec\n\nProse.\n", encoding="utf-8"
        )
        (features_dir / fid / "plan.md").write_text("# Plan\n", encoding="utf-8")
    _index(features_dir, "a", "b")

    rc = dispatch(["council-batch", "--next", "--root", str(tmp_path), "--json"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "backfill" in err
