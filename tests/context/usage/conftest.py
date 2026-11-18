"""A synthetic `~/.claude/projects/` corpus for usage tests.

One deterministic corpus exercises every hard path: a cross-file duplicate
turn, a `<synthetic>` placeholder, a non-assistant line, subagent turns, two
sessions, two projects, two calendar days, and a >5-hour idle gap (so block
splitting is real, not assumed). Timestamps and token counts are fixed so
tests assert exact numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _line(
    *,
    ts: str,
    uuid: str,
    msg_id: str | None,
    req: str,
    model: str,
    usage: dict,
    type_: str = "assistant",
) -> str:
    obj = {
        "type": type_,
        "timestamp": ts,
        "uuid": uuid,
        "requestId": req,
        "message": {"id": msg_id, "model": model, "usage": usage},
    }
    return json.dumps(obj)


def _usage(inp: int, cw: int, cr: int, out: int) -> dict:
    return {
        "input_tokens": inp,
        "cache_creation_input_tokens": cw,
        "cache_read_input_tokens": cr,
        "output_tokens": out,
    }


_OPUS = "claude-opus-4-8"


@pytest.fixture
def usage_corpus(tmp_path: Path) -> Path:
    """Build the corpus under ``tmp_path/projects`` and return that root."""
    root = tmp_path / "projects"
    proj_a = root / "proj-a"
    proj_b = root / "proj-b"
    (proj_a / "s1" / "subagents").mkdir(parents=True)
    proj_b.mkdir(parents=True)

    # Session s1 (project A): two day-1 turns, a duplicate of t2, a synthetic
    # placeholder, a non-assistant line, and a day-2 turn.
    s1_lines = [
        _line(
            ts="2026-06-01T10:00:00Z",
            uuid="u1",
            msg_id="m1",
            req="r1",
            model=_OPUS,
            usage=_usage(100, 10, 1000, 50),
        ),
        _line(
            ts="2026-06-01T10:30:00Z",
            uuid="u2",
            msg_id="m2",
            req="r2",
            model=_OPUS,
            usage=_usage(2, 5, 1200, 80),
        ),
        # Duplicate of t2 — same message id, different uuid, identical usage.
        _line(
            ts="2026-06-01T10:30:00Z",
            uuid="u2b",
            msg_id="m2",
            req="r2",
            model=_OPUS,
            usage=_usage(2, 5, 1200, 80),
        ),
        # Synthetic placeholder — must be skipped.
        _line(
            ts="2026-06-01T10:31:00Z",
            uuid="usyn",
            msg_id=None,
            req="",
            model="<synthetic>",
            usage=_usage(0, 0, 0, 0),
        ),
        # A non-assistant line — must be ignored.
        _line(
            ts="2026-06-01T10:32:00Z",
            uuid="uuser",
            msg_id="mu",
            req="ru",
            model=_OPUS,
            usage=_usage(9, 9, 9, 9),
            type_="user",
        ),
        _line(
            ts="2026-06-02T09:00:00Z",
            uuid="u3",
            msg_id="m3",
            req="r3",
            model=_OPUS,
            usage=_usage(3, 0, 2000, 120),
        ),
    ]
    (proj_a / "s1.jsonl").write_text("\n".join(s1_lines) + "\n", encoding="utf-8")

    # One subagent turn for s1.
    (proj_a / "s1" / "subagents" / "agent-1.jsonl").write_text(
        _line(
            ts="2026-06-01T10:05:00Z",
            uuid="ua1",
            msg_id="a1",
            req="ra1",
            model=_OPUS,
            usage=_usage(1, 2, 500, 400),
        )
        + "\n",
        encoding="utf-8",
    )

    # Session s2 (project B): a single turn at 20:00 — >5h after s1's morning
    # activity and >5h before s1's day-2 turn, forcing three blocks.
    (proj_b / "s2.jsonl").write_text(
        _line(
            ts="2026-06-01T20:00:00Z",
            uuid="u4",
            msg_id="m4",
            req="r4",
            model=_OPUS,
            usage=_usage(10, 0, 300, 20),
        )
        + "\n",
        encoding="utf-8",
    )
    return root
