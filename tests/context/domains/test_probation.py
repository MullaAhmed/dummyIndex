from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.probation import rules, store
from dummyindex.context.domains.probation.enums import Followed, Route, State
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


def _exposures(sessions: int, days: int) -> list[dict]:
    return [
        {
            "item": "probation:rule-a",
            "session": f"s{i}",
            "turn": 0,
            "day": f"2026-01-{1 + i % days:02d}",
        }
        for i in range(sessions)
    ]


def test_route_maps_every_l2_row():
    items = [_item(id="r1", target=".context/conventions/testing.md")]
    assert rules.route("probation:x", items) is Route.COUNT
    assert rules.route(".context/conventions/testing.md#r1", items) is Route.COUNT
    assert rules.route(".context/conventions/testing.md", items) is Route.CONVENTION
    assert (
        rules.route(".context/conventions/testing.md#other", items) is Route.CONVENTION
    )
    assert rules.route(".context/conventions/naming.md", items) is Route.EXPLICIT
    assert rules.route(".context/conventions/sub/a.md", items) is Route.EXPLICIT
    assert rules.route(".context/features/x/spec.md", items) is Route.RECONCILE
    for item in (
        "dummyindex/skills/evolve/SKILL.md",
        "skill:foo",
        ".context/playbooks/a.md",
    ):
        assert rules.route(item, items) is Route.EXPLICIT


def test_followed_require_forbid_window():
    calls = [(0, "pytest -q"), (5, "ruff check"), (9, "git push")]
    assert rules.followed({"require": "pytest"}, calls, 0, None) is Followed.YES
    assert rules.followed({"require": "npm"}, calls, 0, None) is Followed.NO
    assert rules.followed({"forbid": "git push"}, calls, 0, None) is Followed.NO
    assert rules.followed({"forbid": "npm"}, calls, 0, None) is Followed.YES
    assert rules.followed({"require": "pytest"}, calls, 1, None) is Followed.NO
    assert rules.followed({"require": "ruff"}, calls, 0, 5) is Followed.NO
    assert rules.followed({"require": "ruff"}, calls, 0, 6) is Followed.YES
    assert rules.followed({"forbid": "git"}, calls, 0, 9) is Followed.YES
    assert rules.followed({"forbid": "git"}, calls, 0, 10) is Followed.NO
    assert rules.followed(None, calls, 0, None) is Followed.UNKNOWN
    assert rules.followed({"require": "x"}, None, 0, None) is Followed.UNKNOWN


def test_harm_needs_distinct_sessions_and_days():
    same_session = _item(harm=(("s1", "2026-01-01"), ("s1", "2026-01-02")))
    same_day = _item(harm=(("s1", "2026-01-01"), ("s2", "2026-01-01")))
    two_by_two = _item(harm=(("s1", "2026-01-01"), ("s2", "2026-01-02")))
    origin_only = _item(
        origin_session="s1",
        harm=(("s1", "2026-01-01"), ("s2", "2026-01-02")),
    )
    assert rules.harm_reached(same_session) is False
    assert rules.harm_reached(same_day) is False
    assert rules.harm_reached(two_by_two) is True
    assert rules.harm_reached(origin_only) is False


def test_eligibility_edges():
    base = _item()
    assert rules.eligible(base, _exposures(10, 3), {}) is True
    assert rules.eligible(base, _exposures(9, 3), {}) is False
    assert rules.eligible(base, _exposures(10, 2), {}) is False
    origin_rows = _exposures(9, 3) + [
        {"item": "probation:rule-a", "session": "key-1", "turn": 0, "day": "2026-01-01"}
    ]
    assert rules.eligible(base, origin_rows, {}) is False
    assert rules.eligible(replace(base, contested=1), _exposures(10, 3), {}) is False
    suspended = replace(base, state=State.SUSPENDED)
    assert rules.eligible(suspended, _exposures(10, 3), {}) is False

    probed = replace(base, probe={"require": "pytest"})
    rows = _exposures(10, 3)
    assert rules.eligible(probed, rows, {}) is False
    one_yes = {"s0": [(0, "pytest -q")]}
    assert rules.eligible(probed, rows, one_yes) is True
    one_no = {"s0": [(0, "ruff check")]}
    assert rules.eligible(probed, rows, one_no) is False


def test_upper_bound_at_ten():
    assert abs(rules.upper_bound(10) - 0.2589) < 1e-3


def test_content_reasons_flags_high_impact():
    assert "url" in rules.content_reasons("see https://example.com/x")
    assert "code-fence" in rules.content_reasons("```python\nx = 1\n```")
    assert "invisible-unicode" in rules.content_reasons("a​b")
    assert "command" in rules.content_reasons("run this:\n$ rm -rf build")
    assert rules.content_reasons("Prefer fixtures over setup helpers.") == ()


def test_compile_probe_rejects_bad_regex():
    bad_probes = (
        {"require": "("},
        {"require": "a" * 201},
        {"require": "a", "forbid": "b"},
        {"maybe": "a"},
        {"require": 5},
        "pytest",
        ["require"],
    )
    for bad in bad_probes:
        with pytest.raises(EvolveError):
            rules.compile_probe(bad)
    assert rules.compile_probe(None) is None
    probe = {"forbid": "git push"}
    assert rules.compile_probe(probe) is probe
