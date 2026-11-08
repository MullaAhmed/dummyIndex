"""Closeout preserves accepted knowledge without retaining disposable plans."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.buildloop import parse_checklist
from dummyindex.context.domains.evolve_learning import (
    enqueue_learning,
    prepare_learning,
    read_event,
    run_learning,
)
from dummyindex.context.domains.gc import CandidateKind, GcTargetError, delete_workspace
from dummyindex.context.domains.proposals import CloseoutError, closeout_workspace
from dummyindex.context.domains.proposals.closeout import learning_exit_code
from dummyindex.context.domains.proposals.retirement import (
    ADMIN_FILES,
    digest,
    durable_references,
    retirement_block,
    workspace_inventory,
)


@pytest.fixture(autouse=True)
def _local_only(monkeypatch):
    monkeypatch.setattr(
        "dummyindex.context.domains.proposals.closeout.head_commit",
        lambda _root: "revision-one",
    )
    monkeypatch.setattr(
        "dummyindex.context.domains.gc.delete._is_tracked", lambda *_args: True
    )


def _workspace(tmp_path: Path, *, kind="proposal") -> tuple[Path, Path]:
    context = tmp_path / ".context"
    workspace = context / ("proposals" if kind == "proposal" else "audits") / "work"
    workspace.mkdir(parents=True)
    if kind == "proposal":
        (workspace / "proposal.json").write_text(
            json.dumps({"slug": "work", "status": "in_progress"}), encoding="utf-8"
        )
        (workspace / "checklist.md").write_text(
            "- [x] Implement the change\n", encoding="utf-8"
        )
    (context / "conventions").mkdir()
    (context / "conventions" / "coding.md").write_text(
        "# Existing conventions\n", encoding="utf-8"
    )
    (workspace / "lesson.md").write_text("Use the shared parser.\n", encoding="utf-8")
    return context, workspace


def _manifest(workspace: Path, *, transfers=None) -> dict:
    transfers = (
        transfers
        if transfers is not None
        else [
            {
                "kind": "lesson",
                "source": "lesson.md",
                "target": ".context/conventions/coding.md",
            }
        ]
    )
    inventory = workspace_inventory(workspace)
    return {
        "state": "implemented",
        "source_commit": "revision-one",
        "reviewed_files": inventory,
        "transfers": transfers,
        "discarded": {
            name: "No remaining durable information after review"
            for name in inventory
            if name not in ADMIN_FILES and name not in {r["source"] for r in transfers}
        },
    }


def _packaged_audit_manifest(
    tmp_path: Path,
    workspace: Path,
    reflection: dict | None,
    discarded: dict,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    companion = (
        Path(__file__).resolve().parents[3] / "dummyindex/skills/audit/closeout.md"
    )
    text = companion.read_text(encoding="utf-8")
    recipes = re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)
    assert len(recipes) == 1
    script = tmp_path / "prepare-audit-closeout.py"
    script.write_text(recipes[0], encoding="utf-8")
    input_path = tmp_path / "audit-input.json"
    manifest_path = tmp_path / "generated-closeout.json"
    input_path.write_text(
        json.dumps({"learning_reflection": reflection, "discarded": discarded}),
        encoding="utf-8",
    )
    args = [
        sys.executable,
        "-I",
        str(script),
        workspace.relative_to(tmp_path).as_posix(),
        input_path.relative_to(tmp_path).as_posix(),
        manifest_path.relative_to(tmp_path).as_posix(),
    ]
    result = subprocess.run(
        args, cwd=tmp_path, text=True, capture_output=True, check=False
    )
    return result, manifest_path


@pytest.mark.unit
def test_transfer_live_verification_and_retirement_preserve_durable_work(
    tmp_path: Path,
) -> None:
    context, workspace = _workspace(tmp_path)
    checklist = workspace / "checklist.md"
    checklist.write_text(
        checklist.read_text() + "- [ ] Verify the deployed environment\n",
        encoding="utf-8",
    )
    (workspace / "fixture.json").write_text('{"case": 1}\n', encoding="utf-8")
    manifest = _manifest(
        workspace,
        transfers=[
            {
                "kind": "lesson",
                "source": "lesson.md",
                "target": ".context/conventions/coding.md",
            },
            {
                "kind": "fixture",
                "source": "fixture.json",
                "target": "tests/fixtures/parser-case.json",
            },
        ],
    )
    manifest["pending_verification"] = [
        {
            "item_id": parse_checklist(checklist)[1].item_id,
            "description": "Verify the deployed environment",
        }
    ]

    receipt = closeout_workspace(context, "proposal", "work", manifest)

    assert receipt["state"] == "implemented"
    assert len(receipt["pending_verification"]) == 1
    assert json.loads((workspace / "proposal.json").read_text())["status"] == "done"
    assert all(item.done for item in parse_checklist(checklist))
    assert "deployed" not in checklist.read_text()
    convention = context / "conventions" / "coding.md"
    assert "Use the shared parser." in convention.read_text()
    convention.write_text(
        convention.read_text() + "\nAn unrelated new rule.\n", encoding="utf-8"
    )
    assert retirement_block(context, workspace, kind="proposal") is None
    assert delete_workspace(context, kind=CandidateKind.PROPOSAL, slug="work").deleted
    assert convention.exists()
    assert (tmp_path / "tests/fixtures/parser-case.json").exists()
    assert (context / "gc/closeouts/proposal-work.json").exists()


@pytest.mark.unit
def test_audit_knowledge_requires_same_transfer_before_retirement(
    tmp_path: Path,
) -> None:
    context, workspace = _workspace(tmp_path, kind="audit")
    with pytest.raises(GcTargetError, match="knowledge review"):
        delete_workspace(context, kind=CandidateKind.AUDIT, slug="work")
    closeout_workspace(context, "audit", "work", _manifest(workspace))
    assert retirement_block(context, workspace, kind="audit") is None


@pytest.mark.integration
@pytest.mark.parametrize("with_check", [True, False])
def test_audit_reflection_uses_managed_learning_gate_and_is_idempotent(
    tmp_path: Path, with_check: bool, capsys
) -> None:
    context, workspace = _workspace(tmp_path, kind="audit")
    (workspace / "report.md").write_text(
        "Confirmed: parser strips surrounding whitespace.\n", encoding="utf-8"
    )
    (workspace / "findings").mkdir()
    (workspace / "findings/reviewer.md").write_text(
        "The parser contract is exercised by the project test.\n", encoding="utf-8"
    )
    (workspace / "catalog.json").write_text('{"personas": []}\n', encoding="utf-8")
    source = tmp_path / "src/parser.py"
    source.parent.mkdir()
    source.write_text(
        'def parse_token(value):\n    """Strip surrounding whitespace from a token."""\n    return value.strip()\n',
        encoding="utf-8",
    )
    test_path = tmp_path / "tests/test_parser.py"
    test_path.parent.mkdir()
    test_path.write_text(
        "from src.parser import parse_token\n\n"
        "def test_parser_contract():\n"
        "    assert parse_token(' x ') == 'x'\n",
        encoding="utf-8",
    )
    convention = context / "conventions/coding.md"
    owner_bytes = convention.read_bytes()
    source_bytes = source.read_bytes()
    report_bytes = (workspace / "report.md").read_bytes()
    reflection = {
        "verified": True,
        "target": ".context/conventions/coding.md",
        "rule_id": "parser-normalization",
        "body": (
            "Use parse_token for whitespace normalization; see "
            "src/parser.py:L1-L3 and tests/test_parser.py:L1-L4."
        ),
        "expected_sha256": digest(owner_bytes).upper(),
        "sources": ["src/parser.py", "tests/test_parser.py"],
        "tests": ["tests/test_parser.py"] if with_check else [],
        "supersedes": [],
    }
    discarded = {
        "lesson.md": "Reviewed scratch lesson; durable content is represented by the verified rule",
        "report.md": "Final report retained for the user; durable rule cites source and test",
        "findings/reviewer.md": "Reviewed temporary workpaper; no separate durable finding",
    }
    generated, manifest_path = _packaged_audit_manifest(
        tmp_path, workspace, reflection, discarded
    )
    assert generated.returncode != 0
    assert "every workspace file its own nonempty review reason" in generated.stderr
    assert not manifest_path.exists()
    discarded["catalog.json"] = "Reviewed persona catalog; no durable lesson"
    generated, manifest_path = _packaged_audit_manifest(
        tmp_path, workspace, reflection, discarded
    )
    assert generated.returncode == 0, generated.stderr
    prepared_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert prepared_manifest["state"] == "implemented"
    assert prepared_manifest["transfers"] == []
    assert list(prepared_manifest["reviewed_files"]) == sorted(
        prepared_manifest["reviewed_files"]
    )
    assert all(
        value == value.lower() for value in prepared_manifest["reviewed_files"].values()
    )
    assert prepared_manifest["learning_reflection"]["expected_sha256"] == digest(
        owner_bytes
    )
    before_inventory = workspace_inventory(workspace)

    closeout_args = [
        "gc",
        "closeout",
        "--kind",
        "audit",
        "--slug",
        "work",
        "--manifest",
        str(manifest_path),
        "--root",
        str(tmp_path),
        "--json",
    ]
    assert dispatch(closeout_args) == 0
    first = json.loads(capsys.readouterr().out)

    if with_check:
        assert first["learning"]["state"] == "applied"
        revised = convention.read_bytes()
        assert revised.startswith(owner_bytes)
        from dummyindex.context.domains.living_rules import rules_in

        managed = rules_in(revised.decode("utf-8"))
        assert len(managed) == 1
        assert managed[0]["id"] == "parser-normalization"
        assert managed[0]["sources"]["src/parser.py"] == digest(source_bytes)
        assert "audit-work" in json.dumps(managed[0]["evidence"])
    else:
        assert first["learning"]["state"] == "evaluated"
        assert first["learning"]["verdict"] == "blocked"
        assert convention.read_bytes() == owner_bytes

    assert dispatch(closeout_args) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["learning"] == first["learning"]
    assert workspace_inventory(workspace) == before_inventory
    assert source.read_bytes() == source_bytes
    assert (workspace / "report.md").read_bytes() == report_bytes
    assert convention.read_bytes() == (revised if with_check else owner_bytes)


@pytest.mark.unit
def test_stale_review_missing_assets_and_unevaluated_claims_fail_without_writes(
    tmp_path: Path,
) -> None:
    context, workspace = _workspace(tmp_path)
    manifest = _manifest(workspace)
    (workspace / "new-asset.txt").write_text("unique evidence", encoding="utf-8")
    with pytest.raises(CloseoutError, match="reviewed_files"):
        closeout_workspace(context, "proposal", "work", manifest)
    manifest["reviewed_files"] = workspace_inventory(workspace)
    with pytest.raises(CloseoutError, match="unreviewed knowledge"):
        closeout_workspace(context, "proposal", "work", manifest)
    manifest["discarded"]["new-asset.txt"] = "Superseded by the accepted lesson"
    manifest["state"] = "verified"
    with pytest.raises(CloseoutError, match="outcome evidence"):
        closeout_workspace(context, "proposal", "work", manifest)
    assert (context / "conventions/coding.md").read_text() == "# Existing conventions\n"
    assert (
        json.loads((workspace / "proposal.json").read_text())["status"] == "in_progress"
    )


@pytest.mark.unit
def test_inbound_durable_dependencies_and_source_escape_fail_closed(
    tmp_path: Path,
) -> None:
    context, workspace = _workspace(tmp_path)
    (tmp_path / "tests").mkdir()
    dependent = tmp_path / "tests/test_parser.py"
    dependent.write_text(
        'fixture = ".context/proposals/work/fixture.json"\n', encoding="utf-8"
    )
    with pytest.raises(CloseoutError, match="durable references"):
        closeout_workspace(context, "proposal", "work", _manifest(workspace))
    dependent.unlink()
    manifest = _manifest(workspace)
    manifest["transfers"][0]["source"] = "../../outside.md"
    with pytest.raises(CloseoutError, match="escapes allowed root"):
        closeout_workspace(context, "proposal", "work", manifest)
    assert workspace.exists()


@pytest.mark.unit
def test_changed_accepted_unit_requires_explicit_supersession(tmp_path: Path) -> None:
    context, workspace = _workspace(tmp_path)
    receipt = closeout_workspace(context, "proposal", "work", _manifest(workspace))
    convention = context / "conventions/coding.md"
    convention.write_text("# Current\nUse the replacement parser.\n", encoding="utf-8")
    assert "accepted knowledge" in retirement_block(context, workspace, kind="proposal")
    manifest = _manifest(workspace, transfers=[])
    manifest["superseded"] = {
        receipt["transfers"][0]["id"]: "Replaced with the new parser contract"
    }
    closeout_workspace(context, "proposal", "work", manifest)
    assert retirement_block(context, workspace, kind="proposal") is None


@pytest.mark.unit
@pytest.mark.parametrize("explicit_pending", [False, True])
def test_reclose_preserves_moved_live_checks_through_gc(
    tmp_path: Path, explicit_pending: bool
) -> None:
    context, workspace = _workspace(tmp_path)
    checklist = workspace / "checklist.md"
    checklist.write_text(
        checklist.read_text() + "- [ ] Verify deployed parser\n", encoding="utf-8"
    )
    pending = {
        "task_id": parse_checklist(checklist)[1].item_id,
        "description": "Verify deployed parser",
    }
    manifest = _manifest(workspace)
    manifest["pending_verification"] = [pending]
    first = closeout_workspace(context, "proposal", "work", manifest)
    assert "Verify deployed parser" not in checklist.read_text()
    followup = _manifest(workspace)
    if explicit_pending:
        followup["pending_verification"] = [pending]
    second = closeout_workspace(context, "proposal", "work", followup)
    assert second["pending_verification"] == first["pending_verification"]
    assert retirement_block(context, workspace, kind="proposal") is None
    delete_workspace(context, kind=CandidateKind.PROPOSAL, slug="work")
    durable = json.loads((context / "gc/closeouts/proposal-work.json").read_text())
    assert durable["pending_verification"] == first["pending_verification"]


@pytest.mark.unit
@pytest.mark.parametrize("resolution_state", ["verified", "discarded"])
def test_pending_check_resolution_requires_reason_and_durable_evidence(
    tmp_path: Path,
    resolution_state: str,
) -> None:
    context, workspace = _workspace(tmp_path)
    manifest = _manifest(workspace)
    manifest["pending_verification"] = [{"description": "Verify deployed parser"}]
    first = closeout_workspace(context, "proposal", "work", manifest)
    identity = first["pending_verification"][0]["verification_id"]
    followup = _manifest(workspace)
    followup["pending_verification"] = []
    assert (
        closeout_workspace(context, "proposal", "work", followup)[
            "pending_verification"
        ]
        == first["pending_verification"]
    )
    followup = _manifest(workspace)
    followup["resolved_verification"] = {
        identity: {"state": resolution_state, "reason": "Deployment regression passed"}
    }
    with pytest.raises(CloseoutError, match="durable evidence"):
        closeout_workspace(context, "proposal", "work", followup)
    evidence = tmp_path / "deployment-verification.txt"
    evidence.write_text("Deployed parser regression passed.\n", encoding="utf-8")
    resolution = followup["resolved_verification"][identity]
    resolution["evidence"] = [
        {"path": evidence.name, "sha256": digest(evidence.read_bytes())}
    ]
    resolution["reason"] = ""
    with pytest.raises(CloseoutError, match="and a reason"):
        closeout_workspace(context, "proposal", "work", followup)
    resolution["reason"] = "Deployment regression passed"
    final = closeout_workspace(context, "proposal", "work", followup)
    assert final["pending_verification"] == []
    assert (
        final["resolved_verification"][identity]["check"]
        == first["pending_verification"][0]
    )
    assert retirement_block(context, workspace, kind="proposal") is None
    evidence.write_text("Different deployment result.\n", encoding="utf-8")
    assert "outcome evidence" in retirement_block(context, workspace, kind="proposal")


@pytest.mark.unit
@pytest.mark.parametrize(
    "evidence_path",
    [
        ".context/cache/outcome.json",
        ".context/proposals//work/outcome.json",
        ".context/audits//other/outcome.json",
    ],
)
def test_closeout_outcome_evidence_rejects_resolved_ephemeral_paths(
    tmp_path: Path, evidence_path: str
) -> None:
    context, workspace = _workspace(tmp_path)
    evidence = tmp_path / evidence_path
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('{"passed": true}\n', encoding="utf-8")
    manifest = _manifest(workspace)
    manifest["state"] = "verified"
    manifest["evidence"] = [
        {"path": evidence_path, "sha256": digest(evidence.read_bytes())}
    ]
    with pytest.raises(CloseoutError, match="disposable"):
        closeout_workspace(context, "proposal", "work", manifest)
    assert not (context / "gc/closeouts/proposal-work.json").exists()
    assert (context / "conventions/coding.md").read_text() == "# Existing conventions\n"


@pytest.mark.unit
def test_gc_rechecks_durable_closeout_outcome_hash(tmp_path: Path) -> None:
    context, workspace = _workspace(tmp_path)
    evidence = tmp_path / "verification.json"
    evidence.write_text('{"passed": true}\n', encoding="utf-8")
    manifest = _manifest(workspace)
    manifest["state"] = "verified"
    manifest["evidence"] = [
        {"path": evidence.name, "sha256": digest(evidence.read_bytes())}
    ]
    closeout_workspace(context, "proposal", "work", manifest)
    assert retirement_block(context, workspace, kind="proposal") is None
    evidence.write_text('{"passed": false}\n', encoding="utf-8")
    assert "outcome evidence" in retirement_block(context, workspace, kind="proposal")
    with pytest.raises(GcTargetError, match="outcome evidence"):
        delete_workspace(context, kind=CandidateKind.PROPOSAL, slug="work")


@pytest.mark.unit
def test_accepted_unit_id_cannot_replace_prior_identity(tmp_path: Path) -> None:
    context, workspace = _workspace(tmp_path, kind="audit")
    manifest = _manifest(workspace)
    manifest["transfers"][0]["id"] = "lesson-one"
    closeout_workspace(context, "audit", "work", manifest)
    convention = context / "conventions/coding.md"
    convention.write_text("# Current conventions\n", encoding="utf-8")
    (workspace / "lesson.md").write_text(
        "Use the replacement parser.\n", encoding="utf-8"
    )
    followup = _manifest(workspace)
    followup["transfers"][0]["id"] = "lesson-one"
    with pytest.raises(CloseoutError, match="ID cannot be rebound"):
        closeout_workspace(context, "audit", "work", followup)
    assert retirement_block(context, workspace, kind="audit") is not None
    followup["transfers"][0]["id"] = "lesson-two"
    with pytest.raises(CloseoutError, match="prior accepted unit is missing"):
        closeout_workspace(context, "audit", "work", followup)
    followup["superseded"] = {"lesson-one": "Replaced by the new parser contract"}
    final = closeout_workspace(context, "audit", "work", followup)
    assert {unit["id"] for unit in final["transfers"]} == {"lesson-one", "lesson-two"}
    assert retirement_block(context, workspace, kind="audit") is None


@pytest.mark.unit
def test_second_write_failure_restores_preexisting_destination(
    tmp_path: Path, monkeypatch
) -> None:
    import importlib

    module = importlib.import_module("dummyindex.context.domains.proposals.closeout")
    context, workspace = _workspace(tmp_path, kind="audit")
    original = module._replace_bytes
    calls = 0

    def failing(path, data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected failure")
        return original(path, data)

    monkeypatch.setattr(module, "_replace_bytes", failing)
    with pytest.raises(CloseoutError, match="injected failure"):
        closeout_workspace(context, "audit", "work", _manifest(workspace))
    assert (context / "conventions/coding.md").read_text() == "# Existing conventions\n"
    assert not (context / "gc/closeouts/audit-work.json").exists()


@pytest.mark.unit
def test_interruption_before_receipt_protects_even_metadata_only_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    import importlib

    module = importlib.import_module("dummyindex.context.domains.proposals.closeout")
    context, workspace = _workspace(tmp_path)
    (workspace / "lesson.md").unlink()
    checklist = workspace / "checklist.md"
    checklist.write_text("- [x] Implement\n- [ ] Verify deployment\n", encoding="utf-8")
    manifest = _manifest(workspace, transfers=[])
    manifest["pending_verification"] = [
        {
            "task_id": parse_checklist(checklist)[1].item_id,
            "description": "Verify deployment",
        }
    ]
    original = module._replace_bytes
    calls = 0

    def interrupted(path, data):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise KeyboardInterrupt("simulated process interruption")
        original(path, data)

    monkeypatch.setattr(module, "_replace_bytes", interrupted)
    with pytest.raises(KeyboardInterrupt):
        closeout_workspace(context, "proposal", "work", manifest)
    assert json.loads((workspace / "proposal.json").read_text())["status"] == "done"
    assert "interrupted closeout" in retirement_block(
        context, workspace, kind="proposal"
    )
    monkeypatch.setattr(module, "_replace_bytes", original)
    resumed = _manifest(workspace, transfers=[])
    resumed["pending_verification"] = manifest["pending_verification"]
    resumed["resume_interrupted"] = True
    closeout_workspace(context, "proposal", "work", resumed)
    assert retirement_block(context, workspace, kind="proposal") is None


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["proposal", "audit"])
def test_closeout_cli_uses_the_same_reviewed_receipt(tmp_path: Path, kind: str) -> None:
    context, workspace = _workspace(tmp_path, kind=kind)
    manifest = tmp_path / "closeout-input.json"
    manifest.write_text(json.dumps(_manifest(workspace)), encoding="utf-8")
    args = (
        ["context", "build", "--proposal", "work", "--closeout", str(manifest)]
        if kind == "proposal"
        else [
            "context",
            "gc",
            "closeout",
            "--kind",
            kind,
            "--slug",
            "work",
            "--manifest",
            str(manifest),
        ]
    )
    assert dispatch([*args[1:], "--root", str(tmp_path), "--json"]) == 0
    assert (context / f"gc/closeouts/{kind}-work.json").is_file()


def _learning_audit(tmp_path: Path, *, tests: list[str]) -> tuple[Path, Path, dict]:
    """Audit workspace plus a pre-change (legacy-shape) reflection on a fresh rules doc."""
    context, workspace = _workspace(tmp_path, kind="audit")
    rules = context / "conventions/rules.md"
    rules.write_text("# Rules\n\nOwner text.\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/parser.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_ok.py").write_text(
        "from pathlib import Path\n\n"
        "def test_rule():\n"
        "    assert 'parser-rule' in Path('.context/conventions/rules.md').read_text()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    reflection = {
        "verified": True,
        "target": ".context/conventions/rules.md",
        "rule_id": "parser-rule",
        "body": "Use the shared parser.",
        "expected_sha256": digest(rules.read_bytes()),
        "sources": ["src/parser.py"],
        "tests": tests,
    }
    manifest = _manifest(workspace)
    manifest["learning_reflection"] = reflection
    return context, workspace, manifest


def _learner_for(status: str, state: dict):
    """Build the injected learner that yields ``status``; no monkeypatching."""

    def learner(context_dir, **kwargs):
        state["calls"] = state.get("calls", 0) + 1
        if status == "failed":
            raise RuntimeError("learner unavailable")
        if status == "ignored":
            return enqueue_learning(
                context_dir,
                event_id=kwargs["event_id"],
                origin="evolve",
                evidence=kwargs["evidence"],
            )
        if status == "no_entry":
            enqueue_learning(
                context_dir,
                event_id=kwargs["event_id"],
                origin="closeout",
                evidence=kwargs["evidence"],
            )
            return prepare_learning(context_dir, kwargs["event_id"], None)
        return run_learning(context_dir, **kwargs)

    return learner


_CASES = {
    "applied": ["tests/test_ok.py"],
    "evaluated": ["tests/test_bad.py"],
    "blocked": [],
    "no_entry": None,
    "pending": None,
    "ignored": None,
    "failed": None,
}


@pytest.mark.integration
@pytest.mark.parametrize("status", list(_CASES))
def test_every_learning_status_is_persisted_and_only_failed_exits_nonzero(
    tmp_path: Path, status: str
) -> None:
    tests = _CASES[status]
    context, _, manifest = _learning_audit(tmp_path, tests=tests or [])
    if tests is None:
        manifest.pop("learning_reflection")
    state: dict = {}
    learner = _learner_for(status, state)

    receipt = closeout_workspace(context, "audit", "work", manifest, learner=learner)

    assert receipt["learning"]["status"] == status
    assert learning_exit_code(receipt["learning"]) == (1 if status == "failed" else 0)
    event_id = next(
        f"closeout:audit:work:{digest((json.dumps(r, indent=2, sort_keys=True) + chr(10)).encode())}"
        for r in [{k: v for k, v in receipt.items() if k != "learning"}]
    )
    stored = read_event(context, event_id)
    failed = context / "gc/learning/audit-work.failed.json"
    if status == "failed":
        assert stored is None
        record = json.loads(failed.read_text(encoding="utf-8"))
        assert record["status"] == "failed"
        assert "learner unavailable" in record["error"]
        assert b"\r" not in failed.read_bytes()
    elif status == "ignored":
        assert stored is None
        assert not failed.exists()
    else:
        assert stored is not None and stored["status"] == status
        assert not failed.exists()

    if status in {"applied", "evaluated", "blocked", "no_entry"}:
        # Settled statuses are reported from storage; the learner is not re-run.
        again = closeout_workspace(context, "audit", "work", manifest, learner=learner)
        assert again["learning"]["status"] == status
        assert state["calls"] == 1


@pytest.mark.integration
def test_failed_learning_keeps_receipt_bytes_and_rerun_retries(tmp_path: Path) -> None:
    context, workspace, manifest = _learning_audit(tmp_path, tests=[])
    manifest.pop("learning_reflection")
    receipt_file = context / "gc/closeouts/audit-work.json"

    first = closeout_workspace(
        context, "audit", "work", manifest, learner=_learner_for("failed", {})
    )
    assert first["learning"]["status"] == "failed"
    failed = context / "gc/learning/audit-work.failed.json"
    assert failed.is_file()
    receipt_bytes = receipt_file.read_bytes()
    assert b'"learning"' not in receipt_bytes

    second = closeout_workspace(context, "audit", "work", manifest)
    assert second["learning"]["status"] == "pending"
    assert receipt_file.read_bytes() == receipt_bytes
    assert not failed.exists()


@pytest.mark.integration
def test_settled_status_clears_stale_failed_record(tmp_path: Path) -> None:
    context, _, manifest = _learning_audit(tmp_path, tests=[])
    manifest.pop("learning_reflection")
    closeout_workspace(
        context, "audit", "work", manifest, learner=_learner_for("failed", {})
    )
    failed = context / "gc/learning/audit-work.failed.json"
    assert failed.is_file()
    closeout_workspace(
        context, "audit", "work", manifest, learner=_learner_for("no_entry", {})
    )
    closeout_workspace(context, "audit", "work", manifest)
    assert not failed.exists()


@pytest.mark.integration
def test_failed_event_after_creation_is_marked_and_retried(tmp_path: Path) -> None:
    context, _, manifest = _learning_audit(tmp_path, tests=["tests/test_ok.py"])
    rules = context / "conventions/rules.md"
    owner = rules.read_bytes()

    def late_failure(context_dir, **kwargs):
        enqueue_learning(
            context_dir,
            event_id=kwargs["event_id"],
            origin="closeout",
            evidence=kwargs["evidence"],
            cue=kwargs["cue"],
        )
        raise RuntimeError("died after event creation")

    first = closeout_workspace(context, "audit", "work", manifest, learner=late_failure)
    assert first["learning"]["status"] == "failed"
    assert first["learning"]["state"] == "pending"
    assert not (context / "gc/learning/audit-work.failed.json").exists()
    assert rules.read_bytes() == owner

    second = closeout_workspace(context, "audit", "work", manifest)
    assert second["learning"]["status"] == "applied"
    assert "parser-rule" in rules.read_text(encoding="utf-8")


@pytest.mark.integration
def test_legacy_reflection_closes_flagged_legacy_shape_not_failed(
    tmp_path: Path,
) -> None:
    context, _, manifest = _learning_audit(tmp_path, tests=["tests/test_ok.py"])
    with pytest.warns(UserWarning, match="legacy_shape"):
        receipt = closeout_workspace(context, "audit", "work", manifest)
    assert receipt["learning"]["status"] == "applied"
    assert receipt["learning"]["legacy_shape"] is True
    assert learning_exit_code(receipt["learning"]) == 0


@pytest.mark.unit
@pytest.mark.parametrize("bad", [[{"cue": "x"}], {"cue": "only a cue"}])
def test_malformed_lesson_reflection_is_rejected_before_closeout(
    tmp_path: Path, bad
) -> None:
    context, workspace, manifest = _learning_audit(tmp_path, tests=[])
    manifest["learning_reflection"] = bad
    with pytest.raises(CloseoutError, match="learning_reflection"):
        closeout_workspace(context, "audit", "work", manifest)
    assert not (context / "gc/closeouts/audit-work.json").exists()


@pytest.mark.unit
def test_disposable_ref_has_a_single_home() -> None:
    from dummyindex.context.domains.docguard import citations
    from dummyindex.context.domains.proposals import closeout, retirement

    assert not hasattr(retirement, "DISPOSABLE_REF")
    assert not hasattr(closeout, "DISPOSABLE_REF")
    assert citations.cites_disposable(".context/proposals/x/spec.md")
    assert not citations.cites_disposable(".context/features/x/spec.md")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (
            {".context/INDEX.md": "- .context/proposals/work/lesson.md\n"},
            [],
        ),
        (
            {".context/features/INDEX.md": "- .context/proposals/work/lesson.md\n"},
            [".context/features/INDEX.md"],
        ),
        (
            {"tests/x.py": 'p = ".context/proposals/work/lesson.md"\n'},
            ["tests/x.py"],
        ),
        (
            {
                ".context/INDEX.md": "- .context/proposals/work/lesson.md\n",
                "tests/x.py": 'p = ".context/proposals/work/lesson.md"\n',
            },
            ["tests/x.py"],
        ),
        (
            {
                ".context/fleet/run-0001/state.json": '{"paths": [".context/proposals/work/lesson.md"]}\n',
            },
            [],
        ),
    ],
)
def test_generated_context_index_is_not_a_durable_reference(
    tmp_path: Path, files: dict[str, str], expected: list[str]
) -> None:
    """Only authored files count as inbound durable references."""
    context, workspace = _workspace(tmp_path)
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert durable_references(context, workspace) == expected
