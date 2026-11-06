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
from dummyindex.context.domains.gc import CandidateKind, GcTargetError, delete_workspace
from dummyindex.context.domains.proposals import CloseoutError, closeout_workspace
from dummyindex.context.domains.proposals.retirement import (
    ADMIN_FILES,
    digest,
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
