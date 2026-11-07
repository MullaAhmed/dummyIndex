from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from dummyindex.context.domains import evidence
from dummyindex.context.domains.evidence import scan_hosts
from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.evolve_learning import (
    enqueue_learning,
    finish_learning,
    prepare_learning,
)
from dummyindex.context.domains.living_rules import sha256
from dummyindex.context.domains.observe import (
    corrections,
    exposures,
    record_attribution,
    record_exposure,
    session_key,
)
from dummyindex.context.domains.probation import render, rules, store
from dummyindex.context.domains.probation.enums import Followed, Route, State
from dummyindex.context.domains.probation.models import Item
from dummyindex.context.domains.probation.sync import eligible_ids, sync

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


SLUG = "proj"
SYNC_NOW = datetime.now(timezone.utc).replace(
    hour=12, minute=0, second=0, microsecond=0
)
CORRECTION = "wrong, do it the other way"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "encode_project_slug", lambda root: SLUG)
    monkeypatch.setattr(evidence, "project_dir_name", lambda root: SLUG)
    root = tmp_path / "repo"
    context = root / ".context"
    (context / "conventions").mkdir(parents=True)
    (context / "conventions/testing.md").write_text("# Testing\n", encoding="utf-8")
    (root / "cache.py").write_bytes(b"VALUE = 1\n")
    return SimpleNamespace(root=root, context=context, projects=tmp_path / "claude")


def _human(env, sid: str, n: int, text: str, ts: str) -> dict:
    return {
        "type": "user",
        "userType": "external",
        "cwd": str(env.root),
        "uuid": f"{sid}-h{n}",
        "timestamp": ts,
        "message": {"role": "user", "content": text},
    }


def _tool(sid: str, n: int, ts: str, name: str, payload: dict) -> dict:
    return {
        "type": "assistant",
        "uuid": f"{sid}-a{n}",
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "model": "m",
            "content": [
                {
                    "type": "tool_use",
                    "id": f"{sid}-t{n}",
                    "name": name,
                    "input": payload,
                }
            ],
        },
    }


def _session(
    env,
    sid: str,
    *,
    days_ago: int = 0,
    calls: tuple[str, ...] = ("ls",),
    reads: tuple[str, ...] = (),
    inject: tuple[str, ...] = ("probation:r1",),
    texts: tuple[str, ...] = (CORRECTION,),
) -> list[str]:
    """Write one Claude transcript (and its injections); return its correction ids."""
    when = SYNC_NOW - timedelta(days=days_ago)
    ts = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    if inject:
        record_exposure(
            env.context,
            session_id=sid,
            turn=0,
            items=[(item, None) for item in inject],
            now=when,
        )
    rows = [_human(env, sid, 0, "start", ts)]
    n = 1
    for command in calls:
        rows.append(_tool(sid, n, ts, "Bash", {"command": command}))
        n += 1
    for rel in reads:
        rows.append(_tool(sid, n, ts, "Read", {"file_path": str(env.root / rel)}))
        n += 1
    for text in texts:
        rows.append(_human(env, sid, n, text, ts))
        n += 1
    path = env.projects / SLUG / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    scan_hosts(env.context, claude_projects=env.projects, now=when)
    mine = [c for c in corrections(env.context) if c["session"] == session_key(sid)]
    return [c["id"] for c in mine]


def _seed_item(env, **overrides) -> Item:
    fields = {
        "id": "r1",
        "target": ".context/conventions/testing.md",
        "origin_session": None,
        "created": SYNC_NOW.isoformat(),
        "sources": {},
        "state": State.PROBATION,
    }
    fields.update(overrides)
    item = _item(**fields)
    store.save_item(env.context, item)
    return item


def _attribute(env, cids, **kwargs) -> None:
    for cid in cids:
        record_attribution(env.context, cid, now=SYNC_NOW, **kwargs)


def _tree(context: Path) -> dict[str, str]:
    out = {}
    for path in context.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(context).as_posix()
        if rel.startswith(("cache/evolution/", "gc/learning/", "gc/evidence/")):
            continue
        if rel.startswith("cache/") and rel.endswith(".lock"):
            continue
        out[rel] = sha256(path.read_bytes())
    return out


def test_retraction_demotes_in_same_sync(env):
    _seed_item(env)
    cids = _session(env, "s1")
    _attribute(env, cids, verdict="attributed", item="probation:r1", retracts=True)
    sync(env.context, now=SYNC_NOW, probes=False)
    assert store.load_item(env.context, "r1").state is State.DEMOTED


