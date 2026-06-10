# tests/context/domains/test_council_batch_cli.py
import json

from dummyindex.cli import dispatch
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


from dummyindex.cli.help import USAGE


def test_usage_documents_council_batch():
    assert "council-batch" in USAGE
