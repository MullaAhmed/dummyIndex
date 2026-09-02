"""CLI lifecycle for ``dummyindex context evolve`` — one JSONL line per transition.

Drives ``dispatch(["evolve", ...])`` over a throwaway repo and pins the
contract the skill depends on: harvest writes run artifacts + a `harvest`
event; the sleep contract exits 0 having written nothing; diagnose validates
candidates; apply gates them (blocked on all four rejected observation
shapes); promote refuses a blocked verdict without an explicit override but
records the reason when given; rollback restores; discard drops. Every
transition appends exactly one line to `.context/gc/evolution.jsonl`.

The pytest-subset stage runs for real here (a trivial in-repo test file) so
the G1 subprocess contract is exercised end to end once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch

pytestmark = pytest.mark.integration


# ----- fixtures -----------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo with `.context/`, isolated HOME + projects root."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    repo = tmp_path / "repo"
    ctx = repo / ".context"
    (ctx / "conventions").mkdir(parents=True)
    (ctx / "equipment-evals").mkdir()
    (ctx / "conventions" / "naming.md").write_text(
        "# naming\nold content\n", encoding="utf-8"
    )
    monkeypatch.chdir(repo)
    return repo


def _seed_suite(repo: Path) -> None:
    suite = {
        "cases": [{"case_id": "c1", "prompt": "gc me", "expects_trigger": True}]
    }
    (repo / ".context" / "equipment-evals" / "gc.suite.json").write_text(
        json.dumps(suite), encoding="utf-8"
    )


def _candidate(target: str = ".context/conventions/naming.md") -> dict:
    return {
        "target_file": target,
        "diagnosis": "tighten the naming rule",
        "evidence": ["conventions/naming.md:L1"],
        "change_sketch": "rewrite section",
        "prediction": "naming stays stable",
    }


def _harvest(repo: Path) -> Path:
    assert dispatch(["evolve", "harvest", "--run", "r1"]) == 0
    return repo / ".context" / "gc" / "evolve" / "r1"


def _diagnose(repo: Path, candidates: list[dict]) -> int:
    source = repo.parent / "cands.jsonl"
    source.write_text(
        "".join(json.dumps(c) + "\n" for c in candidates), encoding="utf-8"
    )
    return dispatch(["evolve", "diagnose", "--run", "r1", "--from-file", str(source)])


def _stage(repo: Path, index: int, target: str, content: str) -> None:
    staged = repo / ".context" / "gc" / "evolve" / "r1" / "staged" / str(index)
    staged.mkdir(parents=True, exist_ok=True)
    (staged / Path(target).name).write_text(content, encoding="utf-8")


def _events(repo: Path) -> list[dict]:
    path = repo / ".context" / "gc" / "evolution.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _gate(repo: Path, index: int) -> dict:
    return json.loads(
        (
            repo / ".context" / "gc" / "evolve" / "r1" / f"gate-{index}.json"
        ).read_text(encoding="utf-8")
    )


# ----- harvest + sleep contract --------------------------------------------------


def test_harvest_writes_artifacts_and_one_event(repo: Path) -> None:
    run_dir = _harvest(repo)
    payload = json.loads((run_dir / "harvest.json").read_text(encoding="utf-8"))
    assert payload["items"] == []
    events = _events(repo)
    assert [e["kind"] for e in events] == ["harvest"]
    assert events[0]["outcome"]["items"] == 0


def test_sleep_with_nothing_new_exits_0_writing_nothing(
    repo: Path, tmp_path: Path
) -> None:
    marker = repo / ".context" / "gc"
    before = sorted(p.name for p in marker.rglob("*")) if marker.exists() else []
    rc = dispatch(["evolve", "harvest", "--sleep"])
    after = sorted(p.name for p in marker.rglob("*")) if marker.exists() else []
    assert rc == 0
    assert before == after  # no run dir, no evolution.jsonl, nothing


# ----- diagnose ------------------------------------------------------------------


def test_diagnose_validates_candidates_into_the_run(repo: Path) -> None:
    run_dir = _harvest(repo)
    assert _diagnose(repo, [_candidate()]) == 0
    lines = (run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["target_file"] == ".context/conventions/naming.md"


def test_diagnose_rejects_malformed_candidates_without_writing(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = _harvest(repo)
    bad = _candidate()
    bad["target_file"] = "dummyindex/context/drift.py"
    assert _diagnose(repo, [bad]) == 1
    assert not (run_dir / "candidates.jsonl").exists()
    assert "may never be source code" in capsys.readouterr().err


# ----- apply + gate: the four blocked shapes -------------------------------------


@pytest.mark.parametrize(
    "observations",
    [
        None,  # absent observations file
        {"observations": []},  # partial coverage
        {
            "observations": [
                {"case_id": "c1", "fired": True},
                {"case_id": "c1", "fired": False},
            ]
        },  # duplicated judgment
        {"observations": [{"case_id": "zz", "fired": True}]},  # mismatched id
    ],
)
def test_blocked_verdict_on_all_four_observation_shapes(
    repo: Path, observations: dict | None
) -> None:
    _seed_suite(repo)
    _harvest(repo)
    assert _diagnose(repo, [_candidate(".context/equipment-evals/gc.suite.json")]) == 0
    if observations is not None:
        run_dir = repo / ".context" / "gc" / "evolve" / "r1"
        (run_dir / "observations.json").write_text(
            json.dumps(observations), encoding="utf-8"
        )
    _stage(repo, 0, ".context/equipment-evals/gc.suite.json", '{"cases": []}')
    assert dispatch(["evolve", "apply", "--candidate", "0", "--run", "r1"]) == 0
    gate = _gate(repo, 0)
    verdicts = [e["gate"]["verdict"] for e in _events(repo) if e["kind"] == "gate"]
    assert verdicts == ["blocked"]
    assert gate["stages"][0]["status"] == "blocked"


def test_promote_of_blocked_verdict_is_refused_without_override(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    test_blocked_verdict_on_all_four_observation_shapes(repo, None)
    before = len(_events(repo))
    rc = dispatch(["evolve", "promote", "--candidate", "0", "--run", "r1"])
    assert rc == 1
    assert "--override" in capsys.readouterr().err
    assert len(_events(repo)) == before  # a refusal records nothing


def test_gate_pass_lifecycle_promote_then_rollback(repo: Path) -> None:
    naming = repo / ".context" / "conventions" / "naming.md"
    _harvest(repo)
    assert _diagnose(repo, [_candidate()]) == 0
    _stage(repo, 0, ".context/conventions/naming.md", "# naming\nnew content\n")

    # The targeted-pytest subset runs for real against an in-repo test file.
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_naming_seg.py").write_text(
        "def test_noop() -> None:\n    assert True\n", encoding="utf-8"
    )

    assert dispatch(["evolve", "apply", "--candidate", "0", "--run", "r1"]) == 0
    gate = _gate(repo, 0)
    assert gate["verdict"] == "pass"
    statuses = {s["name"]: s["status"] for s in gate["stages"]}
    assert statuses["pytest-subset"] == "pass"

    assert dispatch(["evolve", "promote", "--candidate", "0", "--run", "r1"]) == 0
    assert naming.read_text(encoding="utf-8") == "# naming\nnew content\n"

    assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 0
    assert naming.read_text(encoding="utf-8") == "# naming\nold content\n"

    kinds = [e["kind"] for e in _events(repo)]
    assert kinds == ["harvest", "diagnosis", "gate", "promote", "rollback"]
    promote = _events(repo)[3]
    assert promote["prediction"] == "naming stays stable"
    backup = repo / ".context" / "gc" / "evolve" / "r1" / "backup" / "0"
    assert (
        backup / ".context" / "conventions" / "naming.md"
    ).is_file()


def test_failed_pytest_subset_yields_fail_and_cannot_be_overridden(
    repo: Path,
) -> None:
    naming = repo / ".context" / "conventions" / "naming.md"
    _harvest(repo)
    assert _diagnose(repo, [_candidate()]) == 0
    _stage(repo, 0, ".context/conventions/naming.md", "# naming\nbroken\n")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_naming_seg.py").write_text(
        "def test_noop() -> None:\n    assert False\n", encoding="utf-8"
    )
    assert dispatch(["evolve", "apply", "--candidate", "0", "--run", "r1"]) == 0
    assert _gate(repo, 0)["verdict"] == "fail"
    rc = dispatch(
        [
            "evolve",
            "promote",
            "--candidate",
            "0",
            "--run",
            "r1",
            "--override",
            "not allowed on failures",
        ]
    )
    assert rc == 1
    assert naming.read_text(encoding="utf-8") == "# naming\nold content\n"


def test_promote_with_override_records_reason_in_jsonl(repo: Path) -> None:
    _seed_suite(repo)
    _harvest(repo)
    assert _diagnose(repo, [_candidate(".context/equipment-evals/gc.suite.json")]) == 0
    _stage(repo, 0, ".context/equipment-evals/gc.suite.json", '{"cases": []}')
    dispatch(["evolve", "apply", "--candidate", "0", "--run", "r1"])
    reason = "suite edit is content-neutral; reviewed by hand"
    rc = dispatch(
        [
            "evolve",
            "promote",
            "--candidate",
            "0",
            "--run",
            "r1",
            "--override",
            reason,
        ]
    )
    assert rc == 0
    promotes = [e for e in _events(repo) if e["kind"] == "promote"]
    assert len(promotes) == 1
    assert promotes[0]["outcome"]["override"] == reason


def test_discard_drops_staged_copy_and_records_event(repo: Path) -> None:
    _harvest(repo)
    assert _diagnose(repo, [_candidate()]) == 0
    _stage(repo, 0, ".context/conventions/naming.md", "# changed\n")
    staged = repo / ".context" / "gc" / "evolve" / "r1" / "staged" / "0"
    assert staged.is_dir()
    assert dispatch(["evolve", "discard", "--candidate", "0", "--run", "r1"]) == 0
    assert not staged.exists()
    assert _events(repo)[-1]["kind"] == "discard"
    assert (repo / ".context" / "conventions" / "naming.md").read_text(
        encoding="utf-8"
    ) == "# naming\nold content\n"


def test_out_of_range_candidate_is_a_usage_error(repo: Path) -> None:
    _harvest(repo)
    assert dispatch(["evolve", "apply", "--candidate", "7", "--run", "r1"]) == 2
