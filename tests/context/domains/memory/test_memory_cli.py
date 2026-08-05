"""Integration tests for `dummyindex context memory`."""

from __future__ import annotations

import io
import json

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.memory.miner import (
    RecurringSkillCorrection,
    skill_feedback_cache_path,
    write_skill_feedback,
)

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


def test_memory_mine_refreshes_cache_silently(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
):
    calls = []

    def fake_refresh(context_dir):
        calls.append(context_dir)
        return ()

    monkeypatch.setattr(
        "dummyindex.context.domains.memory.refresh_skill_feedback",
        fake_refresh,
    )
    assert dispatch(["memory", "mine", "--root", str(tmp_path)]) == 0
    assert calls == [tmp_path / ".context"]
    assert capsys.readouterr().out == ""


def test_memory_mine_is_fail_open_and_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
):
    def fail(_context_dir):
        raise OSError("unreadable profile")

    monkeypatch.setattr(
        "dummyindex.context.domains.memory.refresh_skill_feedback",
        fail,
    )
    assert dispatch(["memory", "mine", "--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_prompt_context_current_correction_applies_on_same_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
):
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "Use ADHD skill for output."})),
    )
    assert dispatch(["memory", "prompt-context", "--root", str(tmp_path)]) == 0
    raw = capsys.readouterr().out
    assert raw.count("\n") == 1
    payload = json.loads(raw)
    assert payload["suppressOutput"] is True
    specific = payload["hookSpecificOutput"]
    assert specific["hookEventName"] == "UserPromptSubmit"
    assert "i-have-adhd" in specific["additionalContext"]
    assert "directly" in specific["additionalContext"]


def test_prompt_context_uses_cache_and_current_revocation_suppresses_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
):
    context_dir = tmp_path / ".context"
    write_skill_feedback(
        context_dir,
        (
            RecurringSkillCorrection(
                skill="i-have-adhd",
                corrections=3,
                sessions=2,
            ),
            RecurringSkillCorrection(
                skill="review",
                corrections=2,
                sessions=2,
            ),
        ),
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "Stop using the ADHD skill."})),
    )
    assert dispatch(["memory", "prompt-context", "--root", str(tmp_path)]) == 0
    context = json.loads(capsys.readouterr().out)["hookSpecificOutput"][
        "additionalContext"
    ]
    assert "i-have-adhd" not in context
    assert "review" in context


@pytest.mark.parametrize("stdin_text", ["", "{", "[]", '{"prompt": 4}'])
def test_prompt_context_is_silent_for_absent_or_malformed_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
    stdin_text: str,
):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    assert dispatch(["memory", "prompt-context", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""
    assert not skill_feedback_cache_path(tmp_path / ".context").exists()


def test_prompt_context_is_fail_open_with_no_partial_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
):
    def fail(_context_dir):
        raise RuntimeError("cache raced")

    monkeypatch.setattr(
        "dummyindex.context.domains.memory.read_skill_feedback",
        fail,
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"prompt": "Use ADHD skill."})),
    )
    assert dispatch(["memory", "prompt-context", "--root", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
