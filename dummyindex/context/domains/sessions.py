"""Read-only, bounded, tolerant listing of Claude Code session transcripts.

Backs ``dummyindex sessions list --json`` (contract: docs/engine-contract.md
section 8, schema: docs/schemas/sessions-list.json). The store layout is the
one in ``usage/transcripts.py``::

    <projects>/<encoded-cwd>/<session-id>.jsonl
    <projects>/<encoded-cwd>/<session-id>/subagents/agent-<id>.jsonl
    <projects>/<encoded-cwd>/<session-id>/subagents/agent-<id>.meta.json

Rules that matter to consumers:

- The record ``cwd`` is authoritative; the folder name is never decoded.
- Every transcript read is bounded: at most ``2 * WINDOW_BYTES`` per file
  (the head and tail windows, or the whole file when it is small), and at most
  ``MAX_BYTES_PER_SESSION`` per main session including its subagents.
- Parsing is tolerant: unknown record types and fields are ignored, a line that
  is not a JSON object is skipped and counted into one ``unparseable_line``
  warning, and unreadable data yields ``state: "unknown"`` plus a warning.
  Nothing here raises for bad data.
- Sessions are enrichment only. Nothing is written.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# Shared with the usage reader: the same timestamp rule and the same
# `<session>/subagents/agent-*.jsonl` discovery, so the two cannot drift.
from dummyindex.usage.transcripts import _parse_timestamp, _subagent_files


class SessionState(str, Enum):
    ACTIVE = "active"
    FINISHED = "finished"
    UNKNOWN = "unknown"


# Liveness is file mtime within this window of "now" (contract section 8).
ACTIVE_WINDOW = timedelta(minutes=5)

# Read bounds. A transcript costs at most 2 * WINDOW_BYTES (head and tail);
# a main session and its subagents may read at most MAX_BYTES_PER_SESSION of
# transcripts, plus at most META_MAX_BYTES per sidecar, which is never refused.
WINDOW_BYTES = 64 * 1024
_WHOLE_FILE_MAX = 2 * WINDOW_BYTES
MAX_BYTES_PER_SESSION = 16 * 1024 * 1024
META_MAX_BYTES = 64 * 1024
MAX_SUBAGENTS_PER_SESSION = 100

_SUBAGENT_PREFIX = "agent-"
_BAD_LINE = object()

Warning = tuple[str, str]  # (code, message)


@dataclass(frozen=True)
class _Transcript:
    records: tuple[dict[str, Any], ...] = ()
    bad_lines: int = 0
    error: str | None = None


class _Budget:
    """Byte budget for one main session. A read that does not fit is refused."""

    def __init__(self, limit: int) -> None:
        self.remaining = limit

    def take(self, cost: int) -> bool:
        if cost > self.remaining:
            return False
        self.remaining -= cost
        return True

    def charge(self, cost: int) -> None:
        """Unconditional charge, for the main file, which is always read."""
        self.remaining -= cost


def list_sessions(
    projects_root: Path,
    *,
    now: datetime,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Session items under ``projects_root``, newest first.

    ``root`` keeps only items whose ``cwd`` is that directory or below it.
    A missing projects directory is an empty listing, not an error.
    """
    if not projects_root.is_dir():
        return []
    # abspath, not resolve(): resolve() rewrites junctions and subst drives,
    # so the root would stop matching the cwd that Claude recorded.
    root_key = _path_key(os.path.abspath(root)) if root is not None else None
    items: list[dict[str, Any]] = []
    for main in sorted(projects_root.glob("*/*.jsonl")):
        for item in _session_items(main, now=now):
            if root_key is None or _under(item["cwd"], root_key):
                items.append(item)
    items.sort(key=lambda it: (it["session_id"], it["agent_id"] or ""))
    items.sort(key=lambda it: it["last_event_at"] or "", reverse=True)
    return items


# ----- main sessions and subagent children ----------------------------------


