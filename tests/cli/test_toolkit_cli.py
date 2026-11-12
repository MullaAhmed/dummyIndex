"""`dummyindex toolkit` CLI: envelope shape, exit codes, indent-2 JSON on stdout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.toolkit import run

pytestmark = pytest.mark.unit


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".context").mkdir(parents=True)
    return project


def _cfg(tmp_path: Path) -> Path:
    cfg = tmp_path / "srv.json"
    cfg.write_text('{"command": "node"}', encoding="utf-8")
    return cfg


def _stdout(capsys) -> str:
    return capsys.readouterr().out


def test_list_prints_indent_two_json_and_exits_zero(root: Path, capsys) -> None:
    assert run(["list", "--root", str(root)]) == 0
    out = _stdout(capsys)
    assert out.startswith('{\n  "items": []')
    assert json.loads(out) == {"items": []}


def test_add_then_show_round_trip(root: Path, tmp_path: Path, capsys) -> None:
    assert (
        run(
            [
                "add",
                "srv",
                "--kind",
                "mcp",
                "--root",
                str(root),
                "--config",
                str(_cfg(tmp_path)),
            ]
        )
        == 0
    )
    add = json.loads(_stdout(capsys))
    assert add["changed"] is True
    assert add["item"]["scope"] == "project"
    assert add["item"]["scope_warning"] is True

    assert run(["show", "srv", "--root", str(root)]) == 0
    shown = json.loads(_stdout(capsys))
    assert shown["launch_args"] == []
    assert shown["bundle_dir"] is None


def test_terminal_launch_args_are_printed_as_an_array(
    root: Path, tmp_path: Path, capsys
) -> None:
    out_dir = tmp_path / "a b" / "x&'y"
    out_dir.mkdir(parents=True)
    rc = run(
        [
            "add",
            "srv",
            "--kind",
            "mcp",
            "--scope",
            "terminal",
            "--terminal",
            "t-1",
            "--out-dir",
            str(out_dir),
            "--config",
            str(_cfg(tmp_path)),
            "--root",
            str(root),
            "--mechanism",
            "mcp_exclusive",
        ]
    )
    assert rc == 0
    doc = json.loads(_stdout(capsys))
    assert doc["launch_args"][0] == "--strict-mcp-config"
    assert doc["launch_args"][1] == "--mcp-config"
    assert doc["launch_args"][2] == str(out_dir / "t-1" / "mcp.json")


def test_unknown_flag_value_is_a_usage_envelope_with_exit_two(
    root: Path, capsys
) -> None:
    assert run(["list", "--scope", "bogus", "--root", str(root)]) == 2
    doc = json.loads(_stdout(capsys))
    assert doc["error"]["code"] == "usage"
    assert doc["error"]["message"]


def test_missing_verb_is_a_usage_envelope(capsys) -> None:
    assert run([]) == 2
    assert json.loads(_stdout(capsys))["error"]["code"] == "usage"


def test_operational_failure_is_exit_one_with_code(root: Path, capsys) -> None:
    assert run(["remove", "ghost", "--root", str(root)]) == 1
    doc = json.loads(_stdout(capsys))
    assert doc["error"]["code"] == "not_found"


def test_terminal_scope_without_terminal_is_usage_exit_two(root: Path, capsys) -> None:
    assert run(["list", "--scope", "terminal", "--root", str(root)]) == 2
    assert json.loads(_stdout(capsys))["error"]["code"] == "terminal_required"


def test_out_dir_inside_context_is_refused(root: Path, tmp_path: Path, capsys) -> None:
    rc = run(
        [
            "add",
            "srv",
            "--kind",
            "mcp",
            "--scope",
            "terminal",
            "--terminal",
            "t-1",
            "--out-dir",
            str(root / ".context" / "bundles"),
            "--config",
            str(_cfg(tmp_path)),
            "--root",
            str(root),
        ]
    )
    assert rc == 2
    assert json.loads(_stdout(capsys))["error"]["code"] == "invalid_argument"


def test_install_without_preview_or_yes_is_refused_before_any_network(
    root: Path, capsys
) -> None:
    rc = run(
        [
            "install",
            "--kind",
            "skill",
            "--source",
            "github:o/r/demo",
            "--root",
            str(root),
        ]
    )
    assert rc == 1
    assert json.loads(_stdout(capsys))["error"]["code"] == "confirmation_required"


def test_install_disallowed_scheme_is_refused_before_any_network(
    root: Path, capsys
) -> None:
    rc = run(
        [
            "install",
            "--kind",
            "skill",
            "--source",
            "https://example.test/x",
            "--preview",
            "--root",
            str(root),
        ]
    )
    assert rc == 2
    assert json.loads(_stdout(capsys))["error"]["code"] == "unsupported_source"


def test_install_yes_with_plan_hash_is_refused_when_not_matching(
    root: Path, capsys, monkeypatch
) -> None:
    from tests.context.domains.toolkit import helpers

    fake = helpers.FakeGh(
        contents={"o/r": {"demo/SKILL.md": helpers.SKILL_TEXT}},
        commit_sha=helpers.SHA_A,
    )
    import dummyindex.context.domains.toolkit.facade as facade

    monkeypatch.setattr(facade, "default_runner", fake)
    rc = run(
        [
            "install",
            "--kind",
            "skill",
            "--source",
            "github:o/r/demo",
            "--yes",
            "--plan-hash",
            "0" * 64,
            "--root",
            str(root),
        ]
    )
    assert rc == 1
    assert json.loads(_stdout(capsys))["error"]["code"] == "stale_plan_hash"


def test_utf16_mcp_json_is_malformed_config_envelope_not_traceback(
    root: Path, capsys
) -> None:
    (root / ".mcp.json").write_bytes('{"mcpServers": {}}'.encode("utf-16"))
    assert run(["list", "--scope", "project", "--root", str(root)]) == 1
    doc = json.loads(_stdout(capsys))
    assert doc["error"]["code"] == "malformed_config"
