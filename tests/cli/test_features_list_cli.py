"""`dummyindex context features-list --json` wiring: flags, exit codes, schema."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import features
from tests.paths import FIXTURES_DIR

CONTRACT = FIXTURES_DIR / "contract"
FIXTURE_ROOT = FIXTURES_DIR / "features-list"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURE_ROOT, root)
    return root


def _check_jsonschema(instance: dict, schema_name: str) -> None:
    """Full schema check when jsonschema is installed; the structural asserts
    above run either way, so a missing package never skips the whole test."""
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads((CONTRACT / schema_name).read_text(encoding="utf-8"))
    jsonschema.validate(instance, schema, format_checker=jsonschema.FormatChecker())


_FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _validate_features(document: dict) -> None:
    """Contract rules from docs/schemas/features-list.json, enforced without
    jsonschema; then the full schema check when jsonschema is installed."""
    assert document["schema_version"] == 1 and type(document["schema_version"]) is int
    assert isinstance(document["features"], list)
    for feature in document["features"]:
        assert _FEATURE_ID.match(feature["feature_id"])
        assert isinstance(feature["name"], str) and feature["name"]
        assert isinstance(feature["summary"], str)
        assert type(feature["member_count"]) is int and feature["member_count"] >= 0
        assert feature["confidence"] in {"EXTRACTED", "INFERRED"}
    _check_jsonschema(document, "features-list.json")


@pytest.mark.unit
def test_features_list_json_is_schema_valid_and_pretty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    code = features.run_features_list(["--root", str(root), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith('{\n  "schema_version": 1')
    document = json.loads(out)
    _validate_features(document)
    assert len(document["features"]) == 3


@pytest.mark.unit
def test_schema_version_mismatch_exits_1_with_envelope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    index = root / ".context" / "features" / "INDEX.json"
    payload = json.loads(index.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    index.write_text(json.dumps(payload), encoding="utf-8")

    code = features.run_features_list(["--root", str(root), "--json"])
    out = capsys.readouterr().out
    assert code == 1
    envelope = json.loads(out)
    assert envelope["error"]["code"] == "unsupported_schema_version"
    _validate_error(envelope)


@pytest.mark.unit
def test_missing_context_exits_1_not_indexed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = features.run_features_list(["--root", str(tmp_path), "--json"])
    envelope = json.loads(capsys.readouterr().out)
    assert code == 1
    assert envelope["error"]["code"] == "not_indexed"
    _validate_error(envelope)


@pytest.mark.unit
def test_missing_json_flag_is_a_usage_error_with_no_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = features.run_features_list(["--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "--json is required" in captured.err


@pytest.mark.unit
def test_unknown_argument_prints_envelope_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = features.run_features_list(["--root", str(tmp_path), "--json", "--bogus"])
    envelope = json.loads(capsys.readouterr().out)
    assert code == 2
    assert envelope["error"]["code"] == "unknown_argument"


def _validate_error(envelope: dict) -> None:
    assert set(envelope) == {"error"}
    assert re.match(r"^[a-z][a-z0-9_]*$", envelope["error"]["code"])
    assert isinstance(envelope["error"]["message"], str)
    _check_jsonschema(envelope, "error-envelope.json")