def test_harm_needs_distinct_sessions_and_distinct_days(env):
    _seed_item(env, probe={"forbid": "rm "})
    attributed = dict(verdict="attributed", item="probation:r1")
    _attribute(
        env, _session(env, "s1", texts=(CORRECTION, "wrong again")), **attributed
    )
    sync(env.context, now=SYNC_NOW, probes=True)
    assert store.load_item(env.context, "r1").state is State.PROBATION

    _attribute(env, _session(env, "s2"), **attributed)
    sync(env.context, now=SYNC_NOW, probes=True)
    assert store.load_item(env.context, "r1").state is State.PROBATION

    _attribute(env, _session(env, "s3", days_ago=1), **attributed)
    sync(env.context, now=SYNC_NOW, probes=True)
    assert store.load_item(env.context, "r1").state is State.DEMOTED


def test_forbid_match_counts_ignored_then_needs_enforcement(env):
    _seed_item(env, probe={"forbid": "rm "})
    attributed = dict(verdict="attributed", item="probation:r1")
    _attribute(env, _session(env, "s1", calls=("rm -rf build",)), **attributed)
    sync(env.context, now=SYNC_NOW, probes=True)
    item = store.load_item(env.context, "r1")
    assert item.ignored == 1 and item.needs_enforcement is False

    _attribute(env, _session(env, "s2", calls=("rm -rf build",)), **attributed)
    sync(env.context, now=SYNC_NOW, probes=True)
    item = store.load_item(env.context, "r1")
    assert item.ignored == 2 and item.needs_enforcement is True
    assert item.state is State.PROBATION


def test_null_probe_counts_contested(env):
    _seed_item(env)
    _attribute(env, _session(env, "s1"), verdict="attributed", item="probation:r1")
    sync(env.context, now=SYNC_NOW, probes=True)
    item = store.load_item(env.context, "r1")
    assert item.contested == 1
    rows = exposures(env.context, "probation:r1")
    assert rules.eligible(item, rows, {}) is False


def test_probes_false_leaves_probe_attributions_unconsumed(env):
    _seed_item(env, probe={"forbid": "rm "})
    [cid] = _session(env, "s1")
    _attribute(env, [cid], verdict="attributed", item="probation:r1")
    before = store.load_item(env.context, "r1")
    sync(env.context, now=SYNC_NOW, probes=False)
    after = store.load_item(env.context, "r1")
    assert (after.harm, after.ignored, after.contested) == (
        before.harm,
        before.ignored,
        before.contested,
    )
    assert cid not in store.load_state(env.context)["consumed"]
    sync(env.context, now=SYNC_NOW, probes=True)
    assert cid in store.load_state(env.context)["consumed"]


def test_drift_suspends_then_restores(env):
    original = (env.root / "cache.py").read_bytes()
    _seed_item(env, sources={"cache.py": sha256(original)})
    sync(env.context, now=SYNC_NOW)
    assert store.load_item(env.context, "r1").state is State.PROBATION

    (env.root / "cache.py").write_bytes(b"VALUE = 2\n")
    sync(env.context, now=SYNC_NOW)
    assert store.load_item(env.context, "r1").state is State.SUSPENDED

    (env.root / "cache.py").write_bytes(original)
    sync(env.context, now=SYNC_NOW)
    assert store.load_item(env.context, "r1").state is State.PROBATION


def test_injected_now_expires_unexposed_item(env):
    stale_created = (SYNC_NOW - timedelta(days=31)).isoformat()
    _seed_item(env, id="old", created=stale_created)
    _seed_item(env, id="new")
    sync(env.context, now=SYNC_NOW)
    old = store.load_item(env.context, "old")
    assert old.state is State.EXPIRED
    assert store.item_path(env.context, "old").is_file()
    assert old.history[-1]["to"] == "expired"
    assert store.load_item(env.context, "new").state is State.PROBATION


def test_convention_route_seeds_chat_event(env):
    [cid] = _session(env, "s1", inject=(), reads=(".context/conventions/testing.md",))
    _attribute(
        env,
        [cid],
        verdict="attributed",
        item=".context/conventions/testing.md",
        durable=True,
    )
    result = sync(env.context, now=SYNC_NOW)
    assert result.seeded == (f"chat:{cid}",)
    events = list((env.context / "gc/learning").glob("*.json"))
    assert len(events) == 1
    text = events[0].read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["event_id"] == f"chat:{cid}"
    assert event["origin"] == "human"
    assert set(event["evidence"]) == {f".context/gc/evidence/{cid}.json"}
    assert CORRECTION not in text


