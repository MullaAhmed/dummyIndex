"""Debate resumption log for an audit — ``_debate-log.json``.

Ported from the council log (``context.domains.council``). Every persona
invocation in every round appends an entry. The skill consults the log to:

- Resume a partially-completed audit (skip rounds already ``complete``).
- Surface failures so a re-run targets only the failed auditors.
- Audit what ran and when, for human verification.

The *convergence* judgment (did the panel reach agreement?) is the skill's
call, not this log's — the log records work status (started/complete), and the
``MAX_REBUTTAL_ROUNDS`` cap bounds how far the loop may run.

Log schema (atomic appends):

    {
      "schema_version": 1,
      "slug": "audit-error-handling",
      "entries": [
        {"timestamp": "...", "round": 0, "persona": "security",
         "status": "started", "note": null},
        ...
      ]
    }
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .enums import LogStatus
from .errors import AuditLogError

LOG_SCHEMA_VERSION = 1
_DEBATE_LOG = "_debate-log.json"

_VALID_STATUSES = frozenset(s.value for s in LogStatus)


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    round: int
    persona: str
    status: str
    note: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "round": self.round,
            "persona": self.persona,
            "status": self.status,
            "note": self.note,
        }


def append_log(
    workspace: Path,
    *,
    round_num: int,
    persona: str,
    status: str,
    note: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
) -> LogEntry:
    """Append one entry to ``<workspace>/_debate-log.json``.

    ``workspace`` is the ``.context/audits/<slug>/`` directory. Creates the log
    file if missing. Validates ``status`` against the four allowed values and
    ``round_num`` against ``[0, ...]``.
    """
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise AuditLogError(f"audit folder not found: {workspace}")
    if status not in _VALID_STATUSES:
        raise AuditLogError(
            f"status must be one of {sorted(_VALID_STATUSES)}, got {status!r}"
        )
    if not isinstance(round_num, int) or round_num < 0:
        raise AuditLogError(f"round must be a non-negative int, got {round_num!r}")
    if not persona or "/" in persona:
        raise AuditLogError(f"invalid persona name: {persona!r}")

    log_path = workspace / _DEBATE_LOG
    if log_path.exists():
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Corrupt log → start fresh. The atomic tmp+replace write below
            # makes a torn write on our side impossible, so a corrupt file
            # means external tampering; we don't try to salvage partial JSON.
            payload = {}
    else:
        payload = {}

    payload.setdefault("schema_version", LOG_SCHEMA_VERSION)
    payload.setdefault("slug", workspace.name)
    entries = payload.setdefault("entries", [])

    entry = LogEntry(
        timestamp=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(
            timespec="seconds"
        ),
        round=round_num,
        persona=persona,
        status=status,
        note=note,
    )
    entries.append(entry.to_dict())

    tmp = log_path.with_suffix(log_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(log_path)
    return entry


def read_log(workspace: Path) -> tuple[LogEntry, ...]:
    """Return every entry for an audit's debate log. Empty tuple if absent."""
    log_path = workspace.resolve() / _DEBATE_LOG
    if not log_path.exists():
        return ()
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ()
    out: list[LogEntry] = []
    for raw in payload.get("entries", []):
        out.append(
            LogEntry(
                timestamp=raw.get("timestamp", ""),
                round=int(raw.get("round", 0)),
                persona=raw.get("persona", ""),
                status=raw.get("status", ""),
                note=raw.get("note"),
            )
        )
    return tuple(out)


def is_round_complete(workspace: Path, round_num: int) -> bool:
    """True if every persona that *started* ``round_num`` reached ``complete``
    (or ``skipped``). False if any is still ``started``/``failed``, or none ran."""
    by_persona: dict[str, str] = {}
    for entry in read_log(workspace):
        if entry.round != round_num:
            continue
        by_persona[entry.persona] = entry.status
    if not by_persona:
        return False
    return all(
        v in (LogStatus.COMPLETE.value, LogStatus.SKIPPED.value)
        for v in by_persona.values()
    )


def completed_rounds(workspace: Path) -> tuple[int, ...]:
    """Every round number that is fully complete, ascending. Drives resumption."""
    rounds = {entry.round for entry in read_log(workspace)}
    return tuple(sorted(r for r in rounds if is_round_complete(workspace, r)))


def latest_status(workspace: Path, round_num: int, persona: str) -> Optional[str]:
    """The most recent status for one (round, persona) pair, or None.

    NOTE: ``context.domains.council.latest_status`` runs the byte-identical
    "keep the last entry matching a (key, agent) pair, return its status" loop
    over its own log, keyed on (stage, agent). The two are deliberately *not*
    extracted into a shared helper: ``audit`` and ``council`` are independent
    peer domains with no common parent module, so sharing would create a
    cross-domain dependency that ``conventions/folder-organization.md`` warns
    against — and the loop is too small to justify a new cross-cutting module.
    """
    found: Optional[str] = None
    for entry in read_log(workspace):
        if entry.round == round_num and entry.persona == persona:
            found = entry.status
    return found
