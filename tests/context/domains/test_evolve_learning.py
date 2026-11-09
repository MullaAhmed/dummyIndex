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
from dummyindex.context.domains.probation import store
from dummyindex.context.domains.probation.enums import State
from dummyindex.context.domains.probation.models import Item
from dummyindex.context.domains.probation.rules import CAP_REASON, HIGH_IMPACT

CHAT_CUE = "A human correction was attributed to .context/conventions/testing.md."
RULE_TEST = 'from pathlib import Path\ndef test_rule():\n    assert "dummyindex:rule" in Path(".context/conventions/testing.md").read_text()\n'


def _ok(argv: list[str], cwd: Path) -> tuple[int, str]:
    return 0, "ok"


def _rule_tests(root: Path) -> tuple[str, ...]:
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests/test_rule.py").write_text(RULE_TEST, encoding="utf-8")
    return ("tests/test_rule.py",)


def _chat(context: Path, event_id: str = "chat:c1") -> dict:
    return enqueue_learning(
        context,
        event_id=event_id,
        origin="human",
        evidence=[".context/gc/closeouts/build.json"],
        cue=CHAT_CUE,
    )


@pytest.mark.unit
def test_chat_event_enters_probation_without_committed_writes(lesson) -> None:
    context, reflection = lesson
    tests = _rule_tests(context.parent)
    conventions = {p: p.read_bytes() for p in (context / "conventions").iterdir()}
    _chat(context)
    result = finish_learning(context, "chat:c1", reflection, tests=tests)
    assert not (context / "gc/evolution.jsonl").exists()
    assert {p: p.read_bytes() for p in (context / "conventions").iterdir()} == (
        conventions
    )
    assert not (context / "gc/evolve").exists()
    items = store.load_items(context)
    assert len(items) == 1
    assert items[0].state is State.PROBATION
    assert result["verdict"] == "pass"
    assert result["probation"] == reflection["rule_id"]


@pytest.mark.unit
def test_chat_no_committed_file_holds_body(lesson) -> None:
    context, reflection = lesson
    root = context.parent
    tests = _rule_tests(root)
    _chat(context)
    finish_learning(context, "chat:c1", reflection, tests=tests, runner=_ok)
    assert store.load_items(context)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.relative_to(root).as_posix().startswith(".context/cache/"):
            continue
        assert reflection["body"] not in path.read_bytes().decode("utf-8", "replace")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_id", "origin"), [("build:one", "closeout"), ("human:h1", "human")]
)
def test_closeout_and_legacy_human_events_still_auto_apply(
    lesson, event_id: str, origin: str
) -> None:
    context, reflection = lesson
    tests = _rule_tests(context.parent)
    enqueue_learning(
        context,
        event_id=event_id,
        origin=origin,
        evidence=[".context/gc/closeouts/build.json"],
        cue="Cache contract changed",
    )
    result = finish_learning(context, event_id, reflection, tests=tests, runner=_ok)
    assert result["state"] == "applied"
    target = context / "conventions/testing.md"
    assert reflection["body"] in target.read_text(encoding="utf-8")
    records = [
        json.loads(line)
        for line in (context / "gc/evolution.jsonl").read_text().splitlines()
    ]
    assert any(record.get("kind") == "promote" for record in records)
    assert store.load_items(context) == []


@pytest.mark.unit
@pytest.mark.parametrize("suffix", [" see https://example.com", "\n```\ncode\n```", "​"])
def test_chat_high_impact_body_blocked(lesson, suffix: str) -> None:
    context, reflection = lesson
    _chat(context, "chat:hi")
    body = {**reflection, "body": reflection["body"] + suffix}
    result = prepare_learning(context, "chat:hi", body)
    assert result["state"] == "evaluated"
    assert result["verdict"] == "blocked"
    assert result["reason"] == HIGH_IMPACT
    assert store.load_items(context) == []


@pytest.mark.unit
def test_chat_bad_probe_rejected(lesson) -> None:
    context, reflection = lesson
    _chat(context, "chat:bad")
    with pytest.raises(EvolveError):
        prepare_learning(context, "chat:bad", {**reflection, "probe": {"require": "("}})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "expected"), [("new", "cache changed"), ("legacy", CHAT_CUE)]
)
def test_chat_applies_when_defaults_to_cue(lesson, shape: str, expected: str) -> None:
    context, reflection = lesson
    tests = _rule_tests(context.parent)
    if shape == "new":
        reflection = {
            **{k: v for k, v in reflection.items() if k != "body"},
            "cue": "cache changed",
            "lesson": "Invalidate on digest change",
            "evidence": ".context/gc/closeouts/build.json",
            "confidence": "high",
        }
    _chat(context)
    result = finish_learning(context, "chat:c1", reflection, tests=tests, runner=_ok)
    assert result["verdict"] == "pass"
    assert store.load_items(context)[0].applies_when == expected


