"""Execute a real fixture process and grade artifacts independently.

The fixture is a deterministic agent stand-in for controller verification; it
does not claim to measure LLM behavior. Production commands supply the model.
"""

import json
import sys
import time
from pathlib import Path

import pytest

from dummyindex.context.domains.evolve_experiments import (
    _execute,
    run_experiment,
    utility_status,
)
from dummyindex.context.domains.evolve_gate import EvolveError

_RUNNER = """import argparse,json,pathlib,hashlib
p=argparse.ArgumentParser();p.add_argument('--request');a=p.parse_args()
r=json.loads(pathlib.Path(a.request).read_text())
g=json.loads(pathlib.Path('.context/conventions/testing.md').read_text())
if g['algorithm']=='infra':
    print(json.dumps({'status':'infra_error','reason':'fixture model unavailable'}));raise SystemExit
correct=0;outcomes=[]
for c in r['cases']:
    task=json.loads(pathlib.Path(c['path']).read_text())
    # Executor makes an artifact; a separate golden answer grades it.
    answer=sum(task['numbers']) if g['algorithm']=='sum' or (g['algorithm']=='dev_only' and r['phase']=='development') else len(task['numbers'])
    pathlib.Path('answer.json').write_text(json.dumps(answer))
    actual=json.loads(pathlib.Path('answer.json').read_text())
    correct+=actual==task['expected']
    outcomes.append({'id':c['id'],'status':'pass' if actual==task['expected'] else 'fail'})
if r['phase']=='development':
    assert not pathlib.Path('cases/heldout.json').exists(), 'heldout leaked into development'
loaded=[dict(row,sha256=hashlib.sha256(pathlib.Path(row['path']).read_bytes()).hexdigest()) for row in r['guidance']]
if g.get('wrong_hash'):
    loaded[0]['sha256']='0'*64
print(json.dumps({'status':'measured','cases':outcomes,'tokens':g.get('tokens',10),'cost_usd':g.get('cost',0.1),'guidance_bytes':g.get('claimed_guidance_bytes',0),'loaded':loaded,'evidence':'answer.json independently compared with fixed golden answers'}))
"""


@pytest.fixture
def experiment(tmp_path: Path) -> tuple[Path, Path, dict]:
    context = tmp_path / ".context"
    (context / "conventions").mkdir(parents=True)
    target = context / "conventions/testing.md"
    target.write_text(json.dumps({"algorithm": "sum", "cost": 0.2}), encoding="utf-8")
    (tmp_path / "runner.py").write_text(_RUNNER, encoding="utf-8")
    (tmp_path / "cases").mkdir()
    for name, numbers in (("dev", [2, 3]), ("heldout", [4, 6])):
        (tmp_path / "cases" / f"{name}.json").write_text(
            json.dumps({"numbers": numbers, "expected": sum(numbers)}), encoding="utf-8"
        )
    evidence = tmp_path / "accepted.json"
    evidence.write_text("{}", encoding="utf-8")
    run = context / "gc/evolve/test"
    run.mkdir(parents=True)
    candidates = []
    for index in range(3):
        candidates.append(
            {
                "target_file": ".context/conventions/testing.md",
                "diagnosis": "Measured cost reduction",
                "change_sketch": "Keep correct behavior at lower cost",
                "evidence": ["accepted.json"],
                "prediction": "Artifact remains correct",
            }
        )
        stage = run / "staged" / str(index) / ".context/conventions"
        stage.mkdir(parents=True)
        (stage / "testing.md").write_text(
            json.dumps(
                {
                    "algorithm": "sum",
                    "cost": 0.1 - index * 0.01,
                    "version": str(index + 2),
                }
            ),
            encoding="utf-8",
        )
    (run / "candidates.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in candidates), encoding="utf-8"
    )
    specification = {
        "command": [sys.executable, "runner.py"],
        "cases": [
            {"id": "development", "path": "cases/dev.json", "split": "validation"},
            {"id": "heldout", "path": "cases/heldout.json", "split": "heldout"},
        ],
        "candidates": {"alternative": 0},
        "model": "deterministic-contract-fixture",
        "rubric": "fixed-golden-answer-v1",
        "budget": {"seconds": 30, "stages": 6},
    }
    return context, run, specification


