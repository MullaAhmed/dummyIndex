"""Fold attributed corrections into probation counters, seeds, drift and expiry."""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path

from ..evolve_gate import EvolveError, safe_file
from ..evolve_learning import enqueue_learning
from ..living_rules import sha256
from ..observe import (
    attributions,
    commit_evidence_stub,
    corrections,
    evolution_enabled,
    exposures,
    observe_lock,
    retention_days,
    session_tool_calls,
)
from . import rules, store
from .constants import DIGEST_MEMORY, IGNORED_ROUTE
from .enums import LIVE, Followed, Route, State
from .models import Item
from .rules import PROBATION_PREFIX

CUE = (
    "A human correction was attributed to {target}. "
    "Propose one narrow rule for it, or record NO_ENTRY."
)


@dataclass(frozen=True)
class SyncResult:
    """Outcome of one sync pass; ``skipped`` names why nothing ran."""

    consumed: int = 0
    seeded: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    skipped: str | None = None


def eligible_ids(
    context_dir: Path, items: Iterable[Item], *, probes: bool
) -> list[str]:
    """Ids of PROBATION items that may be promoted now."""
    found = []
    for item in items:
        if item.state is not State.PROBATION:
            continue
        rows = exposures(context_dir, f"{PROBATION_PREFIX}{item.id}")
        calls: dict[str, list[tuple[int, str]] | None] = {}
        if probes and item.probe is not None:
            calls = {
                r["session"]: session_tool_calls(context_dir, r["session"])
                for r in rows
            }
        if rules.eligible(item, rows, calls):
            found.append(item.id)
    return sorted(found)


def sync(
    context_dir: Path, *, now: datetime | None = None, probes: bool = False
) -> SyncResult:
    """Apply unconsumed attributions and lifecycle rules; never gates or writes curated files."""
    if not evolution_enabled():
        return SyncResult(skipped="disabled")
    with observe_lock(context_dir) as held:
        if not held:
            return SyncResult(skipped="locked")
        return _sync_held(context_dir, now or datetime.now(timezone.utc), probes)


def _sync_held(context_dir: Path, now: datetime, probes: bool) -> SyncResult:
    original = {item.id: item for item in store.load_items(context_dir)}
    items = dict(original)
    state = store.load_state(context_dir)
    before = copy.deepcopy(state)
    consumed = set(state["consumed"])
    rows = attributions(context_dir)
    corr = {rec["id"]: rec for rec in corrections(context_dir)}
    exposure_rows = exposures(context_dir)
    seeded: list[str] = []
    taken = 0
    for row in rows:
        cid = row["correction"]
        if cid in consumed:
            continue
        done, event_id = _apply(
            context_dir, row, items, state, corr, exposure_rows, probes, now
        )
        if done:
            consumed.add(cid)
            taken += 1
        if event_id is not None:
            seeded.append(event_id)
    for iid in sorted(items):
        items[iid] = _settle(context_dir, items[iid], exposure_rows, now)
    changed = [iid for iid in sorted(items) if items[iid] != original[iid]]
    for iid in changed:
        store.save_item(context_dir, items[iid])
    state["consumed"] = sorted(consumed & {row["correction"] for row in rows})
    if state != before:
        store.save_state(context_dir, state)
    return SyncResult(
        consumed=taken,
        seeded=tuple(seeded),
        changed=tuple(changed),
        skipped=None,
    )


def _apply(
    context_dir: Path,
    row: dict,
    items: dict[str, Item],
    state: dict,
    corr: dict[str, dict],
    exposure_rows: list[dict],
    probes: bool,
    now: datetime,
) -> tuple[bool, str | None]:
    """Route one attribution; return (consumed, seeded event id)."""
    if row["verdict"] != "attributed":
        return True, None
    item_str = row["item"]
    kind = rules.route(item_str, list(items.values()))
    if kind is Route.COUNT:
        return _count(context_dir, row, items, corr, exposure_rows, probes, now), None
    if not row["durable"]:
        return True, None
    target = item_str.partition("#")[0]
    if _live_in_session(items, exposure_rows, target, row["session"]):
        return True, None
    if kind is Route.CONVENTION:
        return _seed(context_dir, row, target)
    _digest_routed(state, row["correction"], target, kind)
    return True, None


def _count(
    context_dir: Path,
    row: dict,
    items: dict[str, Item],
    corr: dict[str, dict],
    exposure_rows: list[dict],
    probes: bool,
    now: datetime,
) -> bool:
    """Update one evolution item's counters; False leaves the row for a later probes sync."""
    iid = rules.item_id_of(row["item"], list(items.values()))
    item = items.get(iid) if iid is not None else None
    if item is None:
        return True
    if row["retracts"]:
        items[iid] = _retract(item, now)
        return True
    if item.probe is not None and not probes:
        return False
    calls = session_tool_calls(context_dir, row["session"]) if item.probe else None
    start = _window_start(exposure_rows, row["item"], row["session"])
    verdict = rules.followed(item.probe, calls, start, row["turn"])
    items[iid] = _tally(item, verdict, row, corr)
    return True


