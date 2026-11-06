"""Fixed native actors and independent artifact grading; no model is called."""

import json
import os

import pytest

from dummyindex.context.domains.evolve_experiments import run_experiment, utility_status
from dummyindex.context.domains.evolve_gate import EvolveError


@pytest.fixture
def native(tmp_path):
    context = tmp_path / ".context"
    target = context / "conventions/testing.md"
    target.parent.mkdir(parents=True)
    target.write_text('{"algorithm":"count"}')
    (tmp_path / "cases").mkdir()
    for name, numbers in (("dev", [2, 3]), ("held", [4, 6])):
        (tmp_path / f"cases/{name}.json").write_text(
            json.dumps({"numbers": numbers, "expected": sum(numbers)})
        )
    (tmp_path / "grader.py").write_text("# pinned independent evaluator\n")
    run = context / "gc/evolve/native-test"
    run.mkdir(parents=True)
    spec = {
        "execution": "native",
        "model": "fixed-test-actor",
        "rubric": "sum-v1",
        "cases": [
            {"id": "dev", "path": "cases/dev.json", "split": "validation"},
            {"id": "held", "path": "cases/held.json", "split": "heldout"},
        ],
        "guidance": [{"path": ".context/conventions/testing.md"}],
        "grading_paths": ["grader.py"],
        "budget": {"seconds": 60},
    }
    return context, run, spec


def response(context, request, *, fail=False, known=False):
    root = context.parent
    work = root / request["workspace"]
    result = {
        "actor_id": request["request_id"],
        "tokens": 1 if known else None,
        "cost_usd": 0.01 if known else None,
    }
    if request["phase"] == "development":
        assert not (work / "cases/held.json").exists()
    if request["action"] != "grade":
        assert not (work / "grader.py").exists()
    if request["action"] == "author":
        assert request["feedback"]
        assert request["feedback"][0]["label"] == "incumbent"
        if request["label"] == "composition":
            assert {r["label"] for r in request["feedback"]} == {
                "incumbent",
                "general",
                "domain",
            }
            assert set(request["candidate_changes"]) == {"general", "domain"}
        result.update(
            edits={".context/conventions/testing.md": '{"algorithm":"sum"}'},
            diagnosis="Observed count instead of sum",
            prediction="Correct summed artifact",
        )
    elif request["action"] == "execute":
        case = json.loads((work / request["case"]["path"]).read_text())
        guidance = json.loads((work / ".context/conventions/testing.md").read_text())
        actual = (
            sum(case["numbers"])
            if guidance["algorithm"] == "sum"
            else len(case["numbers"])
        )
        (work / "answer.json").write_text(json.dumps(actual))
        result.update(status="completed", loaded=request["guidance"])
    else:
        assert (work / "grader.py").read_text() == "# pinned independent evaluator\n"
        case = json.loads((work / request["case"]["path"]).read_text())
        actual = json.loads((work / "answer.json").read_text())
        # A grader may produce caches without changing frozen execution evidence.
        (work / ".pytest_cache").mkdir()
        (work / ".pytest_cache/note").write_text("grader output")
        status = "pass" if actual == case["expected"] and not fail else "fail"
        result.update(
            status="measured",
            cases=[{"id": request["case"]["id"], "status": status}],
            evidence=f"Independently read answer artifact: {actual}; expected {case['expected']}",
        )
    return {"request_id": request["request_id"], "result": result}


def finish(native, *, failures=()):
    context, run, spec = native
    view = run_experiment(context, run, spec)
    actions = []
    while view["state"] != "complete":
        request = view["pending"]
        actions.append((request["action"], request["label"], request["phase"]))
        payload = response(
            context, request, fail=(request["label"], request["phase"]) in failures
        )
        view = run_experiment(context, run, payload)
    return view, actions


