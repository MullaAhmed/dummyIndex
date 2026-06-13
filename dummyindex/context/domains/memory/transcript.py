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


# Tool names whose ``input.file_path`` (or ``notebook_path``) marks a file the
# session actually edited — the source-drift attribution signal the reconcile
# gate keys on. Read tools (Read/Grep/Bash) never appear here.
_EDIT_TOOL_NAMES: frozenset[str] = frozenset({"Edit", "Write", "NotebookEdit"})


@dataclass(frozen=True)
class SessionSignal:
    """Coarse signals about the current session, read from its transcript.

    ``edited_paths`` are the file paths of every Write/Edit/NotebookEdit
    tool_use in the session — the gate uses them to tell whether THIS session
    plausibly caused source drift (vs inheriting it). Defaulted to ``()`` so a
    pre-attribution ``SessionSignal(...)`` construction stays valid.
    """

    output_tokens: int
    subagent_file_count: int
    main_turns: int
    edited_paths: tuple[str, ...] = ()


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
    edited: list[str] = []
    seen_edits: set[str] = set()
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
                if isinstance(usage, dict):
                    output_tokens += int(usage.get("output_tokens") or 0)
                main_turns += 1
                for path in _edited_paths_in(msg.get("content")):
                    if path not in seen_edits:
                        seen_edits.add(path)
                        edited.append(path)
    except OSError:
        pass
    return SessionSignal(
        output_tokens=output_tokens,
        subagent_file_count=_subagent_file_count(main_transcript),
        main_turns=main_turns,
        edited_paths=tuple(edited),
    )


def _edited_paths_in(content: object) -> list[str]:
    """Pull the edited file path from every Write/Edit/NotebookEdit tool_use in
    one assistant message's ``content`` block. Tolerant of any shape."""
    if not isinstance(content, list):
        return []
    paths: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") not in _EDIT_TOOL_NAMES:
            continue
        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            continue
        raw = tool_input.get("file_path") or tool_input.get("notebook_path")
        if isinstance(raw, str) and raw:
            paths.append(raw)
    return paths
