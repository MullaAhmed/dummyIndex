"""Integration tests for `dummyindex context memory`."""
from __future__ import annotations

import pytest

from dummyindex.cli import dispatch

pytestmark = pytest.mark.integration


def test_memory_init_creates_store(tmp_path, capsys):
    rc = dispatch(["memory", "init", "--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / ".context" / "session-memory" / "now.md").exists()
    assert "memory init" in capsys.readouterr().out


def test_memory_roll_without_store_is_noop(tmp_path, capsys):
    rc = dispatch(["memory", "roll", "--root", str(tmp_path)])
    assert rc == 0
    assert "nothing to do" in capsys.readouterr().out


def test_memory_roll_reports_moves(tmp_path, capsys):
    dispatch(["memory", "init", "--root", str(tmp_path)])
    now = tmp_path / ".context" / "session-memory" / "now.md"
    now.write_text("# Now\n\n## 2020-01-01 09:00 | main\nancient\n", encoding="utf-8")
    rc = dispatch(["memory", "roll", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "memory roll" in out


def test_memory_session_start_silent_without_store(tmp_path, capsys):
    rc = dispatch(["memory", "session-start", "--root", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_memory_session_start_prints_block(tmp_path, capsys):
    dispatch(["memory", "init", "--root", str(tmp_path)])
    now = tmp_path / ".context" / "session-memory" / "now.md"
    now.write_text("# Now\n\n## 2026-06-05 10:00 | main\nhello\n", encoding="utf-8")
    rc = dispatch(["memory", "session-start", "--root", str(tmp_path)])
    assert rc == 0
    assert "=== HANDOFF ===" in capsys.readouterr().out


def test_memory_no_verb_is_bad_args(capsys):
    assert dispatch(["memory"]) == 2


def test_memory_unknown_verb_is_bad_args(tmp_path):
    assert dispatch(["memory", "bogus", "--root", str(tmp_path)]) == 2