def test_native_adaptive_roundtrip_unknown_resources_and_independent_artifacts(native):
    context, run, spec = native
    original = (context / "conventions/testing.md").read_bytes()
    view, actions = finish(native)
    assert view["current"] == "general"
    assert view["candidate_index"] == 0
    assert view["tokens"] is None and view["cost_usd"] is None
    assert view["known_tokens"] == view["known_cost_usd"] == 0
    assert view["actions"] == len(actions) == 15
    assert actions.index(("author", "general", "development")) > actions.index(
        ("grade", "incumbent", "development")
    )
    assert actions.index(("author", "domain", "development")) > actions.index(
        ("grade", "general", "development")
    )
    assert actions.index(("author", "composition", "development")) > actions.index(
        ("grade", "domain", "development")
    )
    assert (context / "conventions/testing.md").read_bytes() == original
    assert len((run / "candidates.jsonl").read_text().splitlines()) == 3
    assert len(list((run / "native-feedback").glob("*.json"))) == 3
    assert all(
        r["tokens"] is None and r["cost_usd"] is None for r in utility_status(context)
    )
    assert run_experiment(context, run, spec) == view


def test_native_equal_quality_with_unknown_cost_retains_incumbent(native):
    context, _, _ = native
    (context / "conventions/testing.md").write_text('{"algorithm":"sum"}')
    view, actions = finish(native)
    assert view["current"] == "incumbent"
    assert view["candidate_index"] is None
    assert not any(
        label == "composition" or phase == "heldout" for _, label, phase in actions
    )


@pytest.mark.parametrize(
    "failures",
    [
        (("general", "heldout"),),
        (("general", "development"), ("domain", "development")),
    ],
)
def test_native_required_controls_retain_incumbent(native, failures):
    view, _ = finish(native, failures=failures)
    assert view["current"] == "incumbent"


def test_native_pending_is_stable_and_accepted_response_idempotent(native):
    context, run, spec = native
    first = run_experiment(context, run, spec)
    assert run_experiment(context, run, spec) == first
    request = first["pending"]
    with pytest.raises(EvolveError, match="out-of-order"):
        run_experiment(
            context, run, {"request_id": "composition-before-feedback", "result": {}}
        )
    payload = response(context, request)
    second = run_experiment(context, run, payload)
    assert second["pending"]["action"] == "grade"
    assert second["actions"] == 2
    assert run_experiment(context, run, payload) == second
    with pytest.raises(EvolveError, match="conflicting"):
        run_experiment(
            context, run, {**payload, "result": {**payload["result"], "tokens": 3}}
        )


@pytest.mark.parametrize(
    "path",
    [
        "cases/dev.json",
        "cases/held.json",
        "grader.py",
        ".context/conventions/testing.md",
    ],
)
def test_native_rejects_changed_pinned_inputs(native, path):
    context, run, spec = native
    run_experiment(context, run, spec)
    (context.parent / path).write_text("changed")
    with pytest.raises(EvolveError, match="baseline"):
        run_experiment(context, run, spec)


def test_native_rejects_candidate_and_frozen_artifact_tampering(native):
    context, run, spec = native
    view = run_experiment(context, run, spec)
    while view["pending"]["action"] != "author":
        view = run_experiment(context, run, response(context, view["pending"]))
    view = run_experiment(context, run, response(context, view["pending"]))
    stage = run / "staged/0/.context/conventions/testing.md"
    previous = stage.read_bytes()
    stage.write_text("changed")
    with pytest.raises(EvolveError, match="candidate bytes"):
        run_experiment(context, run, spec)
    stage.write_bytes(previous)
    view = run_experiment(context, run, response(context, view["pending"]))
    frozen = context.parent / view["pending"]["execution"]["snapshot"]
    (frozen / "answer.json").write_text("999")
    with pytest.raises(EvolveError, match="artifact tampering"):
        run_experiment(context, run, response(context, view["pending"]))


