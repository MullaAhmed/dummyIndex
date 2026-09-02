"""Fleet run state — durable, resumable work units for context maintenance.

A *maintain run* is one assembled maintenance loop over a set of features:
the reconcile report's work list, expanded into per-feature stage checklists
(the council stages from ``council_batch.active_stages``), checkpointed so any
killed session resumes from ``state.json`` — never from transcripts.

Layout (mirrors the committed ``gc/state.json`` precedent):

    .context/fleet/maintain-<ts>/RUN.md      human-readable run manifest
    .context/fleet/maintain-<ts>/state.json  live, atomically-written state

The ``maintain-`` prefix is load-bearing: ``.context/fleet/`` is shared with
the fleet-runner proposal's ``run-*`` dirs, and every discovery helper here
scopes itself to ``maintain-*`` so it never picks up another proposal's runs.
Everything under ``fleet/`` is **committed** — it is the durable cross-session
memory of a maintenance run; nothing lands under ``cache/``.

Frontier semantics are reused, not reinvented: ``next_unit`` returns the
earliest incomplete unit in the same stage-major order
``council_batch.next_batch`` uses (earliest active stage first, then feature
order within that stage), so a resumed run interleaves exactly like a fresh
one. All writes go through ``write_text_atomic``; a corrupt or unreadable
``state.json`` raises :class:`FleetRunError` rather than silently reading as
empty — an empty-looking state would re-dispatch already-done units, which is
precisely the failure resume exists to prevent. Discovery
(:func:`find_newest_run`) stays tolerant instead, mirroring
``drift._manifest_shas``.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from dummyindex.context.domains.atomic_io import write_text_atomic

STATE_SCHEMA_VERSION = 1
FLEET_DIR_REL = "fleet"
# Prefix-scoped: fleet-runner owns ``run-*`` under the same directory.
MAINTAIN_RUN_PREFIX = "maintain-"
STATE_REL = "state.json"
RUN_MANIFEST_REL = "RUN.md"
# Clearly-labelled heuristic reference point for "how long is left" — never
# a wall-clock promise (spec: estimates are deterministic counters only).
HEURISTIC_SECONDS_PER_UNIT = 90

# Stage numbers match the council-log convention (see council_batch).
_STAGE_NAMES: dict[int, str] = {
    1: "specify",
    2: "plan",
    3: "critique",
    4: "flow",
    5: "tree-enrich",
}


class FleetRunError(ValueError):
    """Missing, malformed, or inconsistent fleet run state."""


class UnitStatus(str, Enum):
    """Lifecycle of one dispatch unit inside a maintain run."""

    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"

    __str__ = str.__str__


@dataclass(frozen=True)
class FleetUnit:
    """One unit of LLM work: ``(feature_id, stage)`` plus its status."""

    feature_id: str
    stage: int
    name: str
    status: UnitStatus = UnitStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "name": self.name,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class FleetFeature:
    """One feature's ordered stage checklist plus its deterministic estimate."""

    feature_id: str
    estimate_nodes: int
    stages: tuple[FleetUnit, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "estimate_nodes": self.estimate_nodes,
            "stages": [u.to_dict() for u in self.stages],
        }


@dataclass(frozen=True)
class FleetRun:
    """A loaded maintain run: its directory plus the parsed state."""

    run_dir: Path
    anchor_sha: str | None
    mode: str
    created_at: str
    updated_at: str
    features: tuple[FleetFeature, ...]

    @property
    def units(self) -> tuple[FleetUnit, ...]:
        return tuple(u for f in self.features for u in f.stages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "kind": "maintain",
            "anchor_sha": self.anchor_sha,
            "mode": self.mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "features": [f.to_dict() for f in self.features],
        }


def runs_root(context_dir: Path) -> Path:
    """The ``.context/fleet/`` directory."""
    return context_dir / FLEET_DIR_REL


