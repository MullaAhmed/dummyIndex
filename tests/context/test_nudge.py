"""Tests for the Stop-hook handoff nudge (dummyindex context memory nudge)."""
from __future__ import annotations

from dummyindex.context.domains.memory.enums import AUTO_BREADCRUMB_TAG, MemoryVerb


def test_new_memory_verbs_exist():
    assert MemoryVerb("nudge") is MemoryVerb.NUDGE
    assert MemoryVerb("breadcrumb") is MemoryVerb.BREADCRUMB


def test_auto_breadcrumb_tag_constant():
    assert AUTO_BREADCRUMB_TAG == "(auto-breadcrumb)"


from datetime import datetime, timezone

from dummyindex.context.domains.memory import nudge as nudge_mod
from dummyindex.usage.models import TurnUsage


def _turn(output_tokens: int) -> TurnUsage:
    return TurnUsage(
        timestamp=datetime(2026, 6, 8, tzinfo=timezone.utc),
        session_id="s",
        project="p",
        model="claude-opus-4-8",
        input_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=output_tokens,
        is_subagent=False,
    )


def test_significant_when_subagents_used():
    assert nudge_mod.is_significant((_turn(10),), subagent_file_count=1) is True


def test_significant_when_output_tokens_over_threshold():
    big = (_turn(nudge_mod.LONG_OUTPUT_TOKENS),)
    assert nudge_mod.is_significant(big, subagent_file_count=0) is True


def test_not_significant_when_small_and_no_subagents():
    small = (_turn(100), _turn(200))
    assert nudge_mod.is_significant(small, subagent_file_count=0) is False


def test_total_main_output_tokens_sums():
    assert nudge_mod.total_main_output_tokens((_turn(100), _turn(250))) == 350


from pathlib import Path


def test_already_nudged_false_then_true(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    assert nudge_mod.already_nudged(ctx, "sess-1") is False
    nudge_mod.mark_nudged(ctx, "sess-1", now)
    assert nudge_mod.already_nudged(ctx, "sess-1") is True
    # State lives under the gitignored cache dir.
    assert (ctx / "cache" / "nudge-state.json").exists()


def test_mark_nudged_is_per_session(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    nudge_mod.mark_nudged(ctx, "sess-1", now)
    assert nudge_mod.already_nudged(ctx, "sess-2") is False


def test_empty_session_id_never_nudged(tmp_path: Path):
    ctx = tmp_path / ".context"
    assert nudge_mod.already_nudged(ctx, "") is False
    nudge_mod.mark_nudged(ctx, "", datetime(2026, 6, 8, tzinfo=timezone.utc))
    assert not (ctx / "cache" / "nudge-state.json").exists()


def _write_now(ctx: Path, body: str) -> None:
    mdir = ctx / "session-memory"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "now.md").write_text(body, encoding="utf-8")


def test_real_handoff_today_suppresses(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n\n## 2026-06-08 13:00 | main\nDid real work.\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is True


def test_auto_breadcrumb_today_does_not_suppress(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n\n## 2026-06-08 13:00 | main (auto-breadcrumb)\nx\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is False


def test_old_handoff_does_not_suppress(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n\n## 2026-06-01 09:00 | main\nold.\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is False


def test_empty_now_does_not_suppress(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is False


import json


def test_render_additional_context_shape():
    out = nudge_mod.render_additional_context(
        total_output_tokens=50000, subagent_file_count=3
    )
    obj = json.loads(out)
    assert obj["hookSpecificOutput"]["hookEventName"] == "Stop"
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "/dummyindex-remember" in ctx
    assert "Do NOT save automatically" in ctx


def test_decide_returns_none_when_remember_plugin_present(tmp_path: Path):
    (tmp_path / ".remember").mkdir()
    out = nudge_mod.decide_nudge(
        root=tmp_path,
        main_transcript=None,
        session_id="s",
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )
    assert out is None


def test_decide_returns_none_when_already_nudged(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, tzinfo=timezone.utc)
    nudge_mod.mark_nudged(ctx, "s", now)
    out = nudge_mod.decide_nudge(
        root=tmp_path, main_transcript=None, session_id="s", now=now
    )
    assert out is None


def test_decide_fires_and_marks_for_subagent_session(tmp_path: Path, monkeypatch):
    transcript = tmp_path / "main.jsonl"
    transcript.write_text("", encoding="utf-8")
    now = datetime(2026, 6, 8, tzinfo=timezone.utc)
    # Force load_session → one small main turn + 2 subagent files (significant).
    monkeypatch.setattr(
        nudge_mod, "load_session", lambda p: ((_turn(10),), (), 2)
    )
    out = nudge_mod.decide_nudge(
        root=tmp_path, main_transcript=transcript, session_id="s", now=now
    )
    assert out is not None
    assert "Stop" in out
    # Marker is now set → a second decide is suppressed.
    assert nudge_mod.already_nudged(tmp_path / ".context", "s") is True
    assert nudge_mod.decide_nudge(
        root=tmp_path, main_transcript=transcript, session_id="s", now=now
    ) is None


def test_decide_returns_none_when_not_significant(tmp_path: Path, monkeypatch):
    transcript = tmp_path / "main.jsonl"
    transcript.write_text("", encoding="utf-8")
    monkeypatch.setattr(nudge_mod, "load_session", lambda p: ((_turn(10),), (), 0))
    out = nudge_mod.decide_nudge(
        root=tmp_path,
        main_transcript=transcript,
        session_id="s",
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )
    assert out is None
