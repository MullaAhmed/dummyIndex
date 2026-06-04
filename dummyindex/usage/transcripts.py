"""Read Claude Code transcripts into `TurnUsage` records.

This is the only I/O-touching module in the usage area. It locates the
projects directory, streams the JSONL transcripts line by line (never slurps
— some are tens of MB), parses assistant turns, and **deduplicates**: Claude
Code rewrites the same assistant message across lines (and across resumed /
forked transcripts), so the same logical turn — keyed by `message.id` +
`requestId` — must be counted once or every cumulative number inflates.

Path layout under `~/.claude/projects/`:

    <project-slug>/<session-id>.jsonl                     # main thread
    <project-slug>/<session-id>/subagents/agent-*.jsonl   # Task/subagents

`session_id` and `project` are derived from that path, so a subagent turn is
attributed to its parent session.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .enums import SYNTHETIC_MODEL
from .errors import UsageError
from .models import TurnUsage

# Env var Claude Code sets for the live session; the exact, non-heuristic way
# to identify the current chat.
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"


def default_projects_root() -> Path:
    """`~/.claude/projects`, honouring `CLAUDE_CONFIG_DIR` when set."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config_dir) if config_dir else Path.home() / ".claude"
    return base / "projects"


def resolve_session_id() -> Optional[str]:
    """The live session id from the environment, or None when unset."""
    sid = os.environ.get(SESSION_ID_ENV)
    return sid or None


def encode_project_slug(path: Path) -> str:
    """Claude Code's cwd → project-dir encoding: every non-alphanumeric → '-'."""
    return "".join(c if c.isalnum() else "-" for c in str(path))


def find_main_transcript(
    projects_root: Path, *, session_id: Optional[str], cwd: Path
) -> Optional[Path]:
    """Locate the current session's main transcript.

    `session_id` (from the environment) is **authoritative**: return its
    transcript, or None if it isn't on disk yet — never substitute a different
    session. A brand-new session whose transcript hasn't been flushed must
    report nothing, not the newest *other* session in the same project (that
    silently mislabels one chat's usage as another's).

    Only when there is no `session_id` at all do we fall back to the newest
    transcript for `cwd`'s project — a genuine best guess, flagged as such by
    the caller.
    """
    if session_id:
        matches = sorted(
            projects_root.glob(f"*/{session_id}.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return matches[0] if matches else None
    slug_dir = projects_root / encode_project_slug(cwd)
    candidates = sorted(
        slug_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return candidates[0] if candidates else None


def _parse_timestamp(raw: object) -> Optional[datetime]:
    """ISO-8601 string → timezone-aware UTC datetime. None when unparseable.

    `datetime.fromisoformat` on Python 3.10 rejects the trailing `Z`, so we
    normalise it to `+00:00` first.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedup_key(obj: dict) -> Optional[str]:
    """Stable identity for an assistant turn: `message.id|requestId`.

    Falls back to the line `uuid` when no message id is present, so genuinely
    distinct unkeyed lines are not all collapsed into one.
    """
    message = obj.get("message")
    msg_id = message.get("id") if isinstance(message, dict) else None
    if msg_id:
        return f"{msg_id}|{obj.get('requestId', '')}"
    uuid = obj.get("uuid")
    return str(uuid) if uuid else None


def _turn_from_line(
    obj: dict, *, session_id: str, project: str, is_subagent: bool
) -> Optional[TurnUsage]:
    """Build a `TurnUsage` from a parsed line, or None if it is not a real,
    usage-bearing assistant turn (skips synthetic placeholders)."""
    if obj.get("type") != "assistant":
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    model = message.get("model") or ""
    if model == SYNTHETIC_MODEL:
        return None
    timestamp = _parse_timestamp(obj.get("timestamp"))
    if timestamp is None:
        return None
    return TurnUsage(
        timestamp=timestamp,
        session_id=session_id,
        project=project,
        model=model,
        input_tokens=int(usage.get("input_tokens") or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        is_subagent=is_subagent,
    )


def _read_file(
    path: Path, *, session_id: str, project: str, is_subagent: bool, seen: set[str]
) -> Iterator[TurnUsage]:
    """Stream one transcript, yielding each unique usage-bearing turn once.

    Best-effort by design: an unreadable file (vanished mid-scan, permissions)
    is skipped rather than aborting the whole report. A read-mostly usage
    summary over a large, churning corpus should not fail because one of
    hundreds of transcripts is momentarily unreadable.
    """
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError:
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            key = _dedup_key(obj)
            if key is not None and key in seen:
                continue
            turn = _turn_from_line(
                obj, session_id=session_id, project=project, is_subagent=is_subagent
            )
            if turn is None:
                continue
            if key is not None:
                seen.add(key)
            yield turn


def _subagent_files(main_transcript: Path) -> tuple[Path, ...]:
    """The `agent-*.jsonl` files for a main transcript, if any."""
    subagents_dir = main_transcript.with_suffix("") / "subagents"
    if not subagents_dir.is_dir():
        return ()
    return tuple(sorted(subagents_dir.glob("agent-*.jsonl")))


def load_session(
    main_transcript: Path,
) -> tuple[tuple[TurnUsage, ...], tuple[TurnUsage, ...], int]:
    """Deduplicated (main_turns, subagent_turns, subagent_file_count).

    Main and subagents are deduplicated independently — a subagent's message
    ids never collide with the parent's. The file count is the number of
    subagent transcripts (distinct from the turn count, since one transcript
    holds many turns).
    """
    session_id = main_transcript.stem
    project = main_transcript.parent.name
    main_seen: set[str] = set()
    main = tuple(
        _read_file(
            main_transcript,
            session_id=session_id,
            project=project,
            is_subagent=False,
            seen=main_seen,
        )
    )
    agent_files = _subagent_files(main_transcript)
    sub_seen: set[str] = set()
    sub: list[TurnUsage] = []
    for agent_file in agent_files:
        sub.extend(
            _read_file(
                agent_file,
                session_id=session_id,
                project=project,
                is_subagent=True,
                seen=sub_seen,
            )
        )
    return main, tuple(sub), len(agent_files)


def iter_all_turns(
    projects_root: Path, *, include_subagents: bool = True
) -> Iterator[TurnUsage]:
    """Every deduplicated usage-bearing turn across all projects.

    One global seen-set spans main + subagent files so a turn duplicated across
    resumed/forked transcripts is counted once.
    """
    if not projects_root.is_dir():
        raise UsageError(
            f"projects directory not found: {projects_root}",
            path=str(projects_root),
        )
    seen: set[str] = set()
    for main_transcript in sorted(projects_root.glob("*/*.jsonl")):
        session_id = main_transcript.stem
        project = main_transcript.parent.name
        yield from _read_file(
            main_transcript,
            session_id=session_id,
            project=project,
            is_subagent=False,
            seen=seen,
        )
        if include_subagents:
            for agent_file in _subagent_files(main_transcript):
                yield from _read_file(
                    agent_file,
                    session_id=session_id,
                    project=project,
                    is_subagent=True,
                    seen=seen,
                )
