"""`dummyindex context upgrade [--if-stale] [--root DIR]`: the SessionStart upgrade CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dummyindex.cli import upgrade
from dummyindex.context.build.context_upgrade import UpgradeReport
from dummyindex.context.build.meta import SCHEMA_VERSION
from dummyindex.context.domains.config import current_dummyindex_version

pytestmark = pytest.mark.unit

_NEW = "9.9.9"
_OLD = "0.0.1"


def _write_meta(root: Path, version: str) -> None:
    context = root / ".context"
    context.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "dummyindex_version": version,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "root": str(root),
    }
    (context / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def pinned_version(monkeypatch: pytest.MonkeyPatch) -> str:
    from dummyindex.context.domains import config

    monkeypatch.setattr(config, "current_dummyindex_version", lambda: _NEW)
    return _NEW


def _stub_upgrade(monkeypatch: pytest.MonkeyPatch, report: UpgradeReport) -> list:
    from dummyindex.context.build import context_upgrade

    calls: list = []

    def fake(root, *, package_version, runner):
        calls.append((Path(root), package_version, runner))
        return report

    monkeypatch.setattr(context_upgrade, "upgrade_project", fake)
    return calls


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--if-stale", "--root", "R"], id="if-stale-root"),
        pytest.param(["--root", "R"], id="root-only"),
    ],
)
def test_upgrade_accepts_root_and_if_stale(argv: list[str], tmp_path: Path) -> None:
    """The hook's argv shape and the bare `--root` form both parse."""
    argv = [str(tmp_path) if a == "R" else a for a in argv]
    assert upgrade.run(argv) == 0


def test_root_flag_selects_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_version: str
) -> None:
    project = tmp_path / "proj"
    _write_meta(project, _OLD)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "elsewhere"))
    calls = _stub_upgrade(monkeypatch, UpgradeReport())

    assert upgrade.run(["--root", str(project)]) == 0

    assert calls and calls[0][0] == project.resolve()


def test_root_falls_back_to_claude_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_version: str
) -> None:
    _write_meta(tmp_path, _OLD)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    calls = _stub_upgrade(monkeypatch, UpgradeReport())

    assert upgrade.run([]) == 0

    assert calls[0][0] == tmp_path.resolve()


def test_if_stale_on_current_stamp_writes_nothing(tmp_path: Path) -> None:
    """A current stamp: no output, no file change, and no tree_sitter import."""
    _write_meta(tmp_path, current_dummyindex_version())
    before = _tree(tmp_path)
    probe = (
        "import sys\n"
        "from dummyindex.cli import dispatch\n"
        "rc = dispatch(['upgrade', '--if-stale', '--root', sys.argv[1]])\n"
        "print(rc)\n"
        "print('tree_sitter' in sys.modules)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=120,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["0", "False"]
    assert proc.stderr == ""
    assert _tree(tmp_path) == before


def test_if_stale_on_current_stamp_is_silent_in_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_meta(tmp_path, current_dummyindex_version())
    calls = _stub_upgrade(monkeypatch, UpgradeReport(changed=True))

    assert upgrade.run(["--if-stale", "--root", str(tmp_path)]) == 0

    assert calls == []
    assert capsys.readouterr() == ("", "")


def test_stale_stamp_calls_upgrade_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pinned_version: str
) -> None:
    _write_meta(tmp_path, _OLD)
    calls = _stub_upgrade(monkeypatch, UpgradeReport())

    assert upgrade.run(["--if-stale", "--root", str(tmp_path)]) == 0

    assert len(calls) == 1
    root, version, runner = calls[0]
    assert root == tmp_path.resolve()
    assert version == pinned_version
    assert callable(runner)


def test_lock_held_prints_in_progress_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pinned_version: str
) -> None:
    _write_meta(tmp_path, _OLD)
    lock = tmp_path / ".context" / "cache" / "upgrade.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held", encoding="utf-8")

    assert upgrade.run(["--if-stale", "--root", str(tmp_path)]) == 0

    assert capsys.readouterr().out == "upgrade in progress\n"
    assert lock.is_file()


def test_first_line_names_the_upgraded_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pinned_version: str,
) -> None:
    _stub_upgrade(monkeypatch, UpgradeReport(changed=True, stamp_advanced=True))

    assert upgrade.run(["--root", str(tmp_path)]) == 0

    first = capsys.readouterr().out.splitlines()[0]
    assert first == f"dummyindex: upgraded .context/ to {pinned_version}"


def test_no_output_when_nothing_changed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pinned_version: str,
) -> None:
    _stub_upgrade(monkeypatch, UpgradeReport())

    assert upgrade.run(["--root", str(tmp_path)]) == 0

    assert capsys.readouterr() == ("", "")


def test_restart_hint_only_when_an_adapter_is_written(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pinned_version: str,
) -> None:
    _stub_upgrade(monkeypatch, UpgradeReport(changed=True))
    assert upgrade.run(["--root", str(tmp_path)]) == 0
    assert "restart Claude Code" not in capsys.readouterr().out

    _stub_upgrade(
        monkeypatch,
        UpgradeReport(changed=True, adapters_written=(".claude/agents/x.md",)),
    )
    assert upgrade.run(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "restart Claude Code to load new agents" in out.splitlines()


def test_errors_exit_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    pinned_version: str,
) -> None:
    _stub_upgrade(monkeypatch, UpgradeReport(errors=("refresh maps: boom",)))

    assert upgrade.run(["--root", str(tmp_path)]) == 1

    assert "error: refresh maps: boom" in capsys.readouterr().err


def test_missing_context_is_a_note_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pinned_version: str
) -> None:
    assert upgrade.run(["--root", str(tmp_path)]) == 0

    assert "nothing to upgrade" in capsys.readouterr().err


def test_unknown_argument_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert upgrade.run(["--bogus"]) == 2
    assert "unknown argument" in capsys.readouterr().err
