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
from datetime import datetime, timezone
from pathlib import Path

from .corrections import directive_events
from .models import SkillDirectiveEvent, ToolCallRecord
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
_SKILL_LINE_MARKERS = ("skill", "normal mode", "adhd mode")


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


def iter_main_transcript_files(project_dir: Path) -> tuple[Path, ...]:
    """Root-level transcript JSONLs only; nested subagent logs are excluded."""
    try:
        return tuple(sorted(project_dir.glob("*.jsonl")))
    except OSError:
        return ()


def _iter_json_lines(path: Path) -> Iterator[tuple[int, dict]]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_number, raw in enumerate(fh):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(obj, dict):
                    yield line_number, obj
    except OSError:
        return


def _iter_skill_json_lines(path: Path) -> Iterator[tuple[int, dict]]:
    """Yield only rows that can possibly match the correction grammar.

    Main transcripts are large because tool results and assistant messages are
    also JSONL rows. Every supported named directive contains ``skill``; the
    only exceptions are the fixed ADHD revocation phrases. Rejecting all other
    lines before ``json.loads`` keeps SessionStart work proportional to actual
    candidate prompts without weakening the parser.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_number, raw in enumerate(fh):
                # Claude's own JSONL writer uses one of these two layouts.
                # Non-user rows cannot satisfy `_human_prompt_text`, so avoid
                # allocating/lowercasing and decoding their often-large tool
                # payloads in the first place.
                if '"type":"user"' not in raw and '"type": "user"' not in raw:
                    continue
                lowered = raw.lower()
                if not any(marker in lowered for marker in _SKILL_LINE_MARKERS):
                    continue
                try:
                    obj = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(obj, dict):
                    yield line_number, obj
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
    for _line_number, obj in _iter_json_lines(path):
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


def _resolved_cwd_matches(value: object, repo_root: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        candidate = Path(value).expanduser()
        # Claude normally records the already-resolved absolute cwd. Avoid a
        # filesystem realpath/lstat walk for that overwhelmingly common case,
        # especially on mounted Windows filesystems; unusual relative,
        # symlinked, or ``..`` forms still take the exact resolve path.
        if candidate.is_absolute() and candidate == repo_root:
            return True
        return candidate.resolve() == repo_root
    except (OSError, RuntimeError, ValueError):
        return False


def _human_prompt_text(obj: dict) -> str | None:
    """Extract only an external human prompt, never a synthetic user row."""
    if obj.get("type") != "user" or obj.get("userType") != "external":
        return None
    if any(
        obj.get(flag) is True
        for flag in (
            "isMeta",
            "isSidechain",
            "isCompactSummary",
            "isVisibleInTranscriptOnly",
            "synthetic",
        )
    ):
        return None
    origin = obj.get("origin")
    if origin is not None:
        if not isinstance(origin, dict) or origin.get("kind") != "human":
            return None

    message = obj.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None

    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            return None
        text = block.get("text")
        if not isinstance(text, str):
            return None
        text_parts.append(text)
    return "\n".join(text_parts) if text_parts else None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_skill_directive_events(
    path: Path,
    *,
    repo_root: Path,
    fallback_prefix: tuple[int, ...],
) -> tuple[SkillDirectiveEvent, ...]:
    """Parse privacy-minimized skill directives from one main transcript."""
    try:
        resolved_root = repo_root.resolve()
    except (OSError, RuntimeError):
        return ()

    events: list[SkillDirectiveEvent] = []
    for line_number, obj in _iter_skill_json_lines(path):
        if not _resolved_cwd_matches(obj.get("cwd"), resolved_root):
            continue
        text = _human_prompt_text(obj)
        if text is None:
            continue
        timestamp = obj.get("timestamp")
        timestamp_text = timestamp if isinstance(timestamp, str) else ""
        session_id = obj.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            session_id = path.stem
        event_uuid = obj.get("uuid")
        events.extend(
            directive_events(
                text,
                event_uuid=event_uuid if isinstance(event_uuid, str) else None,
                timestamp=timestamp_text,
                session_id=session_id,
                occurred_at=_parse_timestamp(timestamp),
                fallback_order=(*fallback_prefix, line_number),
            )
        )
    return tuple(events)