def find_newest_run(context_dir: Path) -> Path | None:
    """The newest ``maintain-*`` dir carrying a *parseable* ``state.json``.

    Tolerant scan (the ``drift._manifest_shas`` direction): dirs missing the
    state file or carrying unreadable/malformed JSON are skipped rather than
    raised — discovery must keep working past a half-created run. An
    *explicitly* named run goes through :func:`load_run`, which refuses.
    """
    root = runs_root(context_dir)
    if not root.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for child in sorted(root.glob(f"{MAINTAIN_RUN_PREFIX}*")):
        if not child.is_dir():
            continue
        try:
            json.loads((child / STATE_REL).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidates.append((child.name, child))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def resolve_run_dir(context_dir: Path, explicit: str | None) -> Path | None:
    """An explicit ``--run <name-or-dir>`` (validated) or the newest run.

    A bare name (``maintain-20260822-101500``) resolves under
    ``.context/fleet/``; an absolute path is honoured as-is. Raises
    :class:`FleetRunError` when the explicit target has no ``state.json``;
    returns ``None`` when nothing explicit was given and no run exists.
    """
    if not explicit:
        return find_newest_run(context_dir)
    candidate = Path(explicit)
    run_dir = (
        candidate if candidate.is_absolute() else runs_root(context_dir) / candidate
    )
    if not (run_dir / STATE_REL).is_file():
        raise FleetRunError(
            f"no state.json in {run_dir} — pass the maintain-<ts> directory "
            "created by `context maintain begin`"
        )
    return run_dir


def create_run(
    context_dir: Path,
    features: tuple[str, ...],
    estimates: dict[str, int] | None = None,
    *,
    mode: str = "standard",
    anchor_sha: str | None = None,
    stages_for_feature: dict[str, tuple[tuple[int, str], ...]] | None = None,
    now: _dt.datetime | None = None,
) -> FleetRun:
    """Write a new ``maintain-<ts>/`` run and return its parsed state.

    ``features`` is the work list in execution order. Per-feature stages come
    from ``stages_for_feature`` (an ``(stage_number, name)`` pair per active
    stage); when omitted every feature gets an empty checklist. ``estimates``
    maps feature id → deterministic node count (0 when absent).
    """
    if not features:
        raise FleetRunError("refusing to create a maintain run with no features")
    estimates = estimates or {}
    stage_map = stages_for_feature or {}
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    created = _isoformat(moment)
    run_dir = runs_root(context_dir) / f"{MAINTAIN_RUN_PREFIX}{_run_ts(moment)}"
    if (run_dir / STATE_REL).exists():
        raise FleetRunError(f"run already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    run = FleetRun(
        run_dir=run_dir,
        anchor_sha=anchor_sha,
        mode=mode,
        created_at=created,
        updated_at=created,
        features=tuple(
            FleetFeature(
                feature_id=fid,
                estimate_nodes=int(estimates.get(fid, 0)),
                stages=tuple(
                    FleetUnit(feature_id=fid, stage=stage, name=name)
                    for stage, name in stage_map.get(fid, ())
                ),
            )
            for fid in features
        ),
    )
    _save(run)
    write_text_atomic(run_dir / RUN_MANIFEST_REL, render_run_md(run))
    return run


def load_run(run_dir: Path) -> FleetRun:
    """Load + validate ``state.json`` from ``run_dir``.

    Raises :class:`FleetRunError` on absence or malformed JSON: unlike the
    tolerant discovery scan, a direct load that came back empty would make
    ``next_unit`` re-dispatch done units — the exact failure this module
    exists to prevent.
    """
    path = run_dir / STATE_REL
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FleetRunError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FleetRunError(
            f"{path} is not valid JSON ({exc}) — refusing to guess run state "
            "(repeating done units is worse than stopping)"
        ) from exc
    return _parse_state(run_dir, raw)


def _parse_state(run_dir: Path, raw: Any) -> FleetRun:
    """Validate a parsed state payload into a :class:`FleetRun`."""
    if not isinstance(raw, dict):
        raise FleetRunError(f"state.json in {run_dir} must contain an object")
    features_raw = raw.get("features", [])
    if not isinstance(features_raw, list):
        raise FleetRunError(f"state.json in {run_dir}: features must be a list")

    features: list[FleetFeature] = []
    seen: set[tuple[str, int]] = set()
    for entry in features_raw:
        if not isinstance(entry, dict):
            raise FleetRunError("each state feature entry must be an object")
        fid = entry.get("feature_id")
        if not isinstance(fid, str) or not fid:
            raise FleetRunError("a state feature entry has no usable feature_id")
        stages_raw = entry.get("stages", [])
        if not isinstance(stages_raw, list):
            raise FleetRunError(f"stages for {fid} must be a list")
        units: list[FleetUnit] = []
        for st in stages_raw:
            if not isinstance(st, dict):
                raise FleetRunError(f"{fid} has a malformed stage entry")
            stage_no = st.get("stage")
            if not isinstance(stage_no, int) or isinstance(stage_no, bool):
                raise FleetRunError(f"{fid} has a non-integer stage number")
            if (fid, stage_no) in seen:
                raise FleetRunError(f"duplicate unit {fid}/stage {stage_no}")
            seen.add((fid, stage_no))
            raw_status = st.get("status", UnitStatus.PENDING.value)
            try:
                status = UnitStatus(raw_status)
            except ValueError as exc:
                raise FleetRunError(
                    f"{fid}/stage {stage_no} has unknown status {raw_status!r}"
                ) from exc
            units.append(
                FleetUnit(
                    feature_id=fid,
                    stage=stage_no,
                    name=str(st.get("name", _STAGE_NAMES.get(stage_no, ""))),
                    status=status,
                )
            )
        nodes = entry.get("estimate_nodes", 0)
        if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes < 0:
            raise FleetRunError(f"estimate_nodes for {fid} must be a count")
        features.append(
            FleetFeature(feature_id=fid, estimate_nodes=nodes, stages=tuple(units))
        )

    anchor = raw.get("anchor_sha")
    if anchor is not None and not isinstance(anchor, str):
        raise FleetRunError("anchor_sha must be a string or null")
    return FleetRun(
        run_dir=run_dir,
        anchor_sha=anchor,
        mode=str(raw.get("mode", "standard")),
        created_at=str(raw.get("created_at", "")),
        updated_at=str(raw.get("updated_at", "")),
        features=tuple(features),
    )


def _save(run: FleetRun) -> None:
    """Atomically persist ``run``'s state (the only write boundary)."""
    write_text_atomic(
        run.run_dir / STATE_REL, json.dumps(run.to_dict(), indent=2) + "\n"
    )


def next_unit(run: FleetRun) -> FleetUnit | None:
    """The earliest incomplete unit — the run's frontier.

    Same semantics as ``council_batch.next_batch``: the earliest incomplete
    *stage* across all features wins, then feature order within that stage.
    Done/skipped units are never returned, so a killed-and-resumed loop can
    only ever move forward.
    """
    pending = [u for u in run.units if u.status is UnitStatus.PENDING]
    if not pending:
        return None
    return min(pending, key=lambda u: (u.stage, _feature_index(run, u.feature_id)))


def mark_done(
    run: FleetRun,
    feature_id: str,
    stage: int,
    *,
    status: UnitStatus = UnitStatus.DONE,
) -> FleetRun:
    """Flip one unit's status, persist atomically, return the updated run.

    Idempotent on an already-terminated unit (same status → rewrite-free
    no-op). Unknown feature/stage pairs raise :class:`FleetRunError` — a
    silent success on a typo would leave the frontier stuck forever.
    """
    found = False
    changed = False
    updated_features: list[FleetFeature] = []
    for feature in run.features:
        if feature.feature_id != feature_id:
            updated_features.append(feature)
            continue
        new_stages: list[FleetUnit] = []
        for unit in feature.stages:
            if unit.stage == stage:
                found = True
                if unit.status is not status:
                    unit = replace(unit, status=status)
                    changed = True
            new_stages.append(unit)
        updated_features.append(replace(feature, stages=tuple(new_stages)))
    if not found:
        raise FleetRunError(
            f"run {run.run_dir.name} has no unit {feature_id}/stage {stage}"
        )
    if not changed:
        return run
    updated = replace(run, features=tuple(updated_features), updated_at=_now_iso())
    _save(updated)
    return updated


def run_status(run: FleetRun, *, now: _dt.datetime | None = None) -> dict[str, Any]:
    """Counts, elapsed time, and the labelled heuristic remaining estimate."""
    counts = {s.value: 0 for s in UnitStatus}
    for u in run.units:
        counts[u.status.value] += 1
    pending = counts[UnitStatus.PENDING.value]
    elapsed_seconds: int | None = None
    if run.created_at:
        try:
            started = _dt.datetime.fromisoformat(run.created_at)
            elapsed_seconds = max(0, int((_utcnow(now) - started).total_seconds()))
        except ValueError:
            elapsed_seconds = None
    return {
        "total": len(run.units),
        "done": counts[UnitStatus.DONE.value],
        "pending": pending,
        "skipped": counts[UnitStatus.SKIPPED.value],
        "complete": len(run.units) > 0 and pending == 0,
        "elapsed_seconds": elapsed_seconds,
        "estimated_remaining_seconds_heuristic": pending * HEURISTIC_SECONDS_PER_UNIT,
        "anchor_sha": run.anchor_sha,
        "mode": run.mode,
        "run_dir": str(run.run_dir),
    }


# ----- estimator -------------------------------------------------------------


def estimate_run(
    context_dir: Path,
    features: tuple[str, ...],
    mode: str,
) -> dict[str, Any]:
    """Deterministic pre-flight estimate for a would-be run.

    Composes two existing counters instead of duplicating them: stub-node
    counts per feature come from a single ``enrich.build_plan`` walk (nodes
    attributed via each feature's owned files), and the stage list comes from
    ``council_batch.active_stages`` with critique expanded by its roster the
    way ``next_batch`` expands dispatch units. Every number here is labelled
    ``estimate:`` at print sites — none is a wall-clock promise. A missing or
    unreadable ``tree.json`` estimates zero nodes rather than raising (the
    stage/unit math stays usable).
    """
    from dummyindex.context.domains.council_batch import (
        CRITIC_ROSTER,
        CouncilMode,
        active_stages,
    )
    from dummyindex.context.domains.enrich import build_plan

    council_mode = CouncilMode(mode)
    stages = active_stages(council_mode, tree_enrich=True)
    # Units-per-stage mirrors next_batch's expansion: dev/architect/flow/tree
    # stages are one dispatch unit; critique contributes one per critic.
    units_per_stage = {
        int(stage): len(CRITIC_ROSTER[council_mode]) if stage.name == "CRITIQUE" else 1
        for stage in stages
    }

    owned = {fid: _owned_files(context_dir, fid) for fid in features}
    try:
        plan = build_plan(context_dir)
    except (OSError, KeyError, ValueError):
        plan = None
    stub_counts = {fid: 0 for fid in features}
    if plan is not None:
        for node in plan.nodes:
            if not node.path:
                continue
            for fid in features:
                if node.path in owned[fid]:
                    stub_counts[fid] += 1
                    break

    per_feature = tuple(
        {
            "feature_id": fid,
            "estimate_nodes": stub_counts[fid],
            "estimate_stages": len(stages),
            "estimate_units": sum(units_per_stage.values()),
        }
        for fid in features
    )
    total_units = sum(item["estimate_units"] for item in per_feature)
    return {
        "mode": mode,
        "stages": tuple((int(s), _STAGE_NAMES.get(int(s), str(s))) for s in stages),
        "features": per_feature,
        "total_units": total_units,
        "heuristic_seconds": total_units * HEURISTIC_SECONDS_PER_UNIT,
    }


def render_run_md(run: FleetRun) -> str:
    """The human-readable ``RUN.md`` manifest written next to the state."""
    lines = [
        "# Maintain run",
        "",
        f"- dir: `{run.run_dir.name}`",
        f"- anchor: `{run.anchor_sha or '(none)'}`",
        f"- mode: {run.mode}",
        f"- created: {run.created_at}",
        "",
        "| # | feature | stage | name | status |",
        "|---|---------|-------|------|--------|",
    ]
    idx = 1
    for feature in run.features:
        for unit in feature.stages:
            lines.append(
                f"| {idx} | {unit.feature_id} | {unit.stage} "
                f"| {unit.name} | {unit.status.value} |"
            )
            idx += 1
    lines.append("")
    return "\n".join(lines)


# ----- helpers ---------------------------------------------------------------


def _utcnow(now: _dt.datetime | None) -> _dt.datetime:
    return now or _dt.datetime.now(_dt.timezone.utc)


def _isoformat(moment: _dt.datetime) -> str:
    return moment.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")


def _run_ts(moment: _dt.datetime) -> str:
    return moment.astimezone(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


def _now_iso() -> str:
    return _isoformat(_dt.datetime.now(_dt.timezone.utc))


def _feature_index(run: FleetRun, feature_id: str) -> int:
    for idx, feature in enumerate(run.features):
        if feature.feature_id == feature_id:
            return idx
    return len(run.features)


def _owned_files(context_dir: Path, feature_id: str) -> frozenset[str]:
    """The repo-relative files ``features/<id>/feature.json`` claims."""
    path = context_dir / "features" / feature_id / "feature.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(payload, dict):
        return frozenset()
    files = payload.get("files", []) or []
    return frozenset(f for f in files if isinstance(f, str) and f)
