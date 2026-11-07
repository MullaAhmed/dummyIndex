"""Frozen probation item record and its JSON form."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from ..evolve_gate import EvolveError
from .enums import State

SCHEMA_VERSION = 1


def _field(data: dict, key: str, kind: type | tuple[type, ...]) -> Any:
    value = data.get(key)
    if key not in data or not isinstance(value, kind):
        raise EvolveError(f"probation item field {key} is missing or malformed")
    return value


@dataclass(frozen=True)
class Item:
    """One chat-derived rule on probation, with its counters and history."""

    id: str
    target: str
    body: str
    applies_when: str
    prediction: str
    probe: dict[str, str] | None
    sources: dict[str, str]
    tests: tuple[str, ...]
    evidence: tuple[str, ...]
    origin_session: str | None
    learning_event: str
    created: str
    state: State
    harm: tuple[tuple[str, str], ...]
    ignored: int = 0
    contested: int = 0
    needs_enforcement: bool = False
    demote_pending: bool = False
    history: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "target": self.target,
            "body": self.body,
            "applies_when": self.applies_when,
            "prediction": self.prediction,
            "probe": dict(self.probe) if self.probe is not None else None,
            "sources": dict(self.sources),
            "tests": list(self.tests),
            "evidence": list(self.evidence),
            "origin_session": self.origin_session,
            "learning_event": self.learning_event,
            "created": self.created,
            "state": self.state.value,
            "harm": [list(entry) for entry in self.harm],
            "ignored": self.ignored,
            "contested": self.contested,
            "needs_enforcement": self.needs_enforcement,
            "demote_pending": self.demote_pending,
            "history": [dict(entry) for entry in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Item:
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            raise EvolveError("unsupported probation item schema")
        origin = data.get("origin_session")
        if origin is not None and not isinstance(origin, str):
            raise EvolveError("probation item field origin_session is malformed")
        probe = data.get("probe")
        if probe is not None and not isinstance(probe, dict):
            raise EvolveError("probation item field probe is malformed")
        try:
            return cls(
                id=_field(data, "id", str),
                target=_field(data, "target", str),
                body=_field(data, "body", str),
                applies_when=_field(data, "applies_when", str),
                prediction=_field(data, "prediction", str),
                probe=probe,
                sources=dict(_field(data, "sources", dict)),
                tests=tuple(_field(data, "tests", list)),
                evidence=tuple(_field(data, "evidence", list)),
                origin_session=origin,
                learning_event=_field(data, "learning_event", str),
                created=_field(data, "created", str),
                state=State(_field(data, "state", str)),
                harm=tuple(
                    (entry[0], entry[1]) for entry in _field(data, "harm", list)
                ),
                ignored=_field(data, "ignored", int),
                contested=_field(data, "contested", int),
                needs_enforcement=_field(data, "needs_enforcement", bool),
                demote_pending=_field(data, "demote_pending", bool),
                history=tuple(dict(entry) for entry in _field(data, "history", list)),
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise EvolveError("probation item is malformed") from exc

    def with_state(self, to: State, reason: str, now: datetime | None = None) -> Item:
        stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        entry = {
            "ts": stamp,
            "from": self.state.value,
            "to": to.value,
            "reason": reason,
        }
        return replace(self, state=to, history=self.history + (entry,))

    def note(self, reason: str, now: datetime | None = None) -> Item:
        return self.with_state(self.state, reason, now)