def test_native_action_budget_and_deadline_do_not_reset(native, monkeypatch):
    context, run, spec = native
    spec["budget"]["actions"] = 1
    view = run_experiment(context, run, spec)
    assert view["actions"] == 1
    terminal = run_experiment(context, run, response(context, view["pending"]))
    assert terminal["state"] == "complete" and terminal["actions"] == 1
    assert terminal["current"] == "incumbent"
    assert run_experiment(context, run, spec) == terminal


def test_native_late_response_rejected(native, monkeypatch):
    from dummyindex.context.domains import evolve_native

    context, run, spec = native
    view = run_experiment(context, run, spec)
    payload = response(context, view["pending"])
    monkeypatch.setattr(evolve_native.time, "time", lambda: view["deadline"] + 1)
    with pytest.raises(EvolveError, match="deadline"):
        run_experiment(context, run, payload)


def test_native_each_case_gets_counted_execute_grade_pair(native):
    context, run, spec = native
    extra = context.parent / "cases/dev2.json"
    extra.write_text('{"numbers":[4,2],"expected":6}')
    spec["cases"].insert(1, {"id": "dev2", "path": "cases/dev2.json", "split": "train"})
    view, actions = finish(native)
    assert view["current"] == "general"
    assert view["actions"] == 23
    assert sum(a == "author" for a, _, _ in actions) == 3


def test_native_supports_bounded_sixteen_case_set(native):
    context, run, spec = native
    for index in range(14):
        path = f"cases/extra{index}.json"
        (context.parent / path).write_text(str(index))
        spec["cases"].append({"id": f"extra{index}", "path": path, "split": "heldout"})
    view = run_experiment(context, run, spec)
    assert view["actions"] == 1
    workspace = context.parent / view["pending"]["workspace"]
    assert not list((workspace / "cases").glob("extra*"))


def test_native_invalid_budget_is_domain_error(native):
    context, run, spec = native
    spec["budget"] = []
    with pytest.raises(EvolveError, match="budget must be an object"):
        run_experiment(context, run, spec)


def test_native_interrupted_accept_never_redispatches(native, monkeypatch):
    from dummyindex.context.domains import evolve_native

    context, run, spec = native
    view = run_experiment(context, run, spec)
    payload = response(context, view["pending"])

    def interrupted(*args):
        raise OSError("simulated interrupted artifact capture")

    monkeypatch.setattr(evolve_native, "_accept", interrupted)
    with pytest.raises(EvolveError, match="interruption marker"):
        run_experiment(context, run, payload)
    with pytest.raises(EvolveError, match="interrupted native response"):
        run_experiment(context, run, spec)


def test_native_snapshot_keeps_python_source_in_cache(tmp_path):
    from dummyindex.context.domains.evolve_native_snapshot import _tree

    cache = tmp_path / "src/__pycache__"
    cache.mkdir(parents=True)
    (cache / "rogue.py").write_text("source")
    (cache / "generated.pyc").write_bytes(b"cache")
    assert _tree(tmp_path) == {"src/__pycache__/rogue.py": b"source"}


def test_native_expired_pending_becomes_stable_terminal(native, monkeypatch):
    from dummyindex.context.domains import evolve_native

    context, run, spec = native
    view = run_experiment(context, run, spec)
    monkeypatch.setattr(evolve_native.time, "time", lambda: view["deadline"] + 1)
    terminal = run_experiment(context, run, spec)
    assert terminal["state"] == "complete" and terminal["pending"] is None
    assert terminal["current"] == "incumbent" and terminal["tokens"] is None
    assert run_experiment(context, run, spec) == terminal


@pytest.mark.parametrize("path", ["answer.json", "grader.py"])
def test_native_rejects_mutated_grader_copy(native, path):
    context, run, spec = native
    view = run_experiment(context, run, spec)
    view = run_experiment(context, run, response(context, view["pending"]))
    payload = response(context, view["pending"])
    (context.parent / view["pending"]["workspace"] / path).write_text("changed")
    with pytest.raises(EvolveError, match="grader modified"):
        run_experiment(context, run, payload)


