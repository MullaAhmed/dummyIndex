"""Transcript discovery and JSONL parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import discover_project_dirs
from dummyindex.context.domains.memory.miner.scan import (
    iter_transcript_files,
    parse_transcript,
)

pytestmark = pytest.mark.unit


def _tool_use_line(call_id: str, name: str, tool_input: dict) -> str:
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


def _tool_result_line(call_id: str, content: str, *, is_error: bool = False) -> str:
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


def _write(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- discover_project_dirs -------------------------------------------------


def test_discover_returns_empty_tuple_when_store_missing(tmp_path: Path) -> None:
    assert discover_project_dirs(tmp_path / "does-not-exist") == ()


def test_discover_skips_dotdirs_and_empty_dirs(tmp_path: Path) -> None:
    store = tmp_path / "projects"
    _write(
        store / "-repo-a" / "s1.jsonl",
        [_tool_use_line("1", "Read", {"file_path": "a"})],
    )
    (store / ".hidden").mkdir(parents=True)
    (store / "-repo-empty").mkdir(parents=True)
    dirs = discover_project_dirs(store)
    assert dirs == (store / "-repo-a",)


def test_discover_is_sorted(tmp_path: Path) -> None:
    store = tmp_path / "projects"
    for name in ("-repo-z", "-repo-a", "-repo-m"):
        _write(
            store / name / "s.jsonl", [_tool_use_line("1", "Read", {"file_path": "x"})]
        )
    dirs = discover_project_dirs(store)
    assert [d.name for d in dirs] == ["-repo-a", "-repo-m", "-repo-z"]


def test_iter_transcript_files_includes_nested_subagent_files(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "-repo-a"
    _write(project / "main.jsonl", ["{}"])
    _write(project / "main" / "subagents" / "agent-1.jsonl", ["{}"])
    files = iter_transcript_files(project)
    assert project / "main.jsonl" in files
    assert project / "main" / "subagents" / "agent-1.jsonl" in files


# --- parse_transcript -------------------------------------------------


def test_parse_pairs_tool_use_with_tool_result(tmp_path: Path) -> None:
    t = _write(
        tmp_path / "t.jsonl",
        [
            _tool_use_line("call-1", "Read", {"file_path": "/repo/a.py"}),
            _tool_result_line("call-1", "print('hi')\n"),
        ],
    )
    records = parse_transcript(t)
    assert len(records) == 1
    assert records[0].tool_name == "Read"
    assert records[0].is_error is False


def test_parse_honors_explicit_is_error_flag(tmp_path: Path) -> None:
    t = _write(
        tmp_path / "t.jsonl",
        [
            _tool_use_line("call-1", "Bash", {"command": "git status"}),
            _tool_result_line("call-1", "totally benign text", is_error=True),
        ],
    )
    records = parse_transcript(t)
    assert records[0].is_error is True


def test_parse_detects_error_from_content_heuristic(tmp_path: Path) -> None:
    t = _write(
        tmp_path / "t.jsonl",
        [
            _tool_use_line("call-1", "Read", {"file_path": "/missing.py"}),
            _tool_result_line(
                "call-1", "Error: No such file or directory: /missing.py"
            ),
        ],
    )
    records = parse_transcript(t)
    assert records[0].is_error is True


def test_parse_ignores_unmatched_tool_result(tmp_path: Path) -> None:
    t = _write(tmp_path / "t.jsonl", [_tool_result_line("orphan", "some output")])
    assert parse_transcript(t) == ()


def test_parse_tolerates_malformed_lines(tmp_path: Path) -> None:
    t = _write(
        tmp_path / "t.jsonl",
        [
            "not json at all {{{",
            _tool_use_line("call-1", "Read", {"file_path": "/a.py"}),
            _tool_result_line("call-1", "ok"),
        ],
    )
    records = parse_transcript(t)
    assert len(records) == 1


def test_parse_missing_file_returns_empty(tmp_path: Path) -> None:
    assert parse_transcript(tmp_path / "nope.jsonl") == ()
