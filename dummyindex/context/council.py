"""Council audit log + resumption helpers.

The multi-agent council writes a structured log per feature at
``features/<feature_id>/council/_council-log.json``. Every persona
invocation appends an entry. The skill consults the log to:

- Resume a partially-completed feature (skip stages already `complete`).
- Surface failures so a re-run targets only the failed agents.
- Audit what ran and when, for human verification.

Log schema (atomic appends):

    {
      "schema_version": 1,
      "feature_id": "authentication",
      "entries": [
        {
          "timestamp": "2026-05-24T20:45:00+00:00",
          "stage": 1,
          "agent": "architect",
          "status": "started",
          "note": null
        },
        {
          "timestamp": "2026-05-24T20:46:12+00:00",
          "stage": 1,
          "agent": "architect",
          "status": "complete",
          "note": null
        },
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

SCHEMA_VERSION = 1

_VALID_STATUSES = frozenset({"started", "complete", "failed", "skipped"})


class CouncilLogError(ValueError):
    """Raised on invalid status / stage / feature."""


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    stage: int
    agent: str
    status: str
    note: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "agent": self.agent,
            "status": self.status,
            "note": self.note,
        }


def append_log(
    features_dir: Path,
    *,
    feature_id: str,
    stage: int,
    agent: str,
    status: str,
    note: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
) -> LogEntry:
    """Append a single entry to ``features/<feature_id>/council/_council-log.json``.

    Creates the file (and the ``council/`` folder) if missing.
    Validates ``status`` against the four allowed values.
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise CouncilLogError(f"feature folder not found: {feat_dir}")

    if status not in _VALID_STATUSES:
        raise CouncilLogError(
            f"status must be one of {sorted(_VALID_STATUSES)}, got {status!r}"
        )
    if not isinstance(stage, int) or stage < 0:
        raise CouncilLogError(f"stage must be a non-negative int, got {stage!r}")
    if not agent or "/" in agent:
        raise CouncilLogError(f"invalid agent name: {agent!r}")

    council_dir = feat_dir / "council"
    council_dir.mkdir(parents=True, exist_ok=True)
    log_path = council_dir / "_council-log.json"

    if log_path.exists():
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}

    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("feature_id", feature_id)
    entries = payload.setdefault("entries", [])

    entry = LogEntry(
        timestamp=(now or _dt.datetime.now(_dt.timezone.utc)).isoformat(timespec="seconds"),
        stage=stage,
        agent=agent,
        status=status,
        note=note,
    )
    entries.append(entry.to_dict())

    tmp = log_path.with_suffix(log_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(log_path)
    return entry


def read_log(features_dir: Path, feature_id: str) -> list[LogEntry]:
    """Return every entry for a feature's council log. Empty list if absent."""
    log_path = features_dir.resolve() / feature_id / "council" / "_council-log.json"
    if not log_path.exists():
        return []
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out: list[LogEntry] = []
    for raw in payload.get("entries", []):
        out.append(
            LogEntry(
                timestamp=raw.get("timestamp", ""),
                stage=int(raw.get("stage", 0)),
                agent=raw.get("agent", ""),
                status=raw.get("status", ""),
                note=raw.get("note"),
            )
        )
    return out


def is_stage_complete(features_dir: Path, feature_id: str, stage: int) -> bool:
    """True if every agent that started ``stage`` for ``feature_id`` reached
    ``complete``. False if any agent is still ``started`` or ``failed``."""
    by_agent: dict[str, str] = {}
    for entry in read_log(features_dir, feature_id):
        if entry.stage != stage:
            continue
        by_agent[entry.agent] = entry.status
    if not by_agent:
        return False
    return all(v == "complete" or v == "skipped" for v in by_agent.values())


def latest_status(
    features_dir: Path, feature_id: str, stage: int, agent: str
) -> Optional[str]:
    """The most recent status for one (stage, agent) pair, or None."""
    found: Optional[str] = None
    for entry in read_log(features_dir, feature_id):
        if entry.stage == stage and entry.agent == agent:
            found = entry.status
    return found