@pytest.mark.parametrize("metric", ["tokens", "cost_usd"])
def test_native_unknown_capped_usage_stops(native, metric):
    context, run, spec = native
    spec["budget"][metric] = 100
    view = run_experiment(context, run, spec)
    terminal = run_experiment(context, run, response(context, view["pending"]))
    assert terminal["state"] == "complete" and terminal["actions"] == 1
    assert terminal["stop_reason"] == "resource_cap_unaccounted"
    assert terminal[metric] is None and terminal["current"] == "incumbent"


def test_native_bad_transport_does_not_poison_pending(native):
    context, run, spec = native
    view = run_experiment(context, run, spec)
    with pytest.raises(EvolveError, match="actor_id"):
        run_experiment(
            context, run, {"request_id": view["pending"]["request_id"], "result": {}}
        )
    assert run_experiment(context, run, spec) == view
    view = run_experiment(context, run, response(context, view["pending"]))
    view = run_experiment(context, run, response(context, view["pending"]))
    payload = response(context, view["pending"])
    bad = {**payload, "result": {**payload["result"], "diagnosis": ""}}
    with pytest.raises(EvolveError, match="diagnosis"):
        run_experiment(context, run, bad)
    assert run_experiment(context, run, spec) == view
    assert run_experiment(context, run, payload)["pending"]["action"] == "execute"


def test_native_feedback_provenance_is_pinned(native):
    context, run, spec = native
    view = run_experiment(context, run, spec)
    while view["pending"]["action"] != "author":
        view = run_experiment(context, run, response(context, view["pending"]))
    run_experiment(context, run, response(context, view["pending"]))
    next((run / "native-feedback").glob("*.json")).write_text("{}")
    with pytest.raises(EvolveError, match="feedback changed"):
        run_experiment(context, run, spec)


def test_native_resume_ignores_host_dispatch_id_but_pins_model_environment(
    native, monkeypatch
):
    context, run, spec = native
    monkeypatch.setenv("CODEX_TOOL_CALL_ID", "initial-dispatch")
    view = run_experiment(context, run, spec)
    payload = response(context, view["pending"])
    monkeypatch.setenv("CODEX_TOOL_CALL_ID", "later-dispatch")
    assert run_experiment(context, run, payload)["pending"]["action"] == "grade"
    monkeypatch.setenv("DUMMYINDEX_MODEL_ENDPOINT", "changed-model-endpoint")
    with pytest.raises(EvolveError, match="environment changed"):
        run_experiment(context, run, spec)


def test_native_runtime_profile_invalidates_resume(native, monkeypatch):
    from dummyindex.context.domains import evolve_native_snapshot

    context, run, spec = native
    run_experiment(context, run, spec)
    monkeypatch.setattr(evolve_native_snapshot.sys, "version", "changed interpreter")
    with pytest.raises(EvolveError, match="environment changed"):
        run_experiment(context, run, spec)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable mode contract")
def test_native_grader_preserves_and_binds_executor_modes(native):
    context, run, spec = native
    view = run_experiment(context, run, spec)
    payload = response(context, view["pending"])
    script = context.parent / view["pending"]["workspace"] / "new-script.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)
    view = run_experiment(context, run, payload)
    copy = context.parent / view["pending"]["workspace"] / "new-script.sh"
    assert copy.stat().st_mode & 0o777 == 0o755
    payload = response(context, view["pending"])
    copy.chmod(0o644)
    with pytest.raises(EvolveError, match="grader modified"):
        run_experiment(context, run, payload)


def test_native_accepted_response_remains_idempotent_after_expiry(native, monkeypatch):
    from dummyindex.context.domains import evolve_native

    context, run, spec = native
    view = run_experiment(context, run, spec)
    payload = response(context, view["pending"])
    view = run_experiment(context, run, payload)
    monkeypatch.setattr(evolve_native.time, "time", lambda: view["deadline"] + 1)
    terminal = run_experiment(context, run, payload)
    assert terminal["state"] == "complete" and terminal["actions"] == 2
    assert run_experiment(context, run, payload) == terminal
