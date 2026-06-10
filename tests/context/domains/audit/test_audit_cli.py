"""CLI dispatch tests for `dummyindex context audit` + `audit-log`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch


def _start(tmp_path: Path, *extra: str) -> None:
    dispatch(["audit", "start", *extra, "--root", str(tmp_path)])


@pytest.mark.integration
def test_audit_start_creates_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(
        [
            "audit",
            "start",
            "--describe",
            "Audit error handling in the CLI dispatcher",
            "--scope",
            "dummyindex/cli",
            "--model",
            "opus-4.7",
            "--root",
            str(tmp_path),
            "--json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["model"] == "opus-4.7"
    assert data["scope"] == ["dummyindex/cli"]
    assert data["max_rounds"] == 3
    assert data["catalog"], "catalog should list shipped personas"
    slug = data["slug"]
    assert (tmp_path / ".context" / "audits" / slug / "audit.json").is_file()
    assert (tmp_path / ".context" / "audits" / slug / "catalog.json").is_file()
    assert (tmp_path / ".context" / "audits" / slug / "findings").is_dir()


@pytest.mark.integration
def test_audit_start_requires_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(["audit", "start", "--describe", "x", "--root", str(tmp_path)])
    assert rc == 2
    assert "model is required" in capsys.readouterr().err


@pytest.mark.unit
def test_audit_start_requires_describe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(
        ["audit", "start", "--model", "sonnet-4.6", "--root", str(tmp_path)]
    )
    assert rc == 2
    assert "--describe" in capsys.readouterr().err


@pytest.mark.integration
def test_audit_start_refuses_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start(tmp_path, "--describe", "dup", "--slug", "dup", "--model", "haiku-4.5")
    capsys.readouterr()
    rc = dispatch(
        ["audit", "start", "--describe", "dup", "--slug", "dup",
         "--model", "haiku-4.5", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


@pytest.mark.integration
def test_audit_show_reports_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start(tmp_path, "--describe", "cache layer", "--slug", "cache",
           "--model", "sonnet-4.6")
    capsys.readouterr()
    rc = dispatch(["audit", "show", "--slug", "cache", "--root", str(tmp_path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["slug"] == "cache"
    assert data["completed_rounds"] == []
    assert data["report"] is None


@pytest.mark.integration
def test_audit_show_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["audit", "show", "--slug", "ghost", "--root", str(tmp_path)])
    assert rc == 1


@pytest.mark.integration
def test_audit_log_append_reflected_in_show(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start(tmp_path, "--describe", "x", "--slug", "x", "--model", "haiku-4.5")
    capsys.readouterr()
    rc = dispatch(
        ["audit-log", "--slug", "x", "--round", "0", "--persona", "security",
         "--status", "complete", "--root", str(tmp_path)]
    )
    assert rc == 0
    assert "status=complete" in capsys.readouterr().out

    dispatch(["audit", "show", "--slug", "x", "--root", str(tmp_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["completed_rounds"] == [0]


@pytest.mark.unit
def test_audit_log_validates_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start(tmp_path, "--describe", "x", "--slug", "x", "--model", "haiku-4.5")
    capsys.readouterr()
    rc = dispatch(
        ["audit-log", "--slug", "x", "--round", "0", "--persona", "security",
         "--status", "bogus", "--root", str(tmp_path)]
    )
    assert rc == 2


@pytest.mark.unit
def test_audit_log_requires_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(["audit-log", "--slug", "x", "--root", str(tmp_path)])
    assert rc == 2
    assert "required" in capsys.readouterr().err


@pytest.mark.unit
def test_audit_unknown_verb(capsys: pytest.CaptureFixture[str]) -> None:
    rc = dispatch(["audit", "frobnicate"])
    assert rc == 2
    assert "unknown audit verb" in capsys.readouterr().err


@pytest.mark.integration
def test_audit_start_human_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(
        ["audit", "start", "--describe", "human readable",
         "--mode=deep", "--model=opus-4.7", "--root", str(tmp_path)]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "context audit:" in out
    assert "mode=deep model=opus-4.7 max_rounds=3" in out
    assert "catalog:" in out


@pytest.mark.integration
def test_audit_show_human_output_with_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start(tmp_path, "--describe", "r", "--slug", "r", "--model", "sonnet-4.6")
    capsys.readouterr()
    # simulate the skill having written the synthesis report
    (tmp_path / ".context" / "audits" / "r" / "report.md").write_text(
        "# report", encoding="utf-8"
    )
    rc = dispatch(["audit", "show", "--slug", "r", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "report: written" in out


@pytest.mark.unit
def test_audit_start_unknown_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(
        ["audit", "start", "--describe", "x", "--model", "haiku-4.5",
         "--bogus", "--root", str(tmp_path)]
    )
    assert rc == 2
    assert "unknown argument" in capsys.readouterr().err
