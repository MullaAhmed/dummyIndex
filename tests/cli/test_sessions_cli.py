"""`dummyindex sessions list --json` wiring: flags, exit codes, schema output.

Runs the CLI against a copy of dummyPlane's synthetic session store. The
active session's mtime is "now" and the rest are an hour old, because the CLI
reads the real clock.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

import pytest

from dummyindex.cli import sessions as sessions_cli
from tests.paths import FIXTURES_DIR

FIXTURE_PROJECTS = FIXTURES_DIR / "sessions" / "projects"
CONTRACT = FIXTURES_DIR / "contract"
ACTIVE_SID = "11111111-1111-4111-8111-111111111111"
FINISHED_SID = "22222222-2222-4222-8222-222222222222"
MALFORMED_SID = "44444444-4444-4444-8444-444444444444"


def _stage(tmp_path: Path) -> Path:
    projects = tmp_path / "store" / "projects"
    shutil.copytree(FIXTURE_PROJECTS, projects)
    now = time.time()
    for path in projects.rglob("*"):
        if path.is_file():
            os.utime(path, (now - 3600, now - 3600))
    active = projects / "C--Fixture-active-app" / f"{ACTIVE_SID}.jsonl"
    os.utime(active, (now, now))
    return projects


def _check_jsonschema(instance: dict, schema_name: str) -> None:
    """Full schema check when jsonschema is installed; the structural asserts
    above run either way, so a missing package never skips the whole test."""
    try:
        import jsonschema
    except ImportError:
        return
    schema = json.loads((CONTRACT / schema_name).read_text(encoding="utf-8"))
    jsonschema.validate(instance, schema, format_checker=jsonschema.FormatChecker())


_CODE = re.compile(r"^[a-z][a-z0-9_]*$")
_STATES = {"active", "finished", "unknown"}


def _validate_sessions(document: dict) -> None:
    """Contract rules from docs/schemas/sessions-list.json, enforced without
    jsonschema; then the full schema check when jsonschema is installed."""
    assert set(document) == {"sessions"}
    for item in document["sessions"]:
        assert set(item) >= {
            "session_id",
            "agent_id",
            "agent_type",
            "parent_session_id",
            "cwd",
            "state",
            "started_at",
            "last_event_at",
            "warnings",
        }
        assert isinstance(item["session_id"], str) and item["session_id"]
        for key in (
            "agent_id",
            "agent_type",
            "parent_session_id",
            "cwd",
            "started_at",
            "last_event_at",
        ):
            assert item[key] is None or isinstance(item[key], str), key
        assert item["state"] in _STATES
        assert isinstance(item["warnings"], list)
        for warning in item["warnings"]:
            assert _CODE.match(warning["code"]) and isinstance(warning["message"], str)
        if item["state"] == "unknown":
            assert item["warnings"], "unknown state must carry a warning"
    _check_jsonschema(document, "sessions-list.json")


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str]:
    code = sessions_cli.run(argv)
    return code, capsys.readouterr().out


@pytest.mark.unit
def test_list_json_is_pretty_schema_valid_and_states_are_right(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects = _stage(tmp_path)
    code, out = _run(capsys, ["list", "--json", "--projects-root", str(projects)])
    assert code == 0
    assert out.startswith('{\n  "sessions": [')  # indent 2, nothing else on stdout
    document = json.loads(out)
    _validate_sessions(document)
    states = {
        (i["session_id"], i["agent_id"]): i["state"] for i in document["sessions"]
    }
    assert states[(ACTIVE_SID, None)] == "active"
    assert states[(FINISHED_SID, None)] == "finished"
    assert states[(MALFORMED_SID, None)] == "unknown"


@pytest.mark.unit
def test_root_filter_keeps_only_cwd_under_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projects = _stage(tmp_path)
    # Record cwds are C:\Fixture\...; a root of tmp_path matches none of them.
    code, out = _run(
        capsys,
        ["list", "--json", "--projects-root", str(projects), "--root", str(tmp_path)],
    )
    assert code == 0
    assert json.loads(out) == {"sessions": []}


@pytest.mark.unit
def test_default_projects_root_follows_claude_config_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(tmp_path)  # store/projects
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "store"))
    code, out = _run(capsys, ["list", "--json"])
    assert code == 0
    assert any(i["session_id"] == FINISHED_SID for i in json.loads(out)["sessions"])


@pytest.mark.unit
def test_missing_store_is_an_empty_listing_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(
        capsys, ["list", "--json", "--projects-root", str(tmp_path / "absent")]
    )
    assert code == 0
    assert json.loads(out) == {"sessions": []}


@pytest.mark.unit
def test_missing_json_flag_is_a_usage_error_with_no_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _run(capsys, ["list", "--projects-root", str(tmp_path)])
    assert code == 2
    assert out == ""


@pytest.mark.unit
def test_unknown_argument_prints_envelope_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = _run(capsys, ["list", "--json", "--bogus"])
    assert code == 2
    envelope = json.loads(out)
    assert envelope["error"]["code"] == "unknown_argument"
    assert "--bogus" in envelope["error"]["message"]


@pytest.mark.unit
def test_no_subcommand_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _run(capsys, [])
    assert code == 2
    assert out == ""
