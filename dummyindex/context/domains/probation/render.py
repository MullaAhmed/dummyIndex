"""Render the local probation block for a session and the yield report."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..evolve_learning import pending_learning
from ..living_rules import sha256
from ..observe import (
    attributions,
    corrections,
    evolution_enabled,
    exposures,
    open_corrections,
    record_exposure,
    retention_days,
    session_key,
)
from . import store
from .constants import DIGEST_MEMORY, INDEX_MAX_CHARS, ITEM_LINE_MAX
from .enums import LIVE, State
from .models import Item
from .rules import PROBATION_PREFIX
from .sync import eligible_ids, sync

HEADER_LINES = (
    "## Local probation rules (provisional, unverified)",
    "Local to this checkout; not committed. "
    "Exposure is not applicability: apply a rule only when its condition holds.",
)
REMINDER = (
    "  Reminder: this rule was ignored before; follow it when its condition holds."
)
NEXT_DEMOTE = "Next: dummyindex context evolve probation demote --item {id}"
NEXT_ATTRIBUTE = "Next: dummyindex context evolve attribute --next"
NEXT_LEARNING = "Next: dummyindex context evolve learning --next"
NEXT_RECONCILE = "Next: dummyindex context reconcile ({item})"
NEXT_EXPLICIT = "Next: /dummyindex-evolve for {item} (human promote)"
NEXT_PROMOTE = "Next: dummyindex context evolve probation promote --item {id}"
LABEL = "exposure, not applicability"


def session_block(
    context_dir: Path, session_id: str, *, now: datetime | None = None
) -> str:
    """Return the probation block for one session; empty when nothing applies or on error."""
    if not context_dir.is_dir() or not evolution_enabled():
        return ""
    try:
        sync(context_dir, now=now, probes=False)
    except Exception:
        pass
    try:
        return _block(context_dir, session_id, now)
    except Exception:
        return ""


def _block(context_dir: Path, session_id: str, now: datetime | None) -> str:
    state = store.load_state(context_dir)
    before = copy.deepcopy(state)
    items = store.load_items(context_dir)
    key = session_key(session_id) if session_id else None
    next_line = None
    if key is not None and key not in state["digested"]:
        next_line = _next_line(context_dir, state, items)
    tail = [next_line] if next_line else []
    shown, lines = _fit([i for i in items if i.state is State.PROBATION], tail)
    if key is not None and shown:
        record_exposure(
            context_dir,
            session_id=session_id,
            turn=0,
            items=[
                (f"{PROBATION_PREFIX}{item.id}", sha256(item.body.encode()))
                for item in shown
            ],
            now=now,
        )
    if next_line is not None:
        state["digested"] = (state["digested"] + [key])[-DIGEST_MEMORY:]
    block = ""
    if shown or tail:
        block = "\n".join([*HEADER_LINES, *lines, *tail])
    state["last_block_bytes"] = len(block.encode())
    if state != before:
        store.save_state(context_dir, state)
    return block


def _fit(items: list[Item], tail: list[str]) -> tuple[list[Item], list[str]]:
    """Add item lines in order, skipping any that would break the size budget."""
    shown: list[Item] = []
    lines: list[str] = []
    for item in items:
        line = _item_line(item)
        candidate = "\n".join([*HEADER_LINES, *lines, line, *tail])
        if len(candidate) <= INDEX_MAX_CHARS:
            shown.append(item)
            lines.append(line)
    return shown, lines


def _item_line(item: Item) -> str:
    body = next((ln.strip() for ln in item.body.splitlines() if ln.strip()), "")
    line = (
        f"- [{PROBATION_PREFIX}{item.id}] when {item.applies_when}: "
        f"{body[:ITEM_LINE_MAX]}"
    )
    if item.needs_enforcement:
        line += "\n" + REMINDER
    return line


def _next_line(
    context_dir: Path, state: dict[str, Any], items: list[Item]
) -> str | None:
    """Pick the single highest-priority action for this session; may pop a routed entry."""
    pending = next((item for item in items if item.demote_pending), None)
    if pending is not None:
        return NEXT_DEMOTE.format(id=pending.id)
    if any(
        rec.get("candidates") and not rec.get("quarantine")
        for rec in open_corrections(context_dir)
    ):
        return NEXT_ATTRIBUTE
    if pending_learning(context_dir):
        return NEXT_LEARNING
    if state["routed"]:
        entry = state["routed"].pop(0)
        if entry["route"] == "reconcile":
            return NEXT_RECONCILE.format(item=entry["item"])
        return NEXT_EXPLICIT.format(item=entry["item"])
    probation = [item for item in items if item.state is State.PROBATION]
    ready = eligible_ids(context_dir, probation, probes=False)
    if ready:
        return NEXT_PROMOTE.format(id=ready[0])
    return None


def report(context_dir: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Yield counters for the retention window; rates are None when undefined."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now.date() - timedelta(days=retention_days())).isoformat()
    items = store.load_items(context_dir)
    state = store.load_state(context_dir)
    recent_corrections = [r for r in corrections(context_dir) if _day(r) >= cutoff]
    recent_attributions = [r for r in attributions(context_dir) if _day(r) >= cutoff]
    events = _chat_events(context_dir)
    counts = {
        "observed": len(recent_corrections),
        "quarantined": sum(1 for r in recent_corrections if r.get("quarantine"))
        + sum(1 for item in items if item.state is State.QUARANTINED),
        "attributed": sum(
            1 for r in recent_attributions if r.get("verdict") == "attributed"
        ),
        "proposed": len(events),
        "gate_passes": sum(1 for e in events if e.get("verdict") == "pass"),
        "promotions": _transitions(items, State.PROMOTED, cutoff),
        "demotions": _transitions(items, State.DEMOTED, cutoff),
        "expiries": _transitions(items, State.EXPIRED, cutoff),
        "suspensions": _transitions(items, State.SUSPENDED, cutoff),
    }
    previous = state["last_report"]
    nothing_new = previous == counts
    if not nothing_new:
        state["last_report"] = counts
        store.save_state(context_dir, state)
    live = [item for item in items if item.state in LIVE]
    exposure_rate = None
    if live:
        exposed = sum(
            1
            for item in live
            if any(
                _day(r) >= cutoff
                for r in exposures(context_dir, f"{PROBATION_PREFIX}{item.id}")
            )
        )
        exposure_rate = exposed / len(live)
    ignored = sum(item.ignored for item in items)
    judged = (
        ignored
        + sum(len(item.harm) for item in items)
        + sum(item.contested for item in items)
    )
    promoted_bytes = sum(
        len(item.body.encode()) for item in items if item.state is State.PROMOTED
    )
    return {
        "counts": counts,
        "exposure_rate": exposure_rate,
        "ignored_rate": ignored / judged if judged else None,
        "resident_bytes": state["last_block_bytes"] + promoted_bytes,
        "nothing_new": nothing_new,
        "routed": list(state["routed"]),
        "needs_enforcement": [i.id for i in items if i.needs_enforcement],
        "contested": [i.id for i in items if i.contested > 0],
        "eligible": eligible_ids(context_dir, items, probes=True),
        "label": LABEL,
    }


def format_report(data: dict[str, Any]) -> str:
    """Plain-text yield report; a first line of 'ran, found nothing' when unchanged."""
    lines = []
    if data["nothing_new"]:
        lines.append("ran, found nothing")
    lines.append("counts: " + ", ".join(f"{k}={v}" for k, v in data["counts"].items()))
    lines.append(f"exposure rate: {_pct(data['exposure_rate'])}")
    lines.append(f"ignored rate: {_pct(data['ignored_rate'])}")
    lines.append(f"resident bytes: {data['resident_bytes']}")
    routed = ", ".join(f"{e['item']} ({e['route']})" for e in data["routed"])
    lines.append(f"routed: {routed or 'none'}")
    lines.append(f"needs enforcement: {', '.join(data['needs_enforcement']) or 'none'}")
    lines.append(f"contested: {', '.join(data['contested']) or 'none'}")
    lines.append(f"eligible for promote: {', '.join(data['eligible']) or 'none'}")
    lines.append(f"note: {data['label']}")
    return "\n".join(lines)


def _pct(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * 100:.1f}%"


def _day(row: dict[str, Any]) -> str:
    day = row.get("day")
    return day if isinstance(day, str) else ""


def _transitions(items: list[Item], to: State, cutoff: str) -> int:
    return sum(
        1
        for item in items
        for entry in item.history
        if entry.get("to") == to.value and entry.get("ts", "")[:10] >= cutoff
    )


def _chat_events(context_dir: Path) -> list[dict[str, Any]]:
    directory = context_dir / "gc" / "learning"
    if not directory.is_dir():
        return []
    events = []
    for path in sorted(directory.glob("*.json")):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(event, dict) and str(event.get("event_id", "")).startswith(
            "chat:"
        ):
            events.append(event)
    return events
