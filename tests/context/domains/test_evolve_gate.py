"""Snapshot, instruction-loading and generated-ownership regressions for evolve."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.domains.evolve_gate import (
    EvolveError,
    _working_inputs,
    check_receipt,
    run_gate,
    staged_files,
)

pytestmark = pytest.mark.integration


def _fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "project"
    target = "dummyindex/skills/example/SKILL.md"
    path = root / target
    path.parent.mkdir(parents=True)
    path.write_text("valid incumbent", encoding="utf-8")
    (root / "dummyindex/__init__.py").write_text("", encoding="utf-8")
    run = root / ".context/gc/evolve/r1"
    stage = run / "staged/0" / target
    stage.parent.mkdir(parents=True)
    stage.write_text("broken candidate", encoding="utf-8")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_guidance.py").write_text(
        "from pathlib import Path\n"
        "import dummyindex\n"
        "def test_guidance():\n"
        "    package = Path(dummyindex.__file__).parent\n"
        "    assert package == Path.cwd() / 'dummyindex'\n"
        "    assert 'broken' not in (package / 'skills/example/SKILL.md').read_text()\n",
        encoding="utf-8",
    )
    return root, run, target


def test_candidate_instructions_are_loaded_from_snapshot_package(
    tmp_path: Path,
) -> None:
    root, run, target = _fixture(tmp_path)
    result = run_gate(
        (target,), run, root / ".context", root, test_paths=("tests/test_guidance.py",)
    )
    assert [s.status for s in result.stages] == ["pass", "fail"]
    assert (root / target).read_text() == "valid incumbent"


def test_arms_share_clean_root_and_exclude_runtime_state(tmp_path: Path) -> None:
    root, run, target = _fixture(tmp_path)
    for relative in (".venv/secret", "node_modules/secret", ".context/cache/secret"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not an input", encoding="utf-8")
    roots: list[Path] = []
    contents: list[str] = []

    def execute(argv: list[str], cwd: Path) -> tuple[int, str]:
        roots.append(cwd)
        contents.append((cwd / target).read_text())
        assert not (cwd / "leftover").exists()
        assert not (cwd / ".venv").exists()
        assert not (cwd / "node_modules").exists()
        assert not (cwd / ".context/cache").exists()
        assert not (cwd / ".context/gc/evolve").exists()
        (cwd / "leftover").write_text("baseline side effect", encoding="utf-8")
        return 0, "passed"

    result = run_gate(
        (target,),
        run,
        root / ".context",
        root,
        test_paths=("tests/test_guidance.py",),
        runner=execute,
    )
    assert result.verdict == "pass"
    assert roots[0] == roots[1] != root
    assert contents == ["valid incumbent", "broken candidate"]


def test_git_inventory_reads_dirty_and_untracked_working_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "tracked.py").write_text("dirty working content", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("new working content", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("excluded by git", encoding="utf-8")
    monkeypatch.setattr(
        "dummyindex.context.domains.evolve_gate.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0], 0, b"tracked.py\0untracked.py\0", b""
        ),
    )
    assert _working_inputs(tmp_path) == {
        "tracked.py": b"dirty working content",
        "untracked.py": b"new working content",
    }


def test_linked_staged_file_is_rejected(tmp_path: Path) -> None:
    root, run, target = _fixture(tmp_path)
    stage = run / "staged/0" / target
    stage.unlink()
    try:
        stage.symlink_to(root / target)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(EvolveError, match="symlink"):
        staged_files(run, 0, (target,))


def test_explicit_verification_must_be_existing_project_test(tmp_path: Path) -> None:
    root, run, target = _fixture(tmp_path)
    with pytest.raises(EvolveError, match="verification"):
        run_gate((target,), run, root / ".context", root, test_paths=(target,))


def test_working_inventory_ignores_links_outside_project(tmp_path: Path) -> None:
    root, _, _ = _fixture(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = root / "external.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    assert "external.txt" not in _working_inputs(root)


def test_receipt_is_portable_data_without_environment_values(tmp_path: Path) -> None:
    root, run, target = _fixture(tmp_path)
    result = run_gate(
        (target,), run, root / ".context", root, runner=lambda *args: (0, "passed")
    )
    receipt = json.loads(result.receipt_json)
    assert len(receipt["profile"]["environment_sha256"]) == 64
    assert "PATH" not in receipt["profile"]


def test_baseline_assertion_failure_can_be_repaired_by_staged_guidance(
    tmp_path: Path,
) -> None:
    root, run, target = _fixture(tmp_path)
    (root / target).write_text("broken incumbent", encoding="utf-8")
    (run / "staged/0" / target).write_text("valid repair", encoding="utf-8")
    payload = {"target_file": target}
    result = run_gate(
        (target,),
        run,
        root / ".context",
        root,
        candidate_payload=payload,
        test_paths=("tests/test_guidance.py",),
    )
    assert [s.status for s in result.stages] == ["fail", "pass"]
    assert result.verdict == "pass"
    assert "baseline failed" in result.to_dict()["qualification"]
    check_receipt(result.to_dict(), (target,), run, 0, root, payload)


@pytest.mark.parametrize(
    "codes, verdict", [((4, 1), "fail"), ((4, 0), "blocked"), ((1, 4), "blocked")]
)
def test_candidate_failure_dominates_blocked_baseline_and_receipt_matches(
    tmp_path: Path,
    codes: tuple[int, int],
    verdict: str,
) -> None:
    root, run, target = _fixture(tmp_path)
    replies = iter(codes)
    payload = {"target_file": target}
    result = run_gate(
        (target,),
        run,
        root / ".context",
        root,
        candidate_payload=payload,
        test_paths=("tests/test_guidance.py",),
        runner=lambda *args: (next(replies), "result"),
    )
    assert result.verdict == verdict
    check_receipt(result.to_dict(), (target,), run, 0, root, payload)
