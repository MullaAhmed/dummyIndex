"""Tests for the session-transcript reader's edited-source signal.

The reconcile gate needs to know whether THIS session plausibly caused source
drift — i.e. it edited a file outside ``.context/`` / ``.claude/``. The
transcript reader collects the ``file_path`` of every Write/Edit/NotebookEdit
tool_use so the gate can attribute drift to the session rather than trapping a
planning-only / git-only / tool-update session.
"""

from __future__ import annotations

import json
from pathlib import Path

from dummyindex.context.domains.memory.transcript import read_session_signal


def _assistant_tool_use(name: str, file_path: str) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "usage": {"output_tokens": 10},
                "content": [
                    {
                        "type": "tool_use",
                        "name": name,
                        "input": {"file_path": file_path},
                    }
                ],
            },
        }
    )


def _write_transcript(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_collects_edited_paths_from_edit_and_write(tmp_path: Path) -> None:
    t = _write_transcript(
        tmp_path / "t.jsonl",
        [
            _assistant_tool_use("Edit", "/repo/app/main.py"),
            _assistant_tool_use("Write", "/repo/app/util.py"),
        ],
    )
    sig = read_session_signal(t)
    assert "/repo/app/main.py" in sig.edited_paths
    assert "/repo/app/util.py" in sig.edited_paths


def test_collects_notebook_edit_path(tmp_path: Path) -> None:
    t = _write_transcript(
        tmp_path / "t.jsonl",
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "usage": {"output_tokens": 5},
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "NotebookEdit",
                                "input": {"notebook_path": "/repo/nb.ipynb"},
                            }
                        ],
                    },
                }
            )
        ],
    )
    sig = read_session_signal(t)
    assert "/repo/nb.ipynb" in sig.edited_paths


def test_ignores_non_edit_tools(tmp_path: Path) -> None:
    t = _write_transcript(
        tmp_path / "t.jsonl",
        [
            _assistant_tool_use("Read", "/repo/app/main.py"),
            _assistant_tool_use("Bash", "/repo/whatever"),
        ],
    )
    sig = read_session_signal(t)
    assert sig.edited_paths == ()


def test_edited_paths_default_empty_for_plain_transcript(tmp_path: Path) -> None:
    t = _write_transcript(
        tmp_path / "t.jsonl",
        [json.dumps({"type": "assistant", "message": {"usage": {"output_tokens": 3}}})],
    )
    sig = read_session_signal(t)
    assert sig.edited_paths == ()
    assert sig.output_tokens == 3
