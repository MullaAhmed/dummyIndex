"""Discover transcript files and parse them into tool-call records.

Reimplements the shape of headroom's ``ClaudeCodePlugin.discover_projects`` /
``_scan_session`` (``learn/plugins/claude.py``): walk a ``projects/`` store
whose immediate subdirectories are per-project transcript folders, and within
each folder read every ``*.jsonl`` (Claude Code nests subagent transcripts
under ``<session>/subagents/``, so a recursive glob picks those up too — the
same reasoning ``scan_project(include_subagents=True)`` documents). No model
call, no network: this module only parses JSON already on disk.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from .models import ToolCallRecord
from .signatures import canonical_signature

# Snippet markers a tool_result's content is checked against when the
# transcript itself doesn't carry an explicit ``is_error`` flag. Deliberately
# a small, original list (not headroom's `_shared.is_error_content`/
# `classify_error` tables) — the technique (regex/substring sniff over the
# result content) is reimplemented, the specific patterns are dummyindex's
# own choice for a Read/Grep/Edit/Bash tool surface.
_ERROR_MARKERS = (
    "error:",
    "traceback (most recent call last)",
    "no such file or directory",
    "permission denied",
    "command not found",
    "modulenotfounderror",
    "importerror",
    "syntaxerror",
    "does not exist",
    "cannot find",
)
_ERROR_SNIFF_WINDOW = 1000


def _looks_like_error(content: str) -> bool:
    if not content:
        return False
    snippet = content[:_ERROR_SNIFF_WINDOW].lower()
    return any(marker in snippet for marker in _ERROR_MARKERS)


def discover_project_dirs(store_dir: Path) -> tuple[Path, ...]:
    """Immediate project subdirectories of a transcript store.

    Empty tuple when the store doesn't exist — mirrors the tolerant
    ``detect()``-then-``discover_projects()`` pattern upstream, since a
    missing store (host never installed / never used, or a stale override)
    is a normal, not-an-error state for a deterministic scanner.
    """
    if not store_dir.is_dir():
        return ()
    try:
        entries = sorted(store_dir.iterdir())
    except OSError:
        # A store that exists but cannot be listed (mode 000, root-owned) is
        # the same class of environmental condition as a missing one, and the
        # docstring above promises that is not an error. `_iter_json_lines`
        # already swallows the file-level equivalent.
        return ()
    dirs = []
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if any(entry.rglob("*.jsonl")):
            dirs.append(entry)
    return tuple(dirs)


def iter_transcript_files(project_dir: Path) -> tuple[Path, ...]:
    """Every transcript JSONL under one project dir, main and subagent alike."""
    return tuple(sorted(project_dir.rglob("*.jsonl")))


def _iter_json_lines(path: Path) -> Iterator[dict]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def parse_transcript(path: Path) -> tuple[ToolCallRecord, ...]:
    """Parse one transcript JSONL into ``ToolCallRecord``s, oldest first.

    Best-effort and tolerant of partial/malformed lines, matching this
    domain's existing ``transcript.read_session_signal`` reader style: an
    unreadable file or a bad line yields whatever was parsed so far, it never
    raises.
    """
    pending: dict[str, tuple[str, dict]] = {}
    records: list[ToolCallRecord] = []
    for obj in _iter_json_lines(path):
        line_type = obj.get("type")
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue

        if line_type == "assistant":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                call_id = block.get("id")
                name = block.get("name")
                tool_input = block.get("input")
                if call_id and name and isinstance(tool_input, dict):
                    pending[call_id] = (name, tool_input)
        elif line_type == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call_id = block.get("tool_use_id")
                if call_id not in pending:
                    continue
                name, tool_input = pending.pop(call_id)
                raw_output = block.get("content", "")
                if not isinstance(raw_output, str):
                    raw_output = json.dumps(raw_output, default=str)
                is_error = bool(block.get("is_error", False)) or _looks_like_error(
                    raw_output
                )
                records.append(
                    ToolCallRecord(
                        tool_name=name,
                        signature=canonical_signature(name, tool_input),
                        is_error=is_error,
                        output_bytes=len(raw_output.encode("utf-8")),
                    )
                )
    return tuple(records)
