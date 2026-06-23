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

from .log_scan import last_matching

SCHEMA_VERSION = 1

_VALID_STATUSES = frozenset({"started", "complete", "failed", "skipped"})

# Forced re-council: `council-batch --feature ID --force` appends a stage-0
# reset marker under this agent name. Entries BEFORE the latest marker are
# archived history — `is_stage_complete` only counts entries after it, so a
# fully-logged feature re-surfaces from stage 1 while the append-only log
# keeps the full audit trail.
RECOUNCIL_AGENT = "recouncil"
RECOUNCIL_NOTE = "force-recouncil"

# Synthetic completion entries for enrichment that predates the council-batch
# log convention (`council-log backfill`).
BACKFILL_AGENT = "backfill"
BACKFILL_NOTE = "backfilled-from-artifacts"

# Outcome-C standalone features log exactly one stage-0 complete entry whose
# note starts with this prefix (see skills/council/18-filter-trivial.md) —
# they are done by design and must never be rescheduled.
STANDALONE_NOTE_PREFIX = "standalone"

# Marker prose the deterministic builder bakes into its spec.md / flow .md
# stubs (features/render.py). Backfill treats a doc carrying its marker as
# NOT enriched — only council-authored artifacts count.
_SPEC_STUB_MARKER = "_Deterministic stub"
_FLOW_STUB_MARKER = "_Deterministic trace"

# Stage numbers follow the council-log convention (council/00-overview.md +
# council_batch.CouncilStage): specify=1, plan=2, critique=3, flow=4.
_ARTIFACT_STAGE_DOCS: tuple[tuple[int, str], ...] = (
    (1, "spec.md"),
    (2, "plan.md"),
    (3, "concerns.md"),
)
_FLOW_STAGE = 4


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
    ``complete``. False if any agent is still ``started`` or ``failed``.

    Only entries after the latest reset marker count (see
    :func:`append_reset_marker`) — a forced re-council starts a fresh run.
    """
    by_agent: dict[str, str] = {}
    for entry in read_log(features_dir, feature_id):
        if _is_reset_marker(entry):
            by_agent = {}
            continue
        if entry.stage != stage:
            continue
        by_agent[entry.agent] = entry.status
    if not by_agent:
        return False
    return all(v == "complete" or v == "skipped" for v in by_agent.values())


def _is_reset_marker(entry: LogEntry) -> bool:
    return entry.stage == 0 and entry.agent == RECOUNCIL_AGENT


def append_reset_marker(
    features_dir: Path, feature_id: str, *, now: Optional[_dt.datetime] = None
) -> LogEntry:
    """Start a fresh council run for a feature (forced re-council).

    Appends a stage-0 ``recouncil`` marker; ``is_stage_complete`` /
    ``is_standalone_complete`` ignore everything before the latest marker, so
    the feature re-surfaces from stage 1 while the log stays the audit trail.
    """
    return append_log(
        features_dir,
        feature_id=feature_id,
        stage=0,
        agent=RECOUNCIL_AGENT,
        status="started",
        note=RECOUNCIL_NOTE,
        now=now,
    )


def is_standalone_complete(features_dir: Path, feature_id: str) -> bool:
    """True for an Outcome-C standalone feature — done by design.

    Detected via the stage-0 complete entry whose note starts with
    ``standalone`` (the exact convention 18-filter-trivial.md mandates).
    A later reset marker (forced re-council) clears the exemption.
    """
    standalone = False
    for entry in read_log(features_dir, feature_id):
        if _is_reset_marker(entry):
            standalone = False
            continue
        if (
            entry.stage == 0
            and entry.status == "complete"
            and (entry.note or "").startswith(STANDALONE_NOTE_PREFIX)
        ):
            standalone = True
    return standalone


def backfill_log_from_artifacts(
    features_dir: Path, feature_id: str, *, now: Optional[_dt.datetime] = None
) -> tuple[int, ...]:
    """Append synthetic ``complete`` entries for stages whose council-authored
    artifacts already exist on disk but have no log records.

    For features enriched before the council-batch log convention (v0.20):
    stage 1 when ``spec.md`` is enriched (not the deterministic stub), stage 2
    when ``plan.md`` exists, stage 3 when ``concerns.md`` exists, stage 4 when
    flow narratives exist and none is the deterministic stub. A stage with ANY
    existing entry (started/failed/anything, even pre-reset) is never touched
    — the log stays the single authoritative audit trail. Returns the stages
    backfilled (idempotent: a second run returns ``()``).

    Raises ``CouncilLogError`` when the feature folder is missing.
    """
    features_dir = features_dir.resolve()
    feat_dir = features_dir / feature_id
    if not feat_dir.is_dir():
        raise CouncilLogError(f"feature folder not found: {feat_dir}")

    logged_stages = {entry.stage for entry in read_log(features_dir, feature_id)}
    backfilled: list[int] = []
    for stage, doc_name in _ARTIFACT_STAGE_DOCS:
        if stage in logged_stages:
            continue
        if _is_enriched_doc(feat_dir / doc_name, stub_marker=_SPEC_STUB_MARKER):
            backfilled.append(stage)
    if _FLOW_STAGE not in logged_stages and _has_enriched_flows(feat_dir):
        backfilled.append(_FLOW_STAGE)

    for stage in backfilled:
        append_log(
            features_dir,
            feature_id=feature_id,
            stage=stage,
            agent=BACKFILL_AGENT,
            status="complete",
            note=BACKFILL_NOTE,
            now=now,
        )
    return tuple(backfilled)


def needs_artifact_backfill(features_dir: Path, feature_id: str) -> bool:
    """True when a feature has enrichment artifacts but an empty council log —
    the pre-v0.20 shape the frontier would wrongly reschedule from stage 1."""
    if read_log(features_dir, feature_id):
        return False
    feat_dir = features_dir.resolve() / feature_id
    if not feat_dir.is_dir():
        return False
    return any(
        _is_enriched_doc(feat_dir / doc_name, stub_marker=_SPEC_STUB_MARKER)
        for _, doc_name in _ARTIFACT_STAGE_DOCS
    )


def _is_enriched_doc(path: Path, *, stub_marker: str) -> bool:
    """A doc counts as enriched when it exists and isn't a deterministic stub."""
    if not path.is_file():
        return False
    try:
        return stub_marker not in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _has_enriched_flows(feat_dir: Path) -> bool:
    """At least one flow narrative exists and none is the deterministic stub."""
    flows_dir = feat_dir / "flows"
    if not flows_dir.is_dir():
        return False
    flow_docs = sorted(flows_dir.glob("*.md"))
    if not flow_docs:
        return False
    return all(
        _is_enriched_doc(doc, stub_marker=_FLOW_STUB_MARKER) for doc in flow_docs
    )


def latest_status(
    features_dir: Path, feature_id: str, stage: int, agent: str
) -> Optional[str]:
    """The most recent status for one (stage, agent) pair, or None.

    Load-bearing for resumption; the ``last_matching`` scan preserves the exact
    "keep the last entry matching a (key, agent) pair, return its status"
    semantics.
    """
    return last_matching(
        read_log(features_dir, feature_id),
        lambda entry: entry.stage == stage and entry.agent == agent,
    )
