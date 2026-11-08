"""CLI lifecycle for ``dummyindex context evolve`` — one JSONL line per transition.

Harvest writes run artifacts + a `harvest` event; the sleep contract exits 0
having written nothing; diagnose validates candidates; apply tests exact staged
guidance; missing checks block; promote rejects stale receipts and incomplete
writes but records a given reason; rollback restores; discard drops. Each
transition appends one line to `.context/gc/evolution.jsonl`; pytest runs for real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch

pytestmark = pytest.mark.integration


# --- fixtures


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repo with `.context/`, isolated HOME + projects root."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    repo = tmp_path / "repo"
    ctx = repo / ".context"
    (ctx / "conventions").mkdir(parents=True)
    (ctx / "conventions" / "naming.md").write_text(
        "# naming\nold content\n", encoding="utf-8"
    )
    monkeypatch.chdir(repo)
    return repo


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
    path = staged / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _events(repo: Path) -> list[dict]:
    path = repo / ".context" / "gc" / "evolution.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _gate(repo: Path, index: int) -> dict:
    return json.loads(
        (repo / ".context" / "gc" / "evolve" / "r1" / f"gate-{index}.json").read_text(
            encoding="utf-8"
        )
    )


# --- harvest + sleep contract


def test_native_experiment_cli_resumes_without_external_command(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = repo / ".context/conventions/coding-practices.md"
    target.write_text("# Existing owner guidance\n", encoding="utf-8")
    cases = repo / "cases"
    cases.mkdir()
    for name in ("development", "heldout"):
        (cases / f"{name}.json").write_text(
            json.dumps({"task": name}), encoding="utf-8"
        )
    run = repo / ".context/gc/evolve/native"
    run.mkdir(parents=True)
    spec = run / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "execution": "native",
                "model": "fixed-host-contract-test",
                "rubric": "artifact-check-v1",
                "guidance": [{"path": ".context/conventions/coding-practices.md"}],
                "cases": [
                    {
                        "id": "development",
                        "path": "cases/development.json",
                        "split": "validation",
                    },
                    {"id": "heldout", "path": "cases/heldout.json", "split": "heldout"},
                ],
            }
        ),
        encoding="utf-8",
    )
    command = ["evolve", "experiment", "--run", "native", "--from-file"]
    assert dispatch([*command, str(spec)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["state"] == "awaiting_execute"
    execution = first["pending"]
    assert not (repo / execution["workspace"] / "cases/heldout.json").exists()

    assert dispatch([*command, str(spec)]) == 0
    assert json.loads(capsys.readouterr().out)["pending"] == execution
    response = run / "response.json"
    response.write_text(
        json.dumps(
            {
                "request_id": execution["request_id"],
                "result": {
                    "actor_id": "fixed-execution-contract-test",
                    "tokens": None,
                    "cost_usd": None,
                    "status": "completed",
                    "loaded": execution["guidance"],
                },
            }
        ),
        encoding="utf-8",
    )
    assert dispatch([*command, str(response)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["state"] == "awaiting_grade"
    assert second["pending"]["workspace"] != execution["workspace"]
    assert second["pending"]["request_id"] != execution["request_id"]
    assert target.read_text(encoding="utf-8") == "# Existing owner guidance\n"


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


# --- diagnose


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


def _check(repo: Path, target: str = ".context/conventions/naming.md") -> Path:
    path = repo / "tests" / "test_guidance.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "from pathlib import Path\n"
        "def test_guidance():\n"
        f"    text = Path({target!r}).read_text()\n"
        "    assert 'broken' not in text\n",
        encoding="utf-8",
    )
    return path


def _prepared(repo: Path, content: str = "# naming\nnew content\n") -> Path:
    run = _harvest(repo)
    assert _diagnose(repo, [_candidate()]) == 0
    _stage(repo, 0, ".context/conventions/naming.md", content)
    _check(repo)
    return run


def _apply(repo: Path) -> int:
    return dispatch(
        [
            "evolve",
            "apply",
            "--candidate",
            "0",
            "--run",
            "r1",
            "--tests",
            "tests/test_guidance.py",
            "--root",
            str(repo),
        ]
    )


def _promote(*, override: bool = False) -> int:
    args = ["evolve", "promote", "--candidate", "0", "--run", "r1"]
    return dispatch(args + (["--override", "manual decision"] if override else []))


def test_exact_candidate_breaks_check_while_incumbent_stays_unchanged(
    repo: Path,
) -> None:
    _prepared(repo, "# naming\nbroken\n")
    assert _apply(repo) == 0
    gate = _gate(repo, 0)
    assert [s["status"] for s in gate["stages"]] == ["pass", "fail"]
    assert gate["verdict"] == "fail"
    assert _promote(override=True) == 1
    assert "old content" in (repo / ".context/conventions/naming.md").read_text()


def test_gate_promote_rollback_uses_real_content_check(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepared(repo)
    # --root must work even when the caller's cwd is a different project.
    monkeypatch.chdir(repo.parent)
    assert _apply(repo) == 0
    monkeypatch.chdir(repo)
    assert _gate(repo, 0)["verdict"] == "pass"
    assert _promote() == 0
    assert "new content" in (repo / ".context/conventions/naming.md").read_text()
    assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 0
    assert "old content" in (repo / ".context/conventions/naming.md").read_text()
    assert [e["kind"] for e in _events(repo)] == [
        "harvest",
        "diagnosis",
        "gate",
        "promote",
        "rollback",
    ]
    assert _events(repo)[3]["outcome"]["qualification"] == "project_tests"


def test_missing_checks_blocks_but_explicit_manual_adoption_is_unmeasured(
    repo: Path,
) -> None:
    _harvest(repo)
    assert _diagnose(repo, [_candidate()]) == 0
    _stage(repo, 0, ".context/conventions/naming.md", "new")
    assert dispatch(["evolve", "apply", "--candidate", "0", "--run", "r1"]) == 0
    assert _gate(repo, 0)["verdict"] == "blocked"
    assert _promote() == 1
    assert _promote(override=True) == 0
    assert _events(repo)[-1]["outcome"]["qualification"] == "manual_unmeasured"


@pytest.mark.parametrize(
    "change", ["staged", "baseline", "candidate", "test", "config", "profile"]
)
def test_changed_qualification_inputs_refuse_promotion_even_with_override(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    run = _prepared(repo)
    assert _apply(repo) == 0
    if change == "staged":
        _stage(repo, 0, ".context/conventions/naming.md", "different staged content")
    elif change == "baseline":
        (repo / ".context/conventions/naming.md").write_text(
            "human edit", encoding="utf-8"
        )
    elif change == "candidate":
        candidate = _candidate()
        candidate["prediction"] = "a different prediction"
        (run / "candidates.jsonl").write_text(
            json.dumps(candidate) + "\n", encoding="utf-8"
        )
    elif change == "test":
        _check(repo).write_text(
            "def test_disabled():\n    assert True\n", encoding="utf-8"
        )
    elif change == "config":
        (repo / "pytest.ini").write_text("[pytest]\naddopts = -x\n", encoding="utf-8")
    else:
        monkeypatch.setenv("EVOLVE_TEST_PROFILE", "changed")
    before = (repo / ".context/conventions/naming.md").read_bytes()
    assert _promote(override=True) == 1
    assert (repo / ".context/conventions/naming.md").read_bytes() == before
    assert not (run / "backup").exists()


def _two_targets(repo: Path) -> tuple[Path, tuple[str, str]]:
    targets = (".context/conventions/a/rules.md", ".context/conventions/b/rules.md")
    for number, target in enumerate(targets):
        path = repo / target
        path.parent.mkdir(parents=True)
        path.write_text(f"old {number}", encoding="utf-8")
    run = _harvest(repo)
    candidate = _candidate()
    candidate["target_file"] = list(targets)
    assert _diagnose(repo, [candidate]) == 0
    for number, target in enumerate(targets):
        _stage(repo, 0, target, f"new {number}")
    _check(repo)
    return run, targets


def test_same_basename_targets_keep_distinct_content(repo: Path) -> None:
    _, targets = _two_targets(repo)
    assert _apply(repo) == 0
    assert _promote() == 0
    assert [(repo / t).read_text() for t in targets] == ["new 0", "new 1"]


def test_second_write_failure_restores_all_targets_and_keeps_journal(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dummyindex.context.domains import evolve_promotion

    run, targets = _two_targets(repo)
    assert _apply(repo) == 0
    original = evolve_promotion._atomic_bytes
    failed = False

    def fail_second(path: Path, content: bytes) -> None:
        nonlocal failed
        if path == repo / targets[1] and not failed:
            failed = True
            raise OSError("second target write failed")
        original(path, content)

    monkeypatch.setattr(evolve_promotion, "_atomic_bytes", fail_second)
    assert _promote() == 1
    assert [(repo / t).read_text() for t in targets] == ["old 0", "old 1"]
    journal = json.loads((run / "backup/0/transaction.json").read_text())
    assert journal["state"] == "rolled_back"
    assert all(e["kind"] != "promote" for e in _events(repo))


def test_ambiguous_legacy_basename_staging_is_rejected(repo: Path) -> None:
    run, targets = _two_targets(repo)
    for target in targets:
        (run / "staged/0" / target).unlink()
    (run / "staged/0/rules.md").write_text("aliased content", encoding="utf-8")
    assert _apply(repo) == 2
    assert [(repo / t).read_text() for t in targets] == ["old 0", "old 1"]


def test_unique_legacy_basename_staging_still_works(repo: Path) -> None:
    run = _prepared(repo)
    canonical = run / "staged/0/.context/conventions/naming.md"
    canonical.replace(run / "staged/0/naming.md")
    assert _apply(repo) == 0
    assert _promote() == 0


def test_rollback_refuses_to_overwrite_later_human_edit(repo: Path) -> None:
    _prepared(repo)
    assert _apply(repo) == 0
    assert _promote() == 0
    target = repo / ".context/conventions/naming.md"
    target.write_text("human edit after promotion", encoding="utf-8")
    assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 1
    assert target.read_text() == "human edit after promotion"


def _managed_candidate(repo: Path) -> tuple[Path, str, bytes, bytes]:
    assert (
        dispatch(["equip", "apply", "--root", str(repo), "--platform", "agents"]) == 0
    )
    manifest_path = repo / ".context/equipment.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = next(
        i
        for i in raw["items"]
        if i["source"] == "generated" and i["path"].startswith(".context/equipment/")
    )
    target = record["path"]
    record["future_field"] = "preserve this record metadata"
    raw["future_manifest_field"] = {"preserved": True}
    manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    original_body = (repo / target).read_bytes()
    original_manifest = manifest_path.read_bytes()
    run = _harvest(repo)
    assert _diagnose(repo, [_candidate(target)]) == 0
    _stage(
        repo,
        0,
        target,
        original_body.decode("utf-8") + "\nLearned rule from evidence.\n",
    )
    _check(repo, target)
    return run, target, original_body, original_manifest


def test_managed_promotion_rebaselines_and_apply_refresh_preserve_learning(
    repo: Path,
) -> None:
    from dummyindex.context.domains.equip import ItemState, read_manifest
    from dummyindex.context.domains.equip.lifecycle.status import (
        classify_item,
        is_evolved,
    )

    run, target, _, _ = _managed_candidate(repo)
    assert _apply(repo) == 0
    staged = (run / "staged/0" / target).read_bytes()
    assert b"1.0.1" in staged
    assert _promote() == 0
    assert (repo / target).read_bytes() == staged
    item = next(i for i in read_manifest(repo / ".context").items if i.path == target)
    assert item.version == "1.0.1" and is_evolved(item)
    assert classify_item(repo, item) is ItemState.PRISTINE
    raw = json.loads((repo / ".context/equipment.json").read_text(encoding="utf-8"))
    assert raw["future_manifest_field"] == {"preserved": True}
    assert (
        next(i for i in raw["items"] if i["path"] == target)["future_field"]
        == "preserve this record metadata"
    )
    assert (
        dispatch(["equip", "apply", "--root", str(repo), "--platform", "agents"]) == 0
    )
    assert dispatch(["equip", "refresh", "--root", str(repo)]) == 0
    assert (repo / target).read_bytes() == staged
    # Receipt state covers the derived manifest as well as the declared body.
    journal = json.loads((run / "backup/0/transaction.json").read_text())
    assert journal["targets"] == [target, ".context/equipment.json"]


def test_managed_rollback_restores_body_and_original_manifest(repo: Path) -> None:
    _, target, original_body, original_manifest = _managed_candidate(repo)
    assert _apply(repo) == 0
    assert _promote() == 0
    assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 0
    assert (repo / target).read_bytes() == original_body
    assert (repo / ".context/equipment.json").read_bytes() == original_manifest


def test_failed_managed_manifest_write_restores_body_and_manifest(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dummyindex.context.domains import evolve_promotion

    run, target, original_body, original_manifest = _managed_candidate(repo)
    assert _apply(repo) == 0
    original = evolve_promotion._atomic_bytes
    failed = False

    def fail_manifest(path: Path, content: bytes) -> None:
        nonlocal failed
        if path == repo / ".context/equipment.json" and not failed:
            failed = True
            raise OSError("manifest write failed")
        original(path, content)

    monkeypatch.setattr(evolve_promotion, "_atomic_bytes", fail_manifest)
    assert _promote() == 1
    assert (repo / target).read_bytes() == original_body
    assert (repo / ".context/equipment.json").read_bytes() == original_manifest
    assert (
        json.loads((run / "backup/0/transaction.json").read_text())["state"]
        == "rolled_back"
    )


def test_mixed_explicit_manifest_and_managed_body_are_refused(repo: Path) -> None:
    _, target, original_body, original_manifest = _managed_candidate(repo)
    candidate = _candidate()
    candidate["target_file"] = [target, ".context/equipment.json"]
    assert _diagnose(repo, [candidate]) == 0
    _stage(repo, 1, target, original_body.decode("utf-8") + "\nlearned\n")
    _stage(repo, 1, ".context/equipment.json", original_manifest.decode("utf-8"))
    assert (
        dispatch(
            [
                "evolve",
                "apply",
                "--candidate",
                "1",
                "--run",
                "r1",
                "--tests",
                "tests/test_guidance.py",
            ]
        )
        == 2
    )
    assert (repo / target).read_bytes() == original_body
    assert (repo / ".context/equipment.json").read_bytes() == original_manifest


def test_prepared_journal_recovers_mixed_before_and_after_files(repo: Path) -> None:
    run, targets = _two_targets(repo)
    assert _apply(repo) == 0
    assert _promote() == 0
    journal_path = run / "backup/0/transaction.json"
    journal = json.loads(journal_path.read_text())
    journal["state"] = "prepared"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    # Crash after target 0: target 1 still has its original content.
    (repo / targets[1]).write_text("old 1", encoding="utf-8")
    assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 0
    assert [(repo / t).read_text() for t in targets] == ["old 0", "old 1"]


@pytest.mark.parametrize("human_edit", [False, True])
def test_interrupted_rollback_can_resume_without_overwriting_human_edits(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    human_edit: bool,
) -> None:
    from dummyindex.context.domains import evolve_promotion

    run, targets = _two_targets(repo)
    assert _apply(repo) == 0
    assert _promote() == 0
    original = evolve_promotion._atomic_bytes

    def interrupt_after_first_restoration(path: Path, content: bytes) -> None:
        original(path, content)
        if path == repo / targets[0]:
            raise KeyboardInterrupt("interrupted after first restoration")

    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            evolve_promotion, "_atomic_bytes", interrupt_after_first_restoration
        )
        with pytest.raises(KeyboardInterrupt, match="first restoration"):
            dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"])

    assert [(repo / t).read_text() for t in targets] == ["old 0", "new 1"]
    journal_path = run / "backup/0/transaction.json"
    assert json.loads(journal_path.read_text())["state"] == "recovery_required"
    if human_edit:
        (repo / targets[1]).write_text("human edit", encoding="utf-8")
        assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 1
        assert [(repo / t).read_text() for t in targets] == ["old 0", "human edit"]
    else:
        assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 0
        assert [(repo / t).read_text() for t in targets] == ["old 0", "old 1"]
        assert json.loads(journal_path.read_text())["state"] == "rolled_back"


def test_busy_project_writer_refuses_promote_and_rollback(repo: Path) -> None:
    from dummyindex.context.domains.evolve_promotion import project_lock

    run = _prepared(repo)
    assert _apply(repo) == 0
    with project_lock(repo):
        assert _promote() == 1
    assert not (run / "backup").exists()
    assert _promote() == 0
    with project_lock(repo):
        assert dispatch(["evolve", "rollback", "--candidate", "0", "--run", "r1"]) == 1
    assert "new content" in (repo / ".context/conventions/naming.md").read_text()


def test_failed_candidate_cannot_be_overridden_when_baseline_is_unavailable(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dummyindex.context.domains import evolve_gate

    _prepared(repo)
    codes = iter((4, 1))
    monkeypatch.setattr(
        evolve_gate, "_default_runner", lambda *args: (next(codes), "result")
    )
    assert _apply(repo) == 0
    assert _gate(repo, 0)["verdict"] == "fail"
    assert _promote(override=True) == 1