@pytest.mark.unit
def test_chat_probation_caps_block(lesson) -> None:
    context, reflection = lesson
    tests = _rule_tests(context.parent)
    _chat(context, "chat:c1")
    first = finish_learning(context, "chat:c1", reflection, tests=tests, runner=_ok)
    assert first["probation"] == reflection["rule_id"]

    _chat(context, "chat:c2")
    second = finish_learning(
        context,
        "chat:c2",
        {**reflection, "rule_id": "cache-other"},
        tests=tests,
        runner=_ok,
    )
    assert second["verdict"] == "blocked"
    assert second["reason"] == CAP_REASON
    assert [item.id for item in store.load_items(context)] == [reflection["rule_id"]]

    store.item_path(context, reflection["rule_id"]).unlink()
    for index in range(10):
        store.save_item(
            context,
            Item(
                id=f"pre-{index:02d}",
                target=f".context/conventions/topic-{index}.md",
                body="Pre-existing rule.",
                applies_when="when pre-existing",
                prediction="prediction",
                probe=None,
                sources={},
                tests=(),
                evidence=(),
                origin_session=None,
                learning_event="seed",
                created="2026-01-01T00:00:00+00:00",
                state=State.PROBATION,
                harm=(),
            ),
        )
    _chat(context, "chat:c3")
    third = finish_learning(context, "chat:c3", reflection, tests=tests, runner=_ok)
    assert third["verdict"] == "blocked"
    assert third["reason"] == CAP_REASON


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


def test_explicitly_empty_learning_checks_do_not_auto_discover_unrelated_tests(
    lesson: tuple[Path, dict],
) -> None:
    context, reflection = lesson
    unrelated = context.parent / "tests/test_testing.py"
    unrelated.parent.mkdir()
    unrelated.write_text("def test_unrelated():\n    assert True\n", encoding="utf-8")
    enqueue_learning(
        context,
        event_id="accepted-no-checks",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )

    result = finish_learning(context, "accepted-no-checks", reflection, tests=())

    assert result["state"] == "evaluated"
    assert result["verdict"] == "blocked"
    gate_path = context / "gc/evolve" / result["run"] / "gate-0.json"
    assert json.loads(gate_path.read_text(encoding="utf-8"))["receipt"]["tests"] == []
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


@pytest.mark.unit
def test_new_shape_lesson_applies_and_persists_status(lesson) -> None:
    context, reflection = lesson
    tests = context.parent / "tests"
    tests.mkdir()
    (tests / "test_lesson.py").write_text(
        "from pathlib import Path\ndef test_lesson():\n    assert 'When cache changed: Invalidate' in Path('.context/conventions/testing.md').read_text()\n",
        encoding="utf-8",
    )
    new = {
        **{k: v for k, v in reflection.items() if k != "body"},
        "cue": "cache changed",
        "lesson": "Invalidate on digest change",
        "evidence": ".context/gc/closeouts/build.json",
        "confidence": "high",
    }
    enqueue_learning(
        context,
        event_id="new-shape",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    result = finish_learning(context, "new-shape", new, tests=("tests/test_lesson.py",))
    assert result["status"] == "applied"
    assert "legacy_shape" not in result
    on_disk = json.loads(next((context / "gc/learning").glob("*.json")).read_text())
    assert on_disk["status"] == "applied"
    assert (
        "When cache changed: Invalidate on digest change"
        in (context / "conventions/testing.md").read_text()
    )


@pytest.mark.unit
def test_legacy_reflection_is_flagged_and_warned(lesson) -> None:
    context, reflection = lesson
    enqueue_learning(
        context,
        event_id="legacy",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    with pytest.warns(UserWarning, match="legacy_shape"):
        event = prepare_learning(context, "legacy", reflection)
    assert event["legacy_shape"] is True
    assert event["status"] == "pending"


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["cue", "lesson", "evidence", "confidence"])
def test_new_shape_lesson_missing_a_field_is_rejected(lesson, missing: str) -> None:
    context, reflection = lesson
    new = {
        **reflection,
        "cue": "c",
        "lesson": "l",
        "evidence": "e",
        "confidence": "low",
    }
    del new[missing]
    new["cue" if missing != "cue" else "lesson"] = "x"
    enqueue_learning(
        context,
        event_id="bad",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    with pytest.raises(EvolveError, match="lesson"):
        prepare_learning(context, "bad", new)


@pytest.mark.unit
def test_harvest_and_gate_payloads_carry_no_status(lesson) -> None:
    context, reflection = lesson
    enqueue_learning(
        context,
        event_id="payloads",
        origin="closeout",
        evidence=[".context/gc/closeouts/build.json"],
    )
    with pytest.warns(UserWarning):
        finish_learning(context, "payloads", reflection)
    files = list((context / "gc/evolve").glob("learning-*/harvest.json"))
    files += list((context / "gc/evolve").glob("learning-*/gate-0.json"))
    assert len(files) == 2
    for path in files:
        assert "status" not in json.loads(path.read_text(encoding="utf-8"))