def test_real_paired_replay_selects_cheaper_equal_quality_and_reuses_receipt(
    experiment: tuple[Path, Path, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, run, specification = experiment
    monkeypatch.setenv("CODEX_TOOL_CALL_ID", "initial-dispatch")
    result = run_experiment(context, run, specification)
    assert result["current"] == "alternative"
    assert result["current_reason"] == "lower_cost"
    assert [r["phase"] for r in result["stages"]] == [
        "development",
        "development",
        "heldout",
        "heldout",
    ]
    assert result["tokens"] == 40
    monkeypatch.setenv("CODEX_TOOL_CALL_ID", "later-dispatch")
    assert run_experiment(context, run, specification)["cached"] is True
    utility = utility_status(context)
    assert len({r["version"] for r in utility}) == 2
    assert all(r["successes"] == 2 for r in utility)
    repeated = run_experiment(context, run, {**specification, "repetition": 1})
    assert repeated["identity"] != result["identity"]
    assert repeated["cached"] is False


def test_equal_quality_cost_and_tokens_select_shorter_utf8_guidance_and_replay_heldout(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    incumbent = '{"algorithm":"sum","cost":0.1,"tokens":10,"label":"€€€","claimed_guidance_bytes":"000000000"}'
    candidate = '{"algorithm":"sum","cost":0.1,"tokens":10,"label":"é","claimed_guidance_bytes":"999999999"}'
    (context / "conventions/testing.md").write_text(incumbent, encoding="utf-8")
    (run / "staged/0/.context/conventions/testing.md").write_text(
        candidate, encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["current"] == "alternative"
    assert result["best_reason"] == result["current_reason"] == "fewer_guidance_bytes"
    assert [stage["phase"] for stage in result["stages"]] == [
        "development",
        "development",
        "heldout",
        "heldout",
    ]
    assert [stage["guidance_bytes"] for stage in result["stages"]] == [
        len(incumbent.encode("utf-8")),
        len((run / "staged/0/.context/conventions/testing.md").read_bytes()),
        len(incumbent.encode("utf-8")),
        len((run / "staged/0/.context/conventions/testing.md").read_bytes()),
    ]
    assert result["stages"][1]["guidance_bytes"] < result["stages"][0]["guidance_bytes"]


def test_equal_quality_prefers_tokens_before_guidance_bytes(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    incumbent = '{"algorithm":"sum","cost":0.1,"tokens":10}'
    candidate = (
        '{"algorithm":"sum","cost":0.1,"tokens":5,"padding":"a much longer body"}'
    )
    (context / "conventions/testing.md").write_text(incumbent, encoding="utf-8")
    (run / "staged/0/.context/conventions/testing.md").write_text(
        candidate, encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["current"] == "alternative"
    assert result["best_reason"] == result["current_reason"] == "lower_tokens"
    assert result["stages"][1]["guidance_bytes"] > result["stages"][0]["guidance_bytes"]


def test_equal_quality_cost_and_tokens_reject_larger_guidance(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    incumbent = (
        '{"algorithm":"sum","cost":0.1,"tokens":10,"claimed_guidance_bytes":999999999}'
    )
    candidate = '{"algorithm":"sum","cost":0.1,"tokens":10,"padding":"larger","claimed_guidance_bytes":0}'
    (context / "conventions/testing.md").write_text(incumbent, encoding="utf-8")
    (run / "staged/0/.context/conventions/testing.md").write_text(
        candidate, encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["best"] == result["current"] == "incumbent"
    assert result["stages"][1]["guidance_bytes"] > result["stages"][0]["guidance_bytes"]
    assert len(result["stages"]) == 2


def test_exact_metric_tie_keeps_incumbent(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    body = '{"algorithm":"sum","cost":0.1,"tokens":10}'
    (context / "conventions/testing.md").write_text(body, encoding="utf-8")
    (run / "staged/0/.context/conventions/testing.md").write_text(
        body, encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["best"] == result["current"] == "incumbent"
    assert result["best_reason"] == result["current_reason"] == "incumbent"


def test_heldout_regression_keeps_incumbent_despite_development_gain(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    (run / "staged/0/.context/conventions/testing.md").write_text(
        '{"algorithm":"dev_only","cost":0.01}', encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["best"] == "alternative"
    assert result["best_reason"] == "lower_cost"
    assert result["current"] == "incumbent"
    assert result["current_reason"] == "incumbent"
    assert result["stop_reason"] == "heldout_regression_or_unmeasured"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable mode contract")
def test_project_executor_preserves_mode_and_mode_change_invalidates_receipt(
    experiment,
):
    import shlex

    context, run, specification = experiment
    script = context.parent / "runner.sh"
    script.write_text(
        "#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' runner.py "$@"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    specification["command"] = ["./runner.sh"]
    first = run_experiment(context, run, specification)
    assert first["current"] == "alternative"
    assert first["contract"]["modes"]["runner.sh"] == 0o755
    script.chmod(0o744)
    second = run_experiment(context, run, specification)
    assert second["current"] == "alternative"
    assert second["identity"] != first["identity"]


def test_trigger_declaration_cannot_mask_actual_candidate_regression(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    staged = run / "staged/0/.context/conventions/testing.md"
    staged.write_text(
        json.dumps(
            {"algorithm": "count", "specialist_trigger": True, "version": "bad"}
        ),
        encoding="utf-8",
    )
    result = run_experiment(context, run, specification)
    assert result["current"] == result["best"] == "incumbent"
    assert result["stages"][1]["quality"] == 0
    assert all(row["version"].startswith("sha256:") for row in utility_status(context))
    again = run_experiment(context, run, {**specification, "repetition": 1})
    bad = next(r for r in utility_status(context) if r["failures"] > 0)
    assert bad["state"] == "suspect"
    assert again["current"] == "incumbent"


def test_general_domain_and_composition_all_execute_and_regressing_composition_loses(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    (run / "staged/2/.context/conventions/testing.md").write_text(
        json.dumps({"algorithm": "count", "version": "composed"}), encoding="utf-8"
    )
    specification["candidates"] = {"general": 0, "domain": 1, "composition": 2}
    result = run_experiment(context, run, specification)
    assert [r["label"] for r in result["stages"][:4]] == [
        "incumbent",
        "general",
        "domain",
        "composition",
    ]
    assert result["current"] == "domain"
    assert result["stages"][3]["quality"] == 0


def test_infra_is_unmeasured_and_total_budget_keeps_incumbent(
    experiment: tuple[Path, Path, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    context, run, specification = experiment
    (run / "staged/0/.context/conventions/testing.md").write_text(
        '{"algorithm":"infra"}', encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["stages"][1]["status"] == "infra_error"
    assert result["current"] == "incumbent"
    from dummyindex.context.domains import evolve_experiments

    original_execute = evolve_experiments._execute
    calls = 0

    def counted_execute(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(evolve_experiments, "_execute", counted_execute)
    assert run_experiment(context, run, specification)["cached"] is True
    assert calls == 0
    assert (
        run_experiment(context, run, {**specification, "repetition": 1})["cached"]
        is False
    )
    assert calls > 0
    specification["budget"]["stages"] = 1
    result = run_experiment(context, run, specification)
    assert result["stop_reason"] == "budget_exhausted"
    assert len(result["stages"]) == 1
    assert result["current"] == "incumbent"


def test_exposed_case_cannot_be_laundered_into_heldout(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    run_experiment(context, run, specification)
    specification["cases"][1]["derived_from"] = ["development"]
    with pytest.raises(EvolveError, match="ancestor"):
        run_experiment(context, run, specification)


def test_aggregate_improvement_cannot_hide_required_control_regression(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    (context / "conventions/testing.md").write_text(
        '{"algorithm":"count"}', encoding="utf-8"
    )
    cases = context.parent / "cases"
    (cases / "second.json").write_text(
        '{"numbers":[2,3],"expected":5}', encoding="utf-8"
    )
    (cases / "control.json").write_text(
        '{"numbers":[2,3],"expected":2}', encoding="utf-8"
    )
    specification["cases"] = [
        {
            "id": "one",
            "path": "cases/dev.json",
            "split": "validation",
            "required": False,
        },
        {
            "id": "two",
            "path": "cases/second.json",
            "split": "validation",
            "required": False,
        },
        {
            "id": "control",
            "path": "cases/control.json",
            "split": "validation",
            "required": True,
        },
        {"id": "heldout", "path": "cases/heldout.json", "split": "heldout"},
    ]
    result = run_experiment(context, run, specification)
    assert result["stages"][1]["quality"] > result["stages"][0]["quality"]
    assert result["stages"][1]["controls_pass"] is False
    assert result["best"] == result["current"] == "incumbent"


def test_claimed_load_with_wrong_content_hash_is_unmeasured(
    experiment: tuple[Path, Path, dict],
) -> None:
    context, run, specification = experiment
    (run / "staged/0/.context/conventions/testing.md").write_text(
        '{"algorithm":"sum","wrong_hash":true}', encoding="utf-8"
    )
    result = run_experiment(context, run, specification)
    assert result["stages"][1]["status"] == "infra_error"
    assert result["current"] == "incumbent"


def test_runner_output_is_bounded_while_process_is_alive(tmp_path: Path) -> None:
    runner = tmp_path / "flood.py"
    runner.write_text(
        "import os,time\nos.write(1,b'x'*100000)\ntime.sleep(30)\n", encoding="utf-8"
    )
    before = time.monotonic()
    result = _execute(
        [sys.executable, str(runner)], tmp_path, {"cases": [], "guidance": []}, 5
    )
    assert result["status"] == "infra_error"
    assert "output exceeds" in result["reason"]
    assert time.monotonic() - before < 8


def test_timeout_kills_descendant_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.domains import evolve_experiments

    if sys.platform == "win32":
        import _winapi

    marker = tmp_path / "child-survived"
    ready = tmp_path / "child-ready"
    gate = tmp_path / "child-release"
    child = tmp_path / "child.py"
    child.write_text(
        "import os,pathlib,time\n"
        f"ready=pathlib.Path({str(ready)!r})\n"
        f"gate=pathlib.Path({str(gate)!r})\n"
        "pending=ready.with_suffix('.tmp')\n"
        "pending.write_text(str(os.getpid()))\npending.replace(ready)\n"
        "deadline=time.monotonic()+30\n"
        "while not gate.exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
        f"if gate.exists(): pathlib.Path({str(marker)!r}).write_text('survived')\n",
        encoding="utf-8",
    )
    runner = tmp_path / "parent.py"
    runner.write_text(
        "import subprocess,sys,time\nsubprocess.Popen([sys.executable,"
        + repr(str(child))
        + "])\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    popen = evolve_experiments.subprocess.Popen
    child_handle = None

    def ready_popen(argv, **kwargs):
        nonlocal child_handle
        process = popen(argv, **kwargs)
        if argv[:2] != [sys.executable, str(runner)]:
            return process
        deadline = time.monotonic() + 5
        while (
            not ready.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        if not ready.exists():
            evolve_experiments._kill_tree(process)
            pytest.fail("descendant did not signal readiness")
        if sys.platform == "win32":
            child_handle = _winapi.OpenProcess(
                _winapi.SYNCHRONIZE, False, int(ready.read_text())
            )
        return process

    monkeypatch.setattr(evolve_experiments.subprocess, "Popen", ready_popen)
    try:
        result = _execute(
            [sys.executable, str(runner)], tmp_path, {"cases": [], "guidance": []}, 0.3
        )
        # Slow taskkill must finish before a surviving child can write the marker.
        gate.touch()
        assert "wall-time budget" in result["reason"]
        if child_handle is not None:
            assert _winapi.WaitForSingleObject(child_handle, 0) == _winapi.WAIT_OBJECT_0
        time.sleep(1.7)
        assert not marker.exists()
    finally:
        gate.touch(exist_ok=True)
        if child_handle is not None:
            _winapi.CloseHandle(child_handle)