def _retract(item: Item, now: datetime) -> Item:
    if item.state in LIVE:
        return item.with_state(State.DEMOTED, "retracted", now)
    if item.state is State.PROMOTED and not item.demote_pending:
        return replace(item, demote_pending=True)
    return item


def _tally(item: Item, verdict: Followed, row: dict, corr: dict[str, dict]) -> Item:
    if verdict is Followed.YES:
        rec = corr.get(row["correction"])
        day = rec["day"] if rec is not None else row["day"]
        return replace(item, harm=item.harm + ((row["session"], day),))
    if verdict is Followed.NO:
        ignored = item.ignored + 1
        return replace(
            item,
            ignored=ignored,
            needs_enforcement=item.needs_enforcement or ignored >= IGNORED_ROUTE,
        )
    return replace(item, contested=item.contested + 1)


def _window_start(exposure_rows: list[dict], item_str: str, session: str) -> int:
    """First turn the attributed item was exposed in this session, else 0."""
    key = (
        item_str
        if item_str.startswith(PROBATION_PREFIX)
        else item_str.partition("#")[0]
    )
    turns = [
        row["turn"]
        for row in exposure_rows
        if row.get("session") == session and row.get("item") == key
    ]
    return min(turns, default=0)


def _live_in_session(
    items: dict[str, Item], exposure_rows: list[dict], target: str, session: str
) -> bool:
    """True when this session loaded a live probation item for the same target."""
    for row in exposure_rows:
        item_str = row.get("item")
        if row.get("session") != session or not isinstance(item_str, str):
            continue
        if not item_str.startswith(PROBATION_PREFIX):
            continue
        held = items.get(item_str[len(PROBATION_PREFIX) :])
        if held is not None and held.target == target and held.state in LIVE:
            return True
    return False


def _seed(context_dir: Path, row: dict, target: str) -> tuple[bool, str | None]:
    cid = row["correction"]
    event_id = f"chat:{cid}"
    try:
        stub = commit_evidence_stub(context_dir, cid)
        enqueue_learning(
            context_dir,
            event_id=event_id,
            origin="human",
            evidence=[stub],
            target=target,
            cue=CUE.format(target=target),
        )
    except EvolveError:
        return False, None
    return True, event_id


def _digest_routed(state: dict, cid: str, target: str, kind: Route) -> None:
    entries = [entry for entry in state["routed"] if entry.get("correction") != cid]
    entries.append({"correction": cid, "item": target, "route": kind.value})
    state["routed"] = entries[-DIGEST_MEMORY:]


def _settle(
    context_dir: Path, item: Item, exposure_rows: list[dict], now: datetime
) -> Item:
    """Apply harm, drift and expiry to one item."""
    if rules.harm_reached(item):
        item = _harmed(item, now)
    if item.state in LIVE:
        item = _drift(context_dir, item, now)
    if item.state in LIVE:
        item = _expire(item, exposure_rows, now)
    return item


def _harmed(item: Item, now: datetime) -> Item:
    if item.state in LIVE:
        return item.with_state(State.DEMOTED, "harm", now)
    if item.state is State.PROMOTED and not item.demote_pending:
        return replace(item, demote_pending=True)
    return item


def _file_sha(root: Path, rel: str) -> str | None:
    # A tampered item may point outside the repo; treat that as a missing source.
    try:
        return sha256(safe_file(root, rel).read_bytes())
    except (EvolveError, OSError):
        return None


def _drift(context_dir: Path, item: Item, now: datetime) -> Item:
    root = context_dir.parent
    mismatch = any(_file_sha(root, rel) != want for rel, want in item.sources.items())
    if item.state is State.PROBATION and mismatch:
        return item.with_state(State.SUSPENDED, "source changed", now)
    if item.state is State.SUSPENDED and not mismatch:
        return item.with_state(State.PROBATION, "sources restored", now)
    return item


def _expire(item: Item, exposure_rows: list[dict], now: datetime) -> Item:
    key = f"{PROBATION_PREFIX}{item.id}"
    days = [
        row["day"]
        for row in exposure_rows
        if row.get("item") == key and isinstance(row.get("day"), str)
    ]
    last = max([item.created[:10], *days])
    if (now.date() - date.fromisoformat(last)).days >= retention_days():
        return item.with_state(State.EXPIRED, "no exposure in retention window", now)
    return item