def test_feature_doc_nondurable_unknown_enqueue_nothing(env):
    feature = env.context / "features/x/spec.md"
    feature.parent.mkdir(parents=True)
    feature.write_text("# x\n", encoding="utf-8")
    feature_cid, convention_cid, unknown_cid = _session(
        env,
        "s1",
        inject=(),
        reads=(".context/features/x/spec.md", ".context/conventions/testing.md"),
        texts=(CORRECTION, "wrong, again", "wrong, once more"),
    )
    _attribute(
        env,
        [feature_cid],
        verdict="attributed",
        item=".context/features/x/spec.md",
        durable=True,
    )
    _attribute(
        env,
        [convention_cid],
        verdict="attributed",
        item=".context/conventions/testing.md",
        durable=False,
    )
    _attribute(env, [unknown_cid], verdict="unknown")
    sync(env.context, now=SYNC_NOW)
    learning = env.context / "gc/learning"
    assert not learning.exists() or not any(learning.iterdir())
    routed = store.load_state(env.context)["routed"]
    assert [entry["correction"] for entry in routed] == [feature_cid]
    assert routed[0]["item"] == ".context/features/x/spec.md"


def test_live_probation_item_blocks_seed_for_target(env):
    _seed_item(env)
    [cid] = _session(env, "s1", reads=(".context/conventions/testing.md",))
    _attribute(
        env,
        [cid],
        verdict="attributed",
        item=".context/conventions/testing.md",
        durable=True,
    )
    result = sync(env.context, now=SYNC_NOW)
    assert result.seeded == ()
    assert not (env.context / "gc/learning").exists()


def test_sync_write_scope_by_tree_hash(env):
    [cid] = _session(env, "s1", inject=(), reads=(".context/conventions/testing.md",))
    _attribute(
        env,
        [cid],
        verdict="attributed",
        item=".context/conventions/testing.md",
        durable=True,
    )
    before = _tree(env.context)
    result = sync(env.context, now=SYNC_NOW)
    assert result.seeded == (f"chat:{cid}",)
    assert _tree(env.context) == before


