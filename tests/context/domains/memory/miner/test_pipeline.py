"""End-to-end scan -> group -> write, including the determinism proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import (
    mine_and_feed,
    project_dir_name,
    scan_transcript_store,
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
