import json
from pathlib import Path

import pytest

from dummyindex.context.domains.evolve_gate import EvolveError, run_gate
from dummyindex.context.domains.evolve_learning import (
    enqueue_learning,
    finish_learning,
    pending_learning,
    prepare_learning,
)
from dummyindex.context.domains.living_rules import (
    plan_rule,
    rule_status,
    rules_in,
    sha256,
)


@pytest.fixture
def lesson(tmp_path: Path) -> tuple[Path, dict]:
    context = tmp_path / ".context"
    (context / "conventions").mkdir(parents=True)
    target = context / "conventions/testing.md"
    target.write_text("# Testing\n\nOwner-authored policy.\n", encoding="utf-8")
    (tmp_path / "cache.py").write_text("VALUE = 1\n", encoding="utf-8")
    evidence = context / "gc/closeouts/build.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"outcome":"verified"}\n', encoding="utf-8")
    reflection = {
        "verified": True,
        "target": ".context/conventions/testing.md",
        "rule_id": "cache-contract",
        "body": "Invalidate the cache when the source digest changes.",
        "sources": ["cache.py"],
        "expected_sha256": sha256(target.read_bytes()),
    }
    return context, reflection


def test_managed_rule_replaces_and_supersedes_without_touching_owner_notes(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    target = context / "conventions/testing.md"
    planned = plan_rule(
        context,
        **{k: v for k, v in reflection.items() if k != "verified"},
        evidence=(".context/gc/closeouts/build.json",),
    )
    target.write_text(planned["content"], encoding="utf-8")
    assert rule_status(context)[0]["state"] == "current"
    (context.parent / "cache.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert rule_status(context)[0]["state"] == "stale"
    revised = plan_rule(
        context,
        target=reflection["target"],
        rule_id="cache-v2",
        body="Use the new cache contract.",
        expected_sha256=sha256(target.read_bytes()),
        sources=("cache.py",),
        evidence=(".context/gc/closeouts/build.json",),
        supersedes=("cache-contract",),
    )
    assert "Owner-authored policy." in revised["content"]
    assert "Invalidate the cache" not in revised["content"]
    assert [r["id"] for r in rules_in(revised["content"])] == ["cache-v2"]
    with pytest.raises(EvolveError, match="changed since review"):
        plan_rule(
            context,
            **{k: v for k, v in reflection.items() if k != "verified"},
            evidence=(".context/gc/closeouts/build.json",),
        )


def test_closeout_prepares_exactly_one_candidate_and_runs_existing_gate(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    queued = enqueue_learning(
        context,
        event_id="build:one",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
        cue="Cache contract changed",
    )
    assert (
        enqueue_learning(
            context,
            event_id="build:one",
            origin="closeout",
            evidence=[".context/gc/closeouts/build.json"],
            cue="Cache contract changed",
        )
        == queued
    )
    prepared = prepare_learning(context, "build:one", reflection)
    assert prepare_learning(context, "build:one", reflection) == prepared
    assert pending_learning(context) == []
    run = context / "gc/evolve" / prepared["run"]
    candidate = json.loads((run / "candidates.jsonl").read_text())
    assert len((run / "candidates.jsonl").read_text().splitlines()) == 1
    tests = context.parent / "tests"
    tests.mkdir()
    (tests / "test_rule.py").write_text(
        "from pathlib import Path\ndef test_rule():\n    assert 'Invalidate the cache' in Path('.context/conventions/testing.md').read_text()\n",
        encoding="utf-8",
    )
    result = run_gate(
        (reflection["target"],),
        run,
        context,
        context.parent,
        candidate_payload=candidate,
        test_paths=("tests/test_rule.py",),
    )
    assert result.verdict == "pass"
    assert [stage.status for stage in result.stages] == ["fail", "pass"]
    assert "Invalidate" not in (context / "conventions/testing.md").read_text()


def test_empty_recursive_unsupported_and_changed_evidence_are_bounded(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    assert (
        enqueue_learning(context, event_id="x", origin="evolve", evidence=[])["state"]
        == "ignored"
    )
    assert (
        enqueue_learning(context, event_id="x", origin="closeout", evidence=[])["state"]
        == "ignored"
    )
    enqueue_learning(
        context,
        event_id="x",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    with pytest.raises(EvolveError, match="verified"):
        prepare_learning(context, "x", {**reflection, "verified": False})
    assert prepare_learning(context, "x", None)["state"] == "no_entry"
    enqueue_learning(
        context,
        event_id="y",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    (context / "gc/closeouts/build.json").write_text("changed", encoding="utf-8")
    with pytest.raises(EvolveError, match="evidence changed"):
        prepare_learning(context, "y", reflection)


def test_accepted_closeout_automatically_updates_authoritative_rule_once(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    tests = context.parent / "tests"
    tests.mkdir()
    (tests / "test_contract.py").write_text(
        "from pathlib import Path\ndef test_contract():\n    assert 'Invalidate the cache' in Path('.context/conventions/testing.md').read_text()\n",
        encoding="utf-8",
    )
    enqueue_learning(
        context,
        event_id="accepted",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    result = finish_learning(
        context, "accepted", reflection, tests=("tests/test_contract.py",)
    )
    assert result["state"] == "applied"
    assert "Invalidate the cache" in (context / "conventions/testing.md").read_text()
    assert finish_learning(context, "accepted", reflection) == result
    assert len(rules_in((context / "conventions/testing.md").read_text())) == 1


def test_missing_verification_stays_evaluated_blocked(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    enqueue_learning(
        context,
        event_id="accepted",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    result = finish_learning(context, "accepted", reflection)
    assert result["state"] == "evaluated"
    assert result["verdict"] == "blocked"
    assert (
        "Invalidate the cache" not in (context / "conventions/testing.md").read_text()
    )


@pytest.mark.parametrize(
    "citation", [".context//audits/work/proof.json", ".context//cache/proof.json"]
)
def test_rule_rejects_canonical_aliases_of_disposable_evidence(
    lesson: tuple[Path, dict], citation: str
) -> None:
    context, reflection = lesson
    proof = context.parent / citation
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text("accepted", encoding="utf-8")
    with pytest.raises(EvolveError, match="durable evidence"):
        plan_rule(
            context,
            **{k: v for k, v in reflection.items() if k != "verified"},
            evidence=(citation,),
        )


@pytest.mark.parametrize(
    "citation", [".context//audits/work/proof.json", ".context//cache/proof.json"]
)
def test_learning_rejects_canonical_aliases_of_disposable_evidence(
    lesson: tuple[Path, dict], citation: str
) -> None:
    context, _ = lesson
    proof = context.parent / citation
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text("accepted", encoding="utf-8")
    with pytest.raises(EvolveError, match="durable evidence"):
        enqueue_learning(
            context, event_id="ephemeral", origin="closeout", evidence=[citation]
        )
    assert pending_learning(context) == []


def test_durable_paths_and_hashes_are_canonical_in_rule_and_queue(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    canonical = ".context/gc/closeouts/build.json"
    expected = sha256((context.parent / canonical).read_bytes())
    event = enqueue_learning(
        context,
        event_id="canonical",
        origin="closeout",
        evidence=[".context//gc/closeouts/build.json"],
    )
    assert event["evidence"] == {canonical: expected}
    planned = plan_rule(
        context,
        **{k: v for k, v in reflection.items() if k != "verified"},
        evidence=(".context//gc/closeouts/build.json:L1",),
    )
    rule = rules_in(planned["content"])[0]
    assert rule["evidence"] == [canonical + ":L1"]
    assert rule["evidence_sha256"] == {canonical + ":L1": expected}


@pytest.mark.parametrize(
    "tamper", ["changed-evidence", "ephemeral-event", "ephemeral-candidate"]
)
def test_prepared_learning_rechecks_durability_and_hashes_before_apply(
    lesson: tuple[Path, dict], tamper: str
) -> None:
    context, reflection = lesson
    enqueue_learning(
        context,
        event_id="prepared",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    event = prepare_learning(context, "prepared", reflection)
    if tamper == "changed-evidence":
        (context / "gc/closeouts/build.json").write_text(
            "changed after preparation", encoding="utf-8"
        )
    else:
        proof = context / "cache/proof.json"
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_text("cached", encoding="utf-8")
        if tamper == "ephemeral-event":
            event_file = next((context / "gc/learning").glob("*.json"))
            event["evidence"] = {
                ".context//cache/proof.json": sha256(proof.read_bytes())
            }
            event_file.write_text(json.dumps(event), encoding="utf-8")
        else:
            candidate_file = context / "gc/evolve" / event["run"] / "candidates.jsonl"
            candidate = json.loads(candidate_file.read_text(encoding="utf-8"))
            candidate["evidence"] = [".context//cache/proof.json"]
            candidate_file.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
    with pytest.raises(EvolveError, match="durable evidence|evidence changed"):
        finish_learning(context, "prepared", reflection)
    assert (
        "Invalidate the cache" not in (context / "conventions/testing.md").read_text()
    )