def test_probation_source_has_no_ledger_string():
    package = Path(store.__file__).parent
    for path in sorted(package.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "ledger.json" not in text, path.name
        assert "improv" not in text, path.name


def test_retraction_demotes_suspended_item(env):
    _seed_item(env, state=State.SUSPENDED)
    cids = _session(env, "s1")
    _attribute(env, cids, verdict="attributed", item="probation:r1", retracts=True)
    sync(env.context, now=SYNC_NOW, probes=False)
    assert store.load_item(env.context, "r1").state is State.DEMOTED


def test_drift_suspended_item_hidden_from_block(env):
    _seed_item(env, id="r1")
    _seed_item(env, id="r2", sources={"cache.py": "0" * 64})
    block = render.session_block(env.context, "sx", now=SYNC_NOW)
    assert store.load_item(env.context, "r2").state is State.SUSPENDED
    assert "[probation:r1]" in block
    assert "[probation:r2]" not in block


def test_block_within_budget_and_skipped_item_not_exposed(env):
    for i in range(20):
        _seed_item(
            env,
            id=f"r{i:02d}",
            applies_when="a" * 150,
            body=f"{i:02d} " + "b" * 150 + "\n",
        )
    block = render.session_block(env.context, "sx", now=SYNC_NOW)
    assert len(block.encode()) <= 1600
    shown = set(re.findall(r"\[probation:([^\]]+)\]", block))
    exposed = {
        row["item"][len("probation:") :]
        for row in exposures(env.context)
        if row["item"].startswith("probation:")
    }
    assert exposed == shown
    assert 0 < len(shown) < 20


def test_next_line_once_per_session_by_priority(env):
    _seed_item(env, id="p1", state=State.PROMOTED, demote_pending=True)
    _session(env, "s1", inject=("probation:p1",))
    first = render.session_block(env.context, "a", now=SYNC_NOW)
    assert "Next: dummyindex context evolve probation demote" in first
    again = render.session_block(env.context, "a", now=SYNC_NOW)
    assert "Next:" not in again
    item = store.load_item(env.context, "p1")
    store.save_item(env.context, replace(item, demote_pending=False))
    other = render.session_block(env.context, "b", now=SYNC_NOW)
    assert "Next: dummyindex context evolve attribute --next" in other


def test_empty_session_id_logs_nothing(env):
    _seed_item(env)
    block = render.session_block(env.context, "", now=SYNC_NOW)
    assert "[probation:r1]" in block
    assert "Next:" not in block
    assert exposures(env.context) == []
    assert store.load_state(env.context)["digested"] == []


def test_report_nothing_new_null_rates_resident_bytes(env):
    first = render.report(env.context, now=SYNC_NOW)
    assert first["exposure_rate"] is None
    assert first["ignored_rate"] is None
    second = render.report(env.context, now=SYNC_NOW)
    assert second["nothing_new"] is True
    assert render.format_report(second).splitlines()[0] == "ran, found nothing"

    store.save_item(env.context, _item(id="p1", state=State.PROMOTED, body="abc"))
    state = store.load_state(env.context)
    state["last_block_bytes"] = 100
    store.save_state(env.context, state)
    data = render.report(env.context, now=SYNC_NOW)
    assert data["resident_bytes"] == 103
    assert "improv" not in render.format_report(data)


def test_eligible_ids_respects_probes(env):
    _seed_item(env, id="r1")
    for i in range(10):
        record_exposure(
            env.context,
            session_id=f"s{i}",
            turn=0,
            items=[("probation:r1", None)],
            now=SYNC_NOW - timedelta(days=i % 3),
        )
    items = store.load_items(env.context)
    assert eligible_ids(env.context, items, probes=False) == ["r1"]

    store.save_item(env.context, replace(items[0], probe={"require": "pytest"}))
    items = store.load_items(env.context)
    assert eligible_ids(env.context, items, probes=False) == []


def test_end_to_end_chat_probation_commits_no_correction_text(env):
    [cid] = _session(
        env,
        "s1",
        inject=(),
        reads=(".context/conventions/testing.md",),
        texts=("wrong, never pass the flaky zebra flag",),
    )
    _attribute(
        env,
        [cid],
        verdict="attributed",
        item=".context/conventions/testing.md",
        durable=True,
    )
    result = sync(env.context, now=SYNC_NOW)
    assert result.seeded == (f"chat:{cid}",)

    (env.root / "tests").mkdir()
    (env.root / "tests/test_rule.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    body = "Do not pass the zebra flag to the cache builder."
    reflection = {
        "verified": True,
        "target": ".context/conventions/testing.md",
        "rule_id": "zebra-flag",
        "body": body,
        "sources": ["cache.py"],
        "expected_sha256": sha256(
            (env.context / "conventions/testing.md").read_bytes()
        ),
    }
    event = finish_learning(
        env.context,
        f"chat:{cid}",
        reflection,
        tests=("tests/test_rule.py",),
        runner=lambda argv, cwd: (0, "ok"),
    )
    assert event["verdict"] == "pass"
    assert store.load_item(env.context, "zebra-flag").state is State.PROBATION

    for path in env.root.rglob("*"):
        if not path.is_file():
            continue
        if path.relative_to(env.root).as_posix().startswith(".context/cache/"):
            continue
        text = path.read_bytes().decode("utf-8", errors="ignore")
        assert "flaky zebra flag" not in text, path
        assert body not in text, path


def test_next_line_lower_priority_tiers(env):
    # Tier 3: a pending closeout learning event yields the learning Next line.
    evidence = env.context / "gc/closeouts/x.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"outcome":"verified"}\n', encoding="utf-8")
    enqueue_learning(
        env.context,
        event_id="closeout:x",
        origin="closeout",
        evidence=[".context/gc/closeouts/x.json"],
        cue="c",
    )
    assert "evolve learning --next" in render.session_block(
        env.context, "t3", now=SYNC_NOW
    )
    prepare_learning(env.context, "closeout:x", None)

    # Tier 4: a routed reconcile entry yields the reconcile Next line once.
    state = store.load_state(env.context)
    state["routed"] = [
        {
            "correction": "c9",
            "item": ".context/features/x/spec.md",
            "route": "reconcile",
        }
    ]
    store.save_state(env.context, state)
    block = render.session_block(env.context, "t4", now=SYNC_NOW)
    assert "dummyindex context reconcile" in block
    assert store.load_state(env.context)["routed"] == []

    # Tier 5: a probation item with 10 sessions over 3 days is promotable.
    _seed_item(env, id="r5")
    for i in range(10):
        record_exposure(
            env.context,
            session_id=f"e{i}",
            turn=0,
            items=[("probation:r5", None)],
            now=SYNC_NOW - timedelta(days=i % 3),
        )
    block = render.session_block(env.context, "t5", now=SYNC_NOW)
    assert "evolve probation promote --item r5" in block