def _session_items(main: Path, *, now: datetime) -> list[dict[str, Any]]:
    try:
        stat = main.stat()
    except OSError:
        return [
            _item(
                session_id=main.stem,
                cwd=None,
                state="unknown",
                warnings=[("unreadable_session", "session file could not be stat'ed")],
            )
        ]

    budget = _Budget(MAX_BYTES_PER_SESSION)
    budget.charge(min(stat.st_size, _WHOLE_FILE_MAX))
    transcript = _read_transcript(main, stat.st_size)
    active = _is_active(stat.st_mtime, now)

    warnings: list[Warning] = []
    if transcript.bad_lines:
        warnings.append(_unparseable_warning(transcript.bad_lines))
    # Identity is the file stem: that is the id `--resume` and the hook
    # session_id use. A forked or resumed transcript copies its parent's
    # records, so its first sessionId can name the parent (observed in the
    # real store); that is reported, never used as the identity.
    session_id = main.stem
    first_id = _first_str(transcript.records, "sessionId")
    if first_id is not None and first_id != session_id:
        warnings.append(
            (
                "session_id_mismatch",
                "transcript begins with records of another session (forked or resumed)",
            )
        )
    cwd = _first_str(transcript.records, "cwd")
    if cwd is None:
        warnings.append(("missing_cwd", "no cwd in records"))
    started, last = _timestamp_bounds(transcript.records)

    if not transcript.records:
        if transcript.error is not None:
            warnings.append(("unreadable_session", transcript.error))
            state = "unknown"
        elif transcript.bad_lines:
            state = "unknown"
            warnings.append(("unparseable_session", "no readable records"))
        elif active:
            state = "active"
        else:
            state = "unknown"
            warnings.append(("empty_session", "no records and not recently modified"))
    elif active:
        state = "active"
    elif _is_finished(transcript.records):
        state = "finished"
    else:
        state = "unknown"
        warnings.append(
            ("unknown_state", "no end_turn or turn_duration marker; not recent")
        )

    children, truncated = _children(
        main, parent_id=session_id, parent_cwd=cwd, now=now, budget=budget
    )
    if truncated:
        warnings.append(
            (
                "subagents_truncated",
                f"only the first {MAX_SUBAGENTS_PER_SESSION} subagents were read",
            )
        )
    main_item = _item(
        session_id=session_id,
        cwd=cwd,
        state=state,
        started=started,
        last=last,
        warnings=warnings,
    )
    return [main_item, *children]


def _children(
    main: Path,
    *,
    parent_id: str,
    parent_cwd: str | None,
    now: datetime,
    budget: _Budget,
) -> tuple[list[dict[str, Any]], bool]:
    files = _subagent_files(main)
    out = [
        _child_item(
            child,
            parent_id=parent_id,
            parent_cwd=parent_cwd,
            parent_stem=main.stem,
            now=now,
            budget=budget,
        )
        for child in files[:MAX_SUBAGENTS_PER_SESSION]
    ]
    return out, len(files) > MAX_SUBAGENTS_PER_SESSION


def _child_item(
    child: Path,
    *,
    parent_id: str,
    parent_cwd: str | None,
    parent_stem: str,
    now: datetime,
    budget: _Budget,
) -> dict[str, Any]:
    stem = child.stem
    agent_id = (
        stem[len(_SUBAGENT_PREFIX) :] if stem.startswith(_SUBAGENT_PREFIX) else stem
    )
    warnings: list[Warning] = []
    try:
        stat = child.stat()
    except OSError:
        return _item(
            session_id=parent_id,
            agent_id=agent_id,
            parent_session_id=parent_id,
            cwd=parent_cwd,
            state="unknown",
            warnings=[("unreadable_session", "subagent file could not be stat'ed")],
        )

    # The meta sidecar and mtime decide the state, so they are read first and
    # survive a refused transcript read. A refused transcript only loses the
    # record-derived fields (sessionId, cwd, timestamps), and says so.
    meta, meta_problem = _read_meta(child, budget)
    active = _is_active(stat.st_mtime, now)
    transcript_allowed = budget.take(min(stat.st_size, _WHOLE_FILE_MAX))
    if transcript_allowed:
        transcript = _read_transcript(child, stat.st_size)
    else:
        transcript = _Transcript()
        warnings.append(
            ("read_limit_reached", "transcript not read: session read budget exhausted")
        )

    if transcript.bad_lines:
        warnings.append(_unparseable_warning(transcript.bad_lines))
    # A subagent belongs to its parent folder; the record field is a cross-check.
    session_id = parent_id
    record_id = _first_str(transcript.records, "sessionId")
    if record_id is not None and record_id != parent_stem:
        warnings.append(
            ("session_id_mismatch", "subagent records name a different session")
        )
    cwd = _first_str(transcript.records, "cwd") or parent_cwd
    started, last = _timestamp_bounds(transcript.records)

    finished_flag = meta.get("finished") if meta is not None else None
    if not transcript.records and (
        transcript.error is not None or transcript.bad_lines
    ):
        state = "unknown"
        warnings.append(
            ("unparseable_session", transcript.error or "no readable records")
        )
    elif finished_flag is True:
        state = "finished"
    elif finished_flag is False and active:
        state = "active"
    else:
        state = "unknown"
        if meta_problem is not None:
            warnings.append(meta_problem)
        else:
            warnings.append(("unknown_state", "subagent not finished and not recent"))

    return _item(
        session_id=session_id,
        agent_id=agent_id,
        agent_type=_meta_str(meta, "agentType"),
        parent_session_id=parent_id,
        cwd=cwd,
        state=state,
        started=started,
        last=last,
        warnings=warnings,
    )


# ----- bounded, tolerant reading --------------------------------------------


