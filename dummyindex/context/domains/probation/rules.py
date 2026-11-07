"""Pure decision rules for the probation lifecycle: routing, followed-check, eligibility."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from ..evolve_gate import EvolveError
from ..observe import scan_text
from .constants import (
    HARM_MIN,
    PROBE_MAX_CHARS,
    PROMOTE_MIN_DAYS,
    PROMOTE_MIN_SESSIONS,
)
from .enums import Followed, Route, State
from .models import Item

PROBATION_PREFIX = "probation:"
HIGH_IMPACT = "high-impact content: use explicit /dummyindex-evolve"
CAP_REASON = "probation cap"

_CONVENTION = re.compile(r"\.context/conventions/([^/]+)\.md")
_FEATURES = ".context/features/"
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_FENCE = re.compile(r"```|~~~")
_COMMAND = re.compile(r"^\s*\$ ", re.MULTILINE)


def item_id_of(item: str, items: Iterable[Item]) -> str | None:
    """Return the evolution item id a COUNT route refers to, else None."""
    if item.startswith(PROBATION_PREFIX):
        return item[len(PROBATION_PREFIX) :]
    path, sep, rid = item.partition("#")
    if sep and any(entry.target == path and entry.id == rid for entry in items):
        return rid
    return None


def route(item: str, items: Iterable[Item]) -> Route:
    """Classify an attributed item by blast radius."""
    known = list(items)
    if item_id_of(item, known) is not None:
        return Route.COUNT
    path = item.partition("#")[0]
    match = _CONVENTION.fullmatch(path)
    if match and match.group(1) != "naming":
        return Route.CONVENTION
    if path.startswith(_FEATURES):
        return Route.RECONCILE
    return Route.EXPLICIT


def followed(
    probe: dict[str, str] | None,
    calls: Sequence[tuple[int, str]] | None,
    start_turn: int,
    end_turn: int | None,
) -> Followed:
    """Check tool-call signatures in the turn window against a probe."""
    if probe is None or calls is None:
        return Followed.UNKNOWN
    window = [
        sig
        for turn, sig in calls
        if turn >= start_turn and (end_turn is None or turn < end_turn)
    ]
    if "require" in probe:
        hit = any(re.search(probe["require"], sig) for sig in window)
        return Followed.YES if hit else Followed.NO
    hit = any(re.search(probe["forbid"], sig) for sig in window)
    return Followed.NO if hit else Followed.YES


def harm_reached(item: Item) -> bool:
    """True when harm spans enough distinct sessions and days, origin excluded."""
    entries = [(s, d) for s, d in item.harm if s != item.origin_session]
    sessions = {s for s, _ in entries}
    days = {d for _, d in entries}
    return len(sessions) >= HARM_MIN and len(days) >= HARM_MIN


def exposed_sessions(item: Item, exposures: Iterable[dict[str, Any]]) -> int:
    """Count distinct non-origin sessions in the item's exposure rows."""
    return len(
        {row["session"] for row in exposures if row["session"] != item.origin_session}
    )


def eligible(
    item: Item,
    exposures: Iterable[dict[str, Any]],
    calls_by_session: dict[str, Sequence[tuple[int, str]] | None],
) -> bool:
    """Whether a PROBATION item may be promoted; exposures are this item's rows only."""
    if item.state is not State.PROBATION:
        return False
    rows = [row for row in exposures if row["session"] != item.origin_session]
    if len({row["session"] for row in rows}) < PROMOTE_MIN_SESSIONS:
        return False
    if len({row["day"] for row in rows}) < PROMOTE_MIN_DAYS:
        return False
    if item.harm or item.contested:
        return False
    if item.probe is None:
        return True
    first_turn: dict[str, int] = {}
    for row in rows:
        session = row["session"]
        first_turn[session] = min(row["turn"], first_turn.get(session, row["turn"]))
    verdicts = [
        followed(item.probe, calls_by_session.get(session), turn, None)
        for session, turn in first_turn.items()
    ]
    return Followed.YES in verdicts and Followed.NO not in verdicts


def upper_bound(n: int) -> float:
    """95% upper bound on the miss rate after n exposed sessions with no observed harm."""
    if n <= 0:
        return 1.0
    return 1 - 0.05 ** (1 / n)


def content_reasons(text: str) -> tuple[str, ...]:
    """Return sorted reasons a rule body is too high-impact for probation."""
    reasons = set(scan_text(text))
    if _URL.search(text):
        reasons.add("url")
    if _FENCE.search(text):
        reasons.add("code-fence")
    if _COMMAND.search(text):
        reasons.add("command")
    return tuple(sorted(reasons))


def compile_probe(raw: Any) -> dict[str, str] | None:
    """Validate a probe spec and return it unchanged; raise EvolveError when malformed."""
    if raw is None:
        return None
    message = 'probe must be {"require"|"forbid": regex<=200 chars}'
    if not isinstance(raw, dict) or len(raw) != 1:
        raise EvolveError(message)
    [(key, pattern)] = raw.items()
    if key not in ("require", "forbid") or not isinstance(pattern, str):
        raise EvolveError(message)
    if len(pattern) > PROBE_MAX_CHARS:
        raise EvolveError(message)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise EvolveError(message) from exc
    return raw
