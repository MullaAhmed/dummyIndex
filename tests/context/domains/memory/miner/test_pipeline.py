"""End-to-end scan -> group -> write, including the determinism proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import (
    RecurringSkillCorrection,
    mine_and_feed,
    project_dir_name,
    refresh_skill_feedback,
    scan_skill_feedback,
    scan_transcript_store,
    skill_feedback_cache_path,
)
from dummyindex.context.domains.memory.miner.render import FAILURE_PATTERNS_FILENAME
from dummyindex.context.domains.memory.store import memory_dir

pytestmark = pytest.mark.unit


def _tool_use(call_id: str, name: str, tool_input: dict) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": name,
                        "input": tool_input,
                    }
                ]
            },
        }
    )


def _tool_result(call_id: str, content: str, *, is_error: bool = False) -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": content,
                        "is_error": is_error,
                    }
                ]
            },
        }
    )


def _seed_store(store: Path, *, project_dir_name_: str = "-repo-a") -> None:
    lines = []
    for i in range(4):
        lines.append(
            _tool_use(
                f"c{i}", "Bash", {"command": f"grep TODO app.py | head -{50 + i}"}
            )
        )
        lines.append(
            _tool_result(f"c{i}", "Error: No such file or directory", is_error=True)
        )
    (store / project_dir_name_).mkdir(parents=True)
    (store / project_dir_name_ / "session1.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _human_line(
    repo: Path,
    text: str,
    *,
    uuid: str,
    timestamp: str,
    session: str,
) -> str:
    return json.dumps(
        {
            "type": "user",
            "userType": "external",
            "origin": {"kind": "human"},
            "cwd": str(repo),
            "sessionId": session,
            "uuid": uuid,
            "timestamp": timestamp,
            "message": {"role": "user", "content": text},
        }
    )


def test_scan_transcript_store_finds_qualifying_loop(tmp_path: Path) -> None:
    store = tmp_path / "projects"
    _seed_store(store)
    report = scan_transcript_store(store)
    assert report.scanned_sessions == 1
    assert len(report.signatures) == 1
    assert report.signatures[0].occurrences == 4


def test_scan_transcript_store_empty_when_store_absent(tmp_path: Path) -> None:
    report = scan_transcript_store(tmp_path / "no-such-store")
    assert report.signatures == ()
    assert report.scanned_sessions == 0


def test_scan_is_deterministic_across_runs(tmp_path: Path) -> None:
    store = tmp_path / "projects"
    _seed_store(store)
    first = scan_transcript_store(store)
    second = scan_transcript_store(store)
    assert first == second


def test_mine_and_feed_writes_atomically_via_write_text_atomic(tmp_path: Path) -> None:
    store = tmp_path / "claude-store"
    context_dir = tmp_path / "repo" / ".context"
    # mine_and_feed scopes to the repo owning `context_dir`, so the seeded
    # project dir has to be the one Claude Code would name for that repo.
    _seed_store(
        store / "projects",
        project_dir_name_=project_dir_name(context_dir.resolve().parent),
    )

    mine_and_feed(context_dir, store_override=store)

    out = memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME
    assert out.exists()
    # write_text_atomic never leaves its .tmp sibling behind.
    assert not (out.parent / (out.name + ".tmp")).exists()
    text = out.read_text(encoding="utf-8")
    assert "Bash" in text
    assert "4x" in text


def test_mine_and_feed_is_byte_identical_across_two_runs(tmp_path: Path) -> None:
    """The determinism proof: same transcripts in -> byte-identical file out,
    twice in a row."""
    store = tmp_path / "claude-store"
    _seed_store(store / "projects")
    context_dir = tmp_path / "repo" / ".context"
    out = memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME

    mine_and_feed(context_dir, store_override=store)
    first_bytes = out.read_bytes()

    mine_and_feed(context_dir, store_override=store)
    second_bytes = out.read_bytes()

    assert first_bytes == second_bytes


def test_mine_and_feed_reports_no_patterns_on_empty_store(tmp_path: Path) -> None:
    context_dir = tmp_path / "repo" / ".context"
    report = mine_and_feed(context_dir, store_override=tmp_path / "empty-store")
    assert report.signatures == ()
    out = memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME
    assert "No repeated failure/loop signatures found" in out.read_text(
        encoding="utf-8"
    )


def test_skill_feedback_unions_profiles_and_ignores_nested_subagents(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    profile_a = tmp_path / "profile-a"
    profile_b = tmp_path / "profile-b"
    project_name = project_dir_name(repo)
    main_a = profile_a / "projects" / project_name / "a.jsonl"
    main_b = profile_b / "projects" / project_name / "b.jsonl"
    nested = profile_a / "projects" / project_name / "a" / "subagents" / "agent.jsonl"
    for path, line in (
        (
            main_a,
            _human_line(
                repo,
                "Use ADHD skill.",
                uuid="a1",
                timestamp="2026-08-01T00:00:00Z",
                session="a",
            ),
        ),
        (
            main_b,
            _human_line(
                repo,
                "Why are you not using the ADHD skill?",
                uuid="b1",
                timestamp="2026-08-02T00:00:00Z",
                session="b",
            ),
        ),
        (
            nested,
            _human_line(
                repo,
                "Use nested-only skill.",
                uuid="nested-1",
                timestamp="2026-08-03T00:00:00Z",
                session="nested",
            ),
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(line + "\n", encoding="utf-8")

    assert scan_skill_feedback(
        repo,
        config_dirs=(profile_b, profile_a, profile_a),
    ) == (
        RecurringSkillCorrection(
            skill="i-have-adhd",
            corrections=2,
            sessions=2,
        ),
    )


def test_refresh_skill_feedback_honors_exclusive_override_and_writes_cache(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    context_dir = repo / ".context"
    profile = tmp_path / "fixture-profile"
    transcript = profile / "projects" / project_dir_name(repo) / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "\n".join(
            [
                _human_line(
                    repo,
                    "Use release-check skill.",
                    uuid=f"u-{index}",
                    timestamp=f"2026-08-0{index}T00:00:00Z",
                    session=f"s-{index}",
                )
                for index in (1, 2)
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert refresh_skill_feedback(
        context_dir,
        config_override=profile,
    ) == (
        RecurringSkillCorrection(
            skill="release-check",
            corrections=2,
            sessions=2,
        ),
    )
    assert skill_feedback_cache_path(context_dir).is_file()