def _read_transcript(path: Path, size: int) -> _Transcript:
    """Records from at most two windows of ``path``; never raises."""
    truncated = size > _WHOLE_FILE_MAX
    try:
        with path.open("rb") as handle:
            if truncated:
                head = handle.read(WINDOW_BYTES)
                handle.seek(size - WINDOW_BYTES)
                tail = handle.read(WINDOW_BYTES)
                # The head's last piece and the tail's first piece may be
                # partial lines cut by the window edge; drop them.
                lines = head.split(b"\n")[:-1] + tail.split(b"\n")[1:]
            else:
                lines = handle.read().split(b"\n")
    except OSError as exc:
        return _Transcript(
            error=f"file could not be read ({exc.strerror or 'OSError'})"
        )

    records: list[dict[str, Any]] = []
    bad = 0
    for raw in lines:
        parsed = _parse_line(raw)
        if parsed is None:
            continue
        if parsed is _BAD_LINE:
            bad += 1
            continue
        records.append(parsed)  # type: ignore[arg-type]
    return _Transcript(records=tuple(records), bad_lines=bad)


def _parse_line(raw: bytes) -> dict[str, Any] | None | object:
    """None for a blank line, the sentinel for a bad line, else the object."""
    text = raw.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return _BAD_LINE
    if not isinstance(obj, dict):
        return _BAD_LINE
    return obj


def _read_meta(
    child: Path, budget: _Budget
) -> tuple[dict[str, Any] | None, Warning | None]:
    """The subagent's meta sidecar. Never refused by the budget: it is capped at
    META_MAX_BYTES per file and it is the authority for the subagent's state."""
    meta_path = child.with_name(child.stem + ".meta.json")
    if not meta_path.exists():
        return None, ("missing_meta", "no .meta.json sidecar for subagent")
    try:
        size = meta_path.stat().st_size
    except OSError:
        return None, ("unreadable_meta", "meta sidecar could not be stat'ed")
    if size > META_MAX_BYTES:
        return None, ("unreadable_meta", "meta sidecar exceeds size limit")
    budget.charge(size)
    try:
        obj = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, ("unreadable_meta", "meta sidecar is not valid JSON")
    if not isinstance(obj, dict):
        return None, ("unreadable_meta", "meta sidecar is not a JSON object")
    return obj, None


# ----- record interpretation -------------------------------------------------


def _is_finished(records: tuple[dict[str, Any], ...]) -> bool:
    last = records[-1]
    if last.get("type") == "system" and last.get("subtype") == "turn_duration":
        return True
    for rec in reversed(records):
        if rec.get("type") == "assistant":
            message = rec.get("message")
            return (
                isinstance(message, dict) and message.get("stop_reason") == "end_turn"
            )
    return False


def _first_str(records: Iterable[dict[str, Any]], key: str) -> str | None:
    for rec in records:
        value = rec.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _timestamp_bounds(
    records: Iterable[dict[str, Any]],
) -> tuple[datetime | None, datetime | None]:
    stamps = [t for t in (_parse_timestamp(r.get("timestamp")) for r in records) if t]
    if not stamps:
        return None, None
    return stamps[0], stamps[-1]


def _is_active(mtime_epoch: float, now: datetime) -> bool:
    modified = datetime.fromtimestamp(mtime_epoch, tz=timezone.utc)
    return now - modified <= ACTIVE_WINDOW


def _meta_str(meta: dict[str, Any] | None, key: str) -> str | None:
    if meta is None:
        return None
    value = meta.get(key)
    return value if isinstance(value, str) and value else None


def _unparseable_warning(count: int) -> Warning:
    noun = "line" if count == 1 else "lines"
    return ("unparseable_line", f"{count} unparseable {noun} skipped")


# ----- output shape ---------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="microseconds") if value is not None else None


def _item(
    *,
    session_id: str,
    cwd: str | None,
    state: str,
    agent_id: str | None = None,
    agent_type: str | None = None,
    parent_session_id: str | None = None,
    started: datetime | None = None,
    last: datetime | None = None,
    warnings: list[Warning] | None = None,
) -> dict[str, Any]:
    state = SessionState(state).value
    collected = list(warnings or [])
    if state == "unknown" and not collected:
        collected.append(("unknown_state", "state could not be determined"))
    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "parent_session_id": parent_session_id,
        "cwd": cwd,
        "state": state,
        "started_at": _iso(started),
        "last_event_at": _iso(last),
        "warnings": [{"code": code, "message": msg} for code, msg in collected],
    }


def _path_key(text: str) -> str:
    """Comparable form of a path string: forward slashes, no trailing slash,
    case-folded on Windows (where the file system is case-insensitive)."""
    key = text.replace("\\", "/").rstrip("/")
    return key.casefold() if os.name == "nt" else key


def _under(cwd: str | None, root_key: str) -> bool:
    if cwd is None:
        return False
    key = _path_key(cwd)
    return key == root_key or key.startswith(root_key + "/")
