"""Transcript parsing: dedup, synthetic filtering, path attribution, locating."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest

from dummyindex.usage import (
    encode_project_slug,
    find_main_transcript,
    iter_all_turns,
    load_session,
)


@pytest.mark.unit
def test_load_session_dedups_and_skips_synthetic(usage_corpus: Path) -> None:
    main, sub, n_agents = load_session(usage_corpus / "proj-a" / "s1.jsonl")
    # t1, t2 (dup dropped), t3 — synthetic and the user line excluded.
    assert len(main) == 3
    assert [t.input_tokens for t in main] == [100, 2, 3]
    assert len(sub) == 1
    assert sub[0].is_subagent is True
    assert sub[0].input_tokens == 1
    assert n_agents == 1


@pytest.mark.unit
def test_load_session_attributes_session_and_project_from_path(
    usage_corpus: Path,
) -> None:
    main, sub, _ = load_session(usage_corpus / "proj-a" / "s1.jsonl")
    assert {t.session_id for t in main} == {"s1"}
    assert {t.project for t in main} == {"proj-a"}
    # Subagent turn is attributed to the PARENT session, not its own file.
    assert sub[0].session_id == "s1"
    assert sub[0].project == "proj-a"


@pytest.mark.unit
def test_timestamps_are_utc_aware(usage_corpus: Path) -> None:
    main, _, _ = load_session(usage_corpus / "proj-a" / "s1.jsonl")
    assert main[0].timestamp.tzinfo is not None
    assert main[0].timestamp.utcoffset() == timezone.utc.utcoffset(None)


@pytest.mark.unit
def test_load_session_no_subagents(usage_corpus: Path) -> None:
    main, sub, n_agents = load_session(usage_corpus / "proj-b" / "s2.jsonl")
    assert len(main) == 1
    assert sub == ()
    assert n_agents == 0


@pytest.mark.unit
def test_unreadable_transcript_is_skipped(usage_corpus: Path) -> None:
    # A directory where a .jsonl file is expected: open() raises OSError and the
    # session is skipped, not crashed. (Best-effort scan over a churning corpus.)
    ghost = usage_corpus / "proj-c"
    (ghost / "broken.jsonl").mkdir(parents=True)
    main, sub, n_agents = load_session(ghost / "broken.jsonl")
    assert main == () and sub == () and n_agents == 0


@pytest.mark.unit
def test_turn_with_unparseable_timestamp_is_skipped(tmp_path: Path) -> None:
    import json

    proj = tmp_path / "projects" / "p"
    proj.mkdir(parents=True)
    good = {
        "type": "assistant",
        "timestamp": "2026-06-01T10:00:00Z",
        "uuid": "u1",
        "requestId": "r1",
        "message": {
            "id": "m1",
            "model": "claude-opus-4-8",
            "usage": {"input_tokens": 5},
        },
    }
    bad = dict(good)
    bad["timestamp"] = "not-a-date"
    bad["uuid"] = "u2"
    bad["message"] = {
        "id": "m2",
        "model": "claude-opus-4-8",
        "usage": {"input_tokens": 9},
    }
    (proj / "s.jsonl").write_text(
        json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="utf-8"
    )
    main, _, _ = load_session(proj / "s.jsonl")
    assert [t.input_tokens for t in main] == [5]  # bad-timestamp turn dropped


@pytest.mark.unit
def test_iter_all_turns_spans_projects_and_subagents(usage_corpus: Path) -> None:
    turns = tuple(iter_all_turns(usage_corpus))
    # 3 main (s1) + 1 subagent (s1) + 1 main (s2) = 5 unique turns.
    assert len(turns) == 5
    assert {t.session_id for t in turns} == {"s1", "s2"}


@pytest.mark.unit
def test_iter_all_turns_can_exclude_subagents(usage_corpus: Path) -> None:
    turns = tuple(iter_all_turns(usage_corpus, include_subagents=False))
    assert len(turns) == 4
    assert all(not t.is_subagent for t in turns)


@pytest.mark.unit
def test_find_main_transcript_prefers_session_id(usage_corpus: Path) -> None:
    found = find_main_transcript(usage_corpus, session_id="s2", cwd=Path("/nope"))
    assert found == usage_corpus / "proj-b" / "s2.jsonl"


@pytest.mark.unit
def test_find_main_transcript_falls_back_to_cwd_slug(
    usage_corpus: Path, tmp_path: Path
) -> None:
    # Rename proj-a to the slug encoding of a real cwd so the fallback finds it.
    cwd = tmp_path / "work"
    cwd.mkdir()
    slug = encode_project_slug(cwd)
    (usage_corpus / "proj-a").rename(usage_corpus / slug)
    found = find_main_transcript(usage_corpus, session_id=None, cwd=cwd)
    assert found == usage_corpus / slug / "s1.jsonl"


@pytest.mark.unit
def test_find_main_transcript_returns_none_when_absent(usage_corpus: Path) -> None:
    assert (
        find_main_transcript(usage_corpus, session_id="ghost", cwd=Path("/nope"))
        is None
    )
