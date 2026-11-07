from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.probation import store
from dummyindex.context.domains.probation.enums import State
from dummyindex.context.domains.probation.models import Item

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ITEM_KEYS = {
    "schema_version",
    "id",
    "target",
    "body",
    "applies_when",
    "prediction",
    "probe",
    "sources",
    "tests",
    "evidence",
    "origin_session",
    "learning_event",
    "created",
    "state",
    "harm",
    "ignored",
    "contested",
    "needs_enforcement",
    "demote_pending",
    "history",
}


def _item(**overrides) -> Item:
    fields = {
        "id": "rule-a",
        "target": ".context/conventions/testing.md",
        "body": "Use fixtures.\n",
        "applies_when": "writing tests",
        "prediction": "fewer flakes",
        "probe": None,
        "sources": {"a.py": "ab"},
        "tests": ("tests/test_x.py",),
        "evidence": ("ev-1",),
        "origin_session": "key-1",
        "learning_event": "chat:c1",
        "created": "2026-01-01T00:00:00+00:00",
        "state": State.PROBATION,
        "harm": (),
    }
    fields.update(overrides)
    return Item(**fields)


def test_item_round_trip():
    item = _item(
        probe={"require": "pytest"},
        harm=(("key-2", "2026-01-02"),),
        ignored=1,
        history=(
            {"ts": "t", "from": "proposed", "to": "probation", "reason": "gate pass"},
        ),
    )
    data = item.to_dict()
    assert set(data) == ITEM_KEYS
    assert len(ITEM_KEYS) == 20
    assert Item.from_dict(json.loads(json.dumps(data))) == item


def test_history_is_append_only():
    item = _item()
    first = item.with_state(State.SUSPENDED, "source changed", now=NOW)
    second = first.with_state(State.PROBATION, "sources restored", now=NOW)
    assert len(second.history) == 2
    assert second.history[: len(first.history)] == first.history
    assert second.history[1]["from"] == "suspended"
    assert item.history == ()
    assert item.state is State.PROBATION


def test_bad_id_rejected(tmp_path):
    context_dir = tmp_path / ".context"
    for bad in ("../x", "Bad ID"):
        with pytest.raises(EvolveError, match="invalid probation id"):
            store.item_path(context_dir, bad)


def test_unknown_schema_rejected(tmp_path):
    context_dir = tmp_path / ".context"
    directory = tmp_path / store.PROBATION_REL
    directory.mkdir(parents=True)
    data = _item().to_dict()
    data["schema_version"] = 2
    (directory / "rule-a.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EvolveError):
        store.load_items(context_dir)


def test_store_round_trip_and_state_defaults(tmp_path):
    context_dir = tmp_path / ".context"
    assert store.load_items(context_dir) == []
    assert store.load_item(context_dir, "rule-a") is None
    state = store.load_state(context_dir)
    assert state["routed"] == []
    assert state["consumed"] == []
    assert state["last_report"] is None

    item = _item()
    store.save_item(context_dir, item)
    assert store.load_items(context_dir) == [item]
    assert store.load_item(context_dir, "rule-a") == item

    state["consumed"] = ["c1"]
    store.save_state(context_dir, state)
    assert store.load_state(context_dir)["consumed"] == ["c1"]
    assert store.load_items(context_dir) == [item]


def test_locked_raises_when_held_elsewhere(tmp_path, monkeypatch):
    context_dir = tmp_path / ".context"

    @contextmanager
    def held_elsewhere(_context_dir):
        yield False

    monkeypatch.setattr(store, "observe_lock", held_elsewhere)
    with pytest.raises(EvolveError, match="evidence import is running; retry"):
        with store.locked(context_dir):
            pass
