"""Stdlib-only reader for the current Claude Code session transcript.

Coarse signals (output tokens, subagents, turns) decide whether to nudge a
handoff. Same JSONL as `dummyindex usage`, but `context` never imports `usage`
(CONVENTIONS §2 layering), and a per-file sum replaces its cross-transcript
dedup: these numbers are only a heuristic gate.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"


# Tool names whose ``input.file_path`` (or ``notebook_path``) marks a file the
# session actually edited — the source-drift attribution signal the reconcile
# gate keys on. Read tools (Read/Grep/Bash) never appear here.
_EDIT_TOOL_NAMES: frozenset[str] = frozenset({"Edit", "Write", "NotebookEdit"})


@dataclass(frozen=True)
class SessionSignal:
    """Coarse signals about the current session, read from its transcript.

    ``edited_paths``: deduplicated Write/Edit/NotebookEdit paths from the main
    transcript, telling whether THIS session plausibly caused source drift.
    ``subagent_file_count`` feeds ``nudge.is_significant``; ``subagent_edit_count``
    counts edits inside subagent transcripts, so a read-only fan-out doesn't trip
    the drift gate. Defaults keep pre-attribution constructions valid.
    """

    output_tokens: int
    subagent_file_count: int
    main_turns: int
    edited_paths: tuple[str, ...] = ()
    subagent_edit_count: int = 0


def resolve_session_id() -> str | None:
    """The live session id from the environment, or None when unset."""
    return os.environ.get(_SESSION_ID_ENV) or None


def _projects_root() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config_dir) if config_dir else Path.home() / ".claude"
    return base / "projects"


def _encode_slug(path: Path) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(path))


def find_main_transcript(*, session_id: str | None, cwd: Path) -> Path | None:
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


def _subagent_dir(main_transcript: Path) -> Path:
    return main_transcript.with_suffix("") / "subagents"


def _subagent_file_count(main_transcript: Path) -> int:
    d = _subagent_dir(main_transcript)
    return len(tuple(d.glob("agent-*.jsonl"))) if d.is_dir() else 0


def _subagent_edit_count(main_transcript: Path) -> int:
    """Count Edit/Write/NotebookEdit tool-uses across every subagent transcript.

    A ``/dummyindex-build`` run edits inside subagents
    (``<transcript>/subagents/agent-*.jsonl``), whose assistant rows match the
    main transcript's shape, so :func:`_edited_paths_in` parses them. Counting
    edits, not files, lets a read-only fan-out pass the source-drift gate.
    Best-effort: bad lines and unreadable files are skipped.
    """
    d = _subagent_dir(main_transcript)
    if not d.is_dir():
        return 0
    count = 0
    for agent_file in d.glob("agent-*.jsonl"):
        try:
            with agent_file.open("r", encoding="utf-8") as fh:
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
                    count += len(_edited_paths_in(msg.get("content")))
        except OSError:
            continue
    return count


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
        subagent_edit_count=_subagent_edit_count(main_transcript),
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
