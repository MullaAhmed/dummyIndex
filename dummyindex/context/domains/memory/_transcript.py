"""Stdlib-only reader for the current Claude Code session transcript.

The memory domain needs coarse signals from the live session (output-token
volume, whether subagents ran, turn count) to decide whether to nudge a
handoff. It reads the same JSONL transcripts as `dummyindex usage`, but stays
stdlib-only so the `context` layer never imports the `usage` domain
(CONVENTIONS §2 layering). These numbers are a heuristic gate, so this does
NOT replicate usage's cross-transcript dedup — a per-file sum is sufficient.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"


@dataclass(frozen=True)
class SessionSignal:
    """Coarse signals about the current session, read from its transcript."""

    output_tokens: int
    subagent_file_count: int
    main_turns: int


def resolve_session_id() -> Optional[str]:
    """The live session id from the environment, or None when unset."""
    return os.environ.get(_SESSION_ID_ENV) or None


def _projects_root() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config_dir) if config_dir else Path.home() / ".claude"
    return base / "projects"


def _encode_slug(path: Path) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(path))


def find_main_transcript(*, session_id: Optional[str], cwd: Path) -> Optional[Path]:
    """Locate the current session's main transcript JSONL.

    `session_id` is authoritative: return its transcript or None. With no
    session id, fall back to the newest transcript for `cwd`'s project.
    """
    root = _projects_root()
    if session_id:
        matches = sorted(
            root.glob(f"*/{session_id}.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return matches[0] if matches else None
    slug_dir = root / _encode_slug(cwd)
    cands = sorted(
        slug_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return cands[0] if cands else None


def _subagent_file_count(main_transcript: Path) -> int:
    d = main_transcript.with_suffix("") / "subagents"
    return len(tuple(d.glob("agent-*.jsonl"))) if d.is_dir() else 0


def read_session_signal(main_transcript: Path) -> SessionSignal:
    """Stream the main transcript for coarse signals. Best-effort: an
    unreadable/partial file yields whatever was parsed so far."""
    output_tokens = 0
    main_turns = 0
    try:
        with main_transcript.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "assistant":
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                output_tokens += int(usage.get("output_tokens") or 0)
                main_turns += 1
    except OSError:
        pass
    return SessionSignal(
        output_tokens=output_tokens,
        subagent_file_count=_subagent_file_count(main_transcript),
        main_turns=main_turns,
    )
