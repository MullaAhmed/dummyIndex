from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dummyindex.context.domains.living_rules import plan_rule, rules_in, sha256
from dummyindex.context.domains.observe import record_exposure
from dummyindex.context.domains.probation import (
    State,
    demote,
    enter,
    format_promote,
    promote,
    store,
)
from dummyindex.context.domains.probation.models import Item
from dummyindex.context.domains.probation.rules import CAP_REASON, HIGH_IMPACT

pytestmark = pytest.mark.unit

NOW = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
TARGET = ".context/conventions/testing.md"
BODY = "Invalidate the cache when the source digest changes."
EVIDENCE = (".context/gc/closeouts/build.json",)
TESTS = ("tests/test_rule.py",)


def ok(argv, cwd):
    return 0, "ok"


def bad(argv, cwd):
    return 1, "failed"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    context = tmp_path / ".context"
    (context / "conventions").mkdir(parents=True)
    (context / "conventions/testing.md").write_bytes(
        b"# Testing\n\nOwner-authored policy.\n"
    )
    (tmp_path / "cache.py").write_text("VALUE = 1\n", encoding="utf-8")
    (context / "gc/closeouts").mkdir(parents=True)
    (context / "gc/closeouts/build.json").write_text(
        '{"outcome":"verified"}\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_rule.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    return context


def _item(context: Path, **overrides) -> Item:
    fields = {
        "id": "r1",
        "target": TARGET,
        "body": BODY,
        "applies_when": "changing the cache",
        "prediction": "no stale reads",
        "probe": None,
        "sources": {"cache.py": sha256((context.parent / "cache.py").read_bytes())},
        "tests": TESTS,
        "evidence": EVIDENCE,
        "origin_session": None,
        "learning_event": "chat:c1",
        "created": NOW.isoformat(timespec="seconds"),
        "state": State.PROBATION,
        "harm": (),
    }
    fields.update(overrides)
    return Item(**fields)


def _expose(context: Path, sessions: int) -> None:
    for i in range(sessions):
        record_exposure(
            context,
            session_id=f"s{i}",
            turn=0,
            items=[("probation:r1", None)],
            now=NOW - timedelta(days=i % 3),
        )


def _events(context: Path) -> list[dict]:
    path = context / "gc/evolution.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stored(context: Path, item_id: str = "r1") -> Item:
    item = store.load_item(context, item_id)
    assert item is not None
    return item


def _run_dir(context: Path, rule_id: str, body: str) -> Path:
    run = context / "cache/evolution/runs" / rule_id
    run.mkdir(parents=True)
    (run / "probation.json").write_text(
        json.dumps({"applies_when": "writing cache code", "probe": None, "body": body}),
        encoding="utf-8",
    )
    return run


def _stage(context: Path, run: Path, rule_id: str) -> dict:
    planned = plan_rule(
        context,
        target=TARGET,
        rule_id=rule_id,
        body=BODY,
        expected_sha256=sha256((context / "conventions/testing.md").read_bytes()),
        sources=("cache.py",),
        evidence=EVIDENCE,
    )
    staged = run / "staged/0" / TARGET
    staged.parent.mkdir(parents=True)
    staged.write_text(planned["content"], encoding="utf-8")
    return planned["candidate"]


def test_promote_edits_only_block_and_records_events(repo):
    target = repo / "conventions/testing.md"
    target.write_bytes(target.read_bytes() + b"Owner adds a line.\n")
    before = target.read_text(encoding="utf-8")
    store.save_item(repo, _item(repo))
    _expose(repo, 10)

    results = promote(repo, now=NOW, runner=ok)

    text = target.read_text(encoding="utf-8")
    assert text.startswith(before)
    assert [rule["id"] for rule in rules_in(text)] == ["r1"]
    assert [event["kind"] for event in _events(repo)][-2:] == ["gate", "promote"]
    [row] = results
    assert row["exposed_sessions"] == 10
    assert abs(row["upper_bound_95"] - 0.2589) < 1e-3
    assert _stored(repo).state is State.PROMOTED
    out = format_promote(results)
    assert "no harm detected in 10 exposed sessions" in out
    assert "25.9%" in out
    assert out.splitlines()[-1] == "review and commit .context/conventions/ yourself"
    assert "improv" not in out
    last = _events(repo)[-1]
    outcome = last["outcome"]
    assert abs(outcome["upper_bound_95"] - 0.2589) < 1e-3
    assert outcome["exposed_sessions"] == 10
    assert outcome["qualification"] == "no harm detected"


def test_promote_failing_gate_keeps_probation(repo):
    target = repo / "conventions/testing.md"
    before = target.read_bytes()
    store.save_item(repo, _item(repo))
    _expose(repo, 10)

    [row] = promote(repo, now=NOW, runner=bad)

    assert row["state"] == "probation"
    assert _stored(repo).state is State.PROBATION
    assert _stored(repo).history[-1]["reason"].startswith("gate fail")
    assert target.read_bytes() == before


def test_promote_content_scan_hit_quarantines(repo):
    target = repo / "conventions/testing.md"
    before = target.read_bytes()
    body = "Invalidate the cache using https://example.com when the digest changes."
    store.save_item(repo, _item(repo, body=body))
    _expose(repo, 10)

    [row] = promote(repo, now=NOW, runner=ok)

    assert row["state"] == "quarantined"
    assert _stored(repo).state is State.QUARANTINED
    assert target.read_bytes() == before
    assert not (repo / "gc/evolution.jsonl").exists()


def test_promote_skips_ineligible_items(repo):
    target = repo / "conventions/testing.md"
    before = target.read_bytes()
    store.save_item(repo, _item(repo))
    _expose(repo, 9)

    results = promote(repo, now=NOW, runner=ok)

    assert all(row["id"] != "r1" for row in results)
    assert _stored(repo).state is State.PROBATION
    assert target.read_bytes() == before


def test_demote_promoted_removes_only_block_and_records_rollback(repo):
    target = repo / "conventions/testing.md"
    target.write_bytes(target.read_bytes() + b"Owner adds a line.\n")
    before = target.read_bytes()
    store.save_item(repo, _item(repo))
    _expose(repo, 10)
    promote(repo, now=NOW, runner=ok)
    assert target.read_bytes() != before

    result = demote(repo, "r1", now=NOW, runner=ok)

    assert target.read_bytes() == before
    assert _events(repo)[-1]["kind"] == "rollback"
    assert _events(repo)[-1]["run"] == "probation-r1"
    assert result["state"] == "demoted"
    assert _stored(repo).state is State.DEMOTED


def test_promote_syncs_first_so_drift_blocks(repo):
    target = repo / "conventions/testing.md"
    before = target.read_bytes()
    store.save_item(repo, _item(repo))
    _expose(repo, 10)
    (repo.parent / "cache.py").write_text("VALUE = 2\n", encoding="utf-8")

    results = promote(repo, now=NOW, runner=ok)

    assert all(row["id"] != "r1" for row in results)
    assert target.read_bytes() == before
    assert _stored(repo).state is State.SUSPENDED


def test_demote_missing_block_records_demoted(repo):
    store.save_item(repo, _item(repo, state=State.PROMOTED))

    result = demote(repo, "r1", now=NOW, runner=ok)

    item = _stored(repo)
    assert item.state is State.DEMOTED
    assert "block already gone" in item.history[-1]["reason"]
    assert result["state"] == "demoted"
    assert not (repo / "gc/evolution.jsonl").exists()


def test_demote_probation_item(repo):
    store.save_item(repo, _item(repo))

    result = demote(repo, "r1", now=NOW, runner=ok)

    assert result["state"] == "demoted"
    assert _stored(repo).state is State.DEMOTED


def test_enter_writes_probation_item_and_caps(repo, tmp_path):
    run = _run_dir(repo, "r1", BODY)
    candidate = _stage(repo, run, "r1")
    event = {"event_id": "chat:c1", "rule_id": "r1", "evidence": list(EVIDENCE)}

    assert enter(
        repo, event=event, run=run, candidate=candidate, tests=TESTS, now=NOW
    ) == {"probation": "r1"}
    item = _stored(repo)
    assert item.state is State.PROBATION
    assert item.sources == {"cache.py": sha256((tmp_path / "cache.py").read_bytes())}

    run2 = _run_dir(repo, "r2", BODY)
    candidate2 = _stage(repo, run2, "r2")
    event2 = {"event_id": "chat:c2", "rule_id": "r2", "evidence": list(EVIDENCE)}
    assert enter(
        repo, event=event2, run=run2, candidate=candidate2, tests=TESTS, now=NOW
    ) == {"verdict": "blocked", "reason": CAP_REASON}

    run3 = _run_dir(repo, "r3", "Use this:\n```\nrm -rf x\n```\n")
    event3 = {"event_id": "chat:c3", "rule_id": "r3", "evidence": list(EVIDENCE)}
    assert enter(
        repo, event=event3, run=run3, candidate=candidate, tests=TESTS, now=NOW
    ) == {"verdict": "blocked", "reason": HIGH_IMPACT}
