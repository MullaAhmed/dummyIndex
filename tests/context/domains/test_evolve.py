"""Tests for ``context/domains/evolve.py`` — the self-improvement loop domain.

Coverage: harvest parsers keep citations intact (audit findings, session-memory
corrections, reconcile deltas, transcript adoption misses with
projects-root-relative slug citations), candidate validation + the scope guard
(source code / spec bodies / loop state are denied, ≤5 targets), the gate's
per-stage shapes (the four rejected observation shapes block; an unmatched
suite records ``not_applicable`` honestly), tolerant JSONL reads, and the
prediction re-check (a flipped promote is flagged until rolled back).

Transcript scanning is pointed at a constructed corpus via ``projects_root``
— never at the machine's real ``~/.claude/projects``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.domains.evolve import (
    CANDIDATES_NAME,
    EVOLUTION_REL,
    OBSERVATIONS_NAME,
    Candidate,
    EvolveWarning,
    HarvestReport,
    check_predictions,
    harvest,
    load_candidates,
    load_events,
    next_event_id,
    record_event,
    run_gate,
    validate_candidate,
)
from tests.paths import FIXTURES_DIR

pytestmark = pytest.mark.unit

_EVOLVE_FIXTURES = FIXTURES_DIR / "evolve"


# ----- shared fixtures ----------------------------------------------------------


@pytest.fixture()
def ctx(tmp_path: Path) -> Path:
    """A minimal `.context/` with every evidence source the harvesters read."""
    context_dir = tmp_path / ".context"
    (context_dir / "audits" / "demo").mkdir(parents=True)
    shutil.copy(
        _EVOLVE_FIXTURES / "audit-report.md",
        context_dir / "audits" / "demo" / "report.md",
    )
    memory_dir = context_dir / "session-memory"
    memory_dir.mkdir()
    shutil.copy(_EVOLVE_FIXTURES / "session-now.md", memory_dir / "now.md")
    shutil.copy(_EVOLVE_FIXTURES / "session-recent.md", memory_dir / "recent.md")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "loader.py").write_text("x = 1\n", encoding="utf-8")
    return context_dir


def _valid_candidate(target: str = ".context/conventions/naming.md") -> dict:
    return {
        "target_file": target,
        "diagnosis": "tighten the naming rule",
        "evidence": ["audits/demo/report.md:L9"],
        "change_sketch": "rewrite section 2",
        "prediction": "no new loader findings next harvest",
    }


def _seed_conventions(tmp_path: Path, ctx: Path) -> None:
    (ctx / "conventions").mkdir(exist_ok=True)
    (ctx / "conventions" / "naming.md").write_text("# naming\n", encoding="utf-8")


def _seed_projects(tmp_path: Path) -> Path:
    """A constructed transcript corpus shaped like `~/.claude/projects`."""
    projects = tmp_path / "projects"
    session_dir = projects / "mnt-tmp-project"
    session_dir.mkdir(parents=True)
    shutil.copy(
        _EVOLVE_FIXTURES / "transcript.jsonl",
        session_dir / "abc123.jsonl",
    )
    return projects


# ----- harvest ------------------------------------------------------------------


def test_harvest_audit_findings_keep_citations(ctx: Path, tmp_path: Path) -> None:
    report = harvest(ctx, tmp_path, projects_root=tmp_path / "absent")
    findings = [i for i in report.items if i.kind == "audit_finding"]
    # The fixture's third bullet is refuted — dropped, never harvested.
    assert len(findings) == 2
    assert findings[0].citation == "audits/demo/report.md:L9"
    assert findings[0].source == "audits/demo"
    assert "src/loader.py:L40-L52" in findings[0].summary


def test_harvest_memory_corrections_only(ctx: Path, tmp_path: Path) -> None:
    # A section with no correction marker must not be harvested.
    now = ctx / "session-memory" / "now.md"
    now.write_text(
        now.read_text(encoding="utf-8") + "\n## 2026-08-22 — calm day\n\nNothing happened.\n",
        encoding="utf-8",
    )
    report = harvest(ctx, tmp_path, projects_root=tmp_path / "absent")
    corrections = [i for i in report.items if i.kind == "memory_correction"]
    assert {i.citation.split(":")[0] for i in corrections} == {
        "session-memory/now.md",
        "session-memory/recent.md",
    }
    assert all("calm day" not in i.summary for i in corrections)


def test_harvest_since_drops_older_dated_sections(ctx: Path, tmp_path: Path) -> None:
    report = harvest(
        ctx, tmp_path, projects_root=tmp_path / "absent", since="2026-08-15"
    )
    corrections = [
        i for i in report.items if i.kind == "memory_correction"
    ]
    assert [i.citation for i in corrections] == ["session-memory/now.md:L3"]


def test_harvest_transcript_hits_cite_relative_slugs(
    ctx: Path, tmp_path: Path
) -> None:
    projects = _seed_projects(tmp_path)
    report = harvest(ctx, tmp_path, projects_root=projects)
    misses = [i for i in report.items if i.kind == "adoption_miss"]
    assert len(misses) == 2  # HOW_TO_USE.md mention + manual /dummyindex-gc
    assert all(i.citation.startswith("projects/") for i in misses)
    assert misses[0].citation == (
        "projects/mnt-tmp-project/abc123.jsonl:L2"
    )
    serialized = json.dumps(report.to_dict())
    assert str(Path.home()) not in serialized


def test_harvest_report_round_trips_through_dict(ctx: Path, tmp_path: Path) -> None:
    report = harvest(ctx, tmp_path, projects_root=tmp_path / "absent")
    revived = HarvestReport.from_dict(report.to_dict())
    assert revived == report


# ----- candidate validation + scope guard ---------------------------------------


def test_validate_candidate_accepts_a_well_formed_candidate(
    ctx: Path, tmp_path: Path
) -> None:
    _seed_conventions(tmp_path, ctx)
    errors = validate_candidate(_valid_candidate(), ctx, project_root=tmp_path)
    assert errors == []


def test_validate_candidate_lists_every_missing_field() -> None:
    errors = validate_candidate({}, Path("."), project_root=Path("."))
    for field in ("target_file", "diagnosis", "evidence", "change_sketch", "prediction"):
        assert any(field in e for e in errors), (field, errors)


def test_scope_guard_rejects_source_code_target(ctx: Path, tmp_path: Path) -> None:
    errors = validate_candidate(
        _valid_candidate("dummyindex/context/drift.py"), ctx, project_root=tmp_path
    )
    assert any("may never be source code" in e for e in errors)


def test_scope_guard_rejects_feature_spec_bodies(ctx: Path, tmp_path: Path) -> None:
    errors = validate_candidate(
        _valid_candidate(".context/features/tree-enrich/spec.md"),
        ctx,
        project_root=tmp_path,
    )
    assert any("plans/reconcile" in e for e in errors)


def test_scope_guard_denies_the_loop_state_itself(
    ctx: Path, tmp_path: Path
) -> None:
    for denied in (".context/gc/evolution.jsonl", ".context/gc/state.json"):
        errors = validate_candidate(_valid_candidate(denied), ctx, project_root=tmp_path)
        assert any("denied" in e for e in errors), denied


def test_scope_guard_caps_targets_at_five(ctx: Path, tmp_path: Path) -> None:
    _seed_conventions(tmp_path, ctx)
    candidate = _valid_candidate(
        [f".context/conventions/n{i}.md" for i in range(6)]
    )
    errors = validate_candidate(candidate, ctx, project_root=tmp_path)
    assert any("at most 5 files" in e for e in errors)


def test_validate_candidate_requires_existing_citations(
    ctx: Path, tmp_path: Path
) -> None:
    _seed_conventions(tmp_path, ctx)
    candidate = _valid_candidate()
    candidate["evidence"] = ["conventions/naming.md:L1"]
    assert validate_candidate(candidate, ctx, project_root=tmp_path) == []
    candidate["evidence"] = ["conventions/absent.md:L1"]
    errors = validate_candidate(candidate, ctx, project_root=tmp_path)
    assert any("not found" in e for e in errors)


def test_validate_candidate_resolves_project_slugs_against_projects_root(
    ctx: Path, tmp_path: Path
) -> None:
    _seed_conventions(tmp_path, ctx)
    projects = _seed_projects(tmp_path)
    candidate = _valid_candidate()
    candidate["evidence"] = ["projects/mnt-tmp-project/abc123.jsonl:L2"]
    errors = validate_candidate(
        candidate, ctx, project_root=tmp_path, projects_root=projects
    )
    assert errors == []


def test_load_candidates_skips_corrupt_lines_with_warnings(
    ctx: Path, tmp_path: Path
) -> None:
    _seed_conventions(tmp_path, ctx)
    path = ctx / "scratch.jsonl"
    good = _valid_candidate()
    path.write_text(
        json.dumps(good) + "\n{not json}\n" + json.dumps({"target_file": 7}) + "\n",
        encoding="utf-8",
    )
    valid, invalid, warnings = load_candidates(path, ctx, project_root=tmp_path)
    assert len(valid) == 1 and isinstance(valid[0], Candidate)
    assert len(invalid) == 1  # structurally invalid, reported per line
    assert len(warnings) == 1  # the non-JSON line warns instead of failing


# ----- gate ---------------------------------------------------------------------


def _seed_suite(ctx: Path, cases: list[dict] | None = None) -> None:
    evals = ctx / "equipment-evals"
    evals.mkdir(exist_ok=True)
    suite_cases = cases if cases is not None else [
        {"case_id": "c1", "prompt": "gc me", "expects_trigger": True}
    ]
    (evals / "gc.suite.json").write_text(json.dumps({"cases": suite_cases}))


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / ".context" / "gc" / "evolve" / "r1"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _fake_runner(code: int, output: str = ""):
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        return code, output

    return runner, calls


_SKILL_TARGET = ("dummyindex/skills/gc/SKILL.md",)


def test_gate_without_suite_match_is_not_applicable(ctx: Path, tmp_path: Path) -> None:
    result = run_gate((".context/conventions/naming.md",), _run_dir(tmp_path), ctx, tmp_path)
    assert result.verdict == "pass"
    assert [s.status for s in result.stages] == [
        "not_applicable",
        "not_applicable",
        "not_applicable",
    ]


def test_gate_blocks_when_suite_matched_but_observations_absent(
    ctx: Path, tmp_path: Path
) -> None:
    _seed_suite(ctx)
    result = run_gate(_SKILL_TARGET, _run_dir(tmp_path), ctx, tmp_path)
    assert result.verdict == "blocked"
    assert result.stages[0].status == "blocked"


def _observations(run_dir: Path, payload: dict) -> None:
    (run_dir / OBSERVATIONS_NAME).write_text(json.dumps(payload), encoding="utf-8")


def test_gate_passes_on_perfect_observation_coverage(
    ctx: Path, tmp_path: Path
) -> None:
    _seed_suite(ctx)
    run_dir = _run_dir(tmp_path)
    _observations(run_dir, {"observations": [{"case_id": "c1", "fired": True}]})
    result = run_gate(_SKILL_TARGET, _run_dir(tmp_path), ctx, tmp_path)
    assert result.verdict == "pass"
    assert result.stages[0].status == "pass"


def test_gate_fails_on_misfire(ctx: Path, tmp_path: Path) -> None:
    _seed_suite(ctx)
    run_dir = _run_dir(tmp_path)
    _observations(run_dir, {"observations": [{"case_id": "c1", "fired": False}]})
    result = run_gate(_SKILL_TARGET, _run_dir(tmp_path), ctx, tmp_path)
    assert result.verdict == "fail"
    assert result.stages[0].status == "fail"


@pytest.mark.parametrize(
    "payload",
    [
        {"observations": []},  # partial: a case with no observation
        {
            "observations": [
                {"case_id": "c1", "fired": True},
                {"case_id": "c1", "fired": False},
            ]
        },  # duplicated judgment
        {"observations": [{"case_id": "zz", "fired": True}]},  # mismatched id
    ],
)
def test_gate_blocks_on_partial_duplicated_and_mismatched_shapes(
    ctx: Path, tmp_path: Path, payload: dict
) -> None:
    _seed_suite(ctx)
    run_dir = _run_dir(tmp_path)
    _observations(run_dir, payload)
    result = run_gate(_SKILL_TARGET, _run_dir(tmp_path), ctx, tmp_path)
    assert result.verdict == "blocked"
    assert result.stages[0].status == "blocked"


def test_pytest_stage_runs_matching_subset_or_records_not_applicable(
    tmp_path: Path,
) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_evolve_seg.py"
    test_file.write_text("def test_ok() -> None:\n    assert True\n", encoding="utf-8")

    runner, calls = _fake_runner(0, "1 passed")
    result = run_gate(
        ("dummyindex/skills/evolve/SKILL.md",),
        _run_dir(tmp_path),
        ctx,
        tmp_path,
        runner=runner,
    )
    assert result.stages[1].status == "pass"
    pytest_argv = calls[0]
    assert pytest_argv[1:3] == ["-m", "pytest"]
    assert "-q" in pytest_argv
    assert str(test_file.relative_to(tmp_path)) in pytest_argv

    # No test file matches the changed segments -> honest not_applicable.
    result = run_gate(("dummyindex/skills/nonexistent-tool/SKILL.md",), _run_dir(tmp_path), ctx, tmp_path)
    assert result.stages[1].status == "not_applicable"


def test_pytest_failure_fails_the_gate_and_usage_error_blocks(
    tmp_path: Path,
) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_evolve_seg.py").write_text(
        "def test_ok() -> None:\n    assert True\n", encoding="utf-8"
    )
    for code, expected in ((1, "fail"), (4, "blocked")):
        runner, _calls = _fake_runner(code, "boom")
        result = run_gate(
            ("dummyindex/skills/evolve/SKILL.md",),
            _run_dir(tmp_path),
            ctx,
            tmp_path,
            runner=runner,
        )
        assert result.stages[1].status == expected


def test_ruff_stage_only_applies_to_python_targets(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    runner, calls = _fake_runner(0)
    result = run_gate(("dummyindex/skills/gc/SKILL.md",), _run_dir(tmp_path), ctx, tmp_path, runner=runner)
    assert result.stages[2].status == "not_applicable"
    assert calls == []

    # A .py target can only reach the gate from packaged tooling paths; feed
    # the stage directly through a skills .py target to pin the argv contract.
    (tmp_path / "dummyindex" / "skills" / "tool").mkdir(parents=True)
    (tmp_path / "dummyindex" / "skills" / "tool" / "helper.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    result = run_gate(
        ("dummyindex/skills/tool/helper.py",),
        _run_dir(tmp_path),
        ctx,
        tmp_path,
        runner=_fake_runner(0)[0],
    )
    assert result.stages[2].status == "pass"


# ----- decision history + predictions -------------------------------------------


def test_record_and_read_events_round_trip(ctx: Path) -> None:
    record_event(ctx, {"kind": "promote", "run": "r1", "candidate": 0})
    record_event(ctx, {"kind": "rollback", "run": "r1", "candidate": 0})
    events, warnings = load_events(ctx)
    assert [e["kind"] for e in events] == ["promote", "rollback"]
    assert warnings == []
    assert next_event_id(ctx) == 3
    assert (ctx / EVOLUTION_REL).read_text(encoding="utf-8").endswith("\n")


def test_corrupt_jsonl_lines_are_skipped_with_warning(ctx: Path) -> None:
    record_event(ctx, {"kind": "harvest"})
    with (ctx / EVOLUTION_REL).open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    record_event(ctx, {"kind": "gate"})
    events, warnings = load_events(ctx)
    assert [e["kind"] for e in events] == ["harvest", "gate"]
    assert len(warnings) == 1
    assert isinstance(warnings[0], EvolveWarning)
    assert next_event_id(ctx) == 3


def test_flipped_prediction_is_flagged_by_next_harvest(
    ctx: Path, tmp_path: Path
) -> None:
    record_event(
        ctx,
        {
            "kind": "promote",
            "run": "r1",
            "candidate": 0,
            "target": ".context/conventions/naming.md",
            "evidence": ["audits/demo/report.md:L9"],
            "prediction": "loader findings stay fixed",
        },
    )
    fresh = harvest(ctx, tmp_path, projects_root=tmp_path / "absent")
    flags = check_predictions(ctx, fresh)
    assert len(flags) == 1
    assert flags[0].targets == (".context/conventions/naming.md",)
    # Both open fixture findings share the promoted evidence path.
    assert flags[0].matched_citations == (
        "audits/demo/report.md:L9",
        "audits/demo/report.md:L10",
    )


def test_rollback_and_supersede_close_open_predictions(
    ctx: Path, tmp_path: Path
) -> None:
    record_event(
        ctx,
        {
            "kind": "promote",
            "run": "r1",
            "candidate": 0,
            "target": ".context/conventions/naming.md",
            "evidence": ["audits/demo/report.md:L9"],
            "prediction": "p",
        },
    )
    fresh = harvest(ctx, tmp_path, projects_root=tmp_path / "absent")
    record_event(ctx, {"kind": "rollback", "run": "r1", "candidate": 0})
    assert check_predictions(ctx, fresh) == ()
    record_event(
        ctx,
        {
            "kind": "promote",
            "run": "r1",
            "candidate": 0,
            "target": ".context/conventions/naming.md",
            "evidence": [],
            "prediction": "",
        },
    )
    assert check_predictions(ctx, fresh) == ()


def test_predictions_file_never_written_for_missing_history(
    ctx: Path, tmp_path: Path
) -> None:
    assert not (ctx / CANDIDATES_NAME).exists()
    fresh = harvest(ctx, tmp_path, projects_root=tmp_path / "absent")
    assert check_predictions(ctx, fresh) == ()
