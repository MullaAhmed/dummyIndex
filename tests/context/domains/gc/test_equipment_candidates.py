"""Equipment GC candidates (contract 18) and their orphan listing (contract 20)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip.constants import SCHEMA_VERSION
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentScope,
    EquipmentSource,
    RequestedBy,
)
from dummyindex.context.domains.equip.generate.fresh import project_slug
from dummyindex.context.domains.equip.lifecycle.hashing import content_hash
from dummyindex.context.domains.equip.lifecycle.manifest import write_manifest
from dummyindex.context.domains.equip.models import EquipmentItem, EquipmentManifest
from dummyindex.context.domains.gc import Recommendation, scan
from dummyindex.context.domains.gc.enums import CandidateKind
from dummyindex.context.domains.gc.equipment import enumerate_equipment_candidates

pytestmark = pytest.mark.unit

BODY = "# implementer\n\nDo the task.\n"


def _context(tmp_path: Path) -> Path:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    return context_dir


def _proposal(
    context_dir: Path, slug: str, status: str, *, checklist: str = ""
) -> None:
    workspace = context_dir / "proposals" / slug
    workspace.mkdir(parents=True)
    (workspace / "proposal.json").write_text(
        json.dumps({"slug": slug, "title": slug, "status": status}), encoding="utf-8"
    )
    if checklist:
        (workspace / "checklist.md").write_text(checklist, encoding="utf-8")


def _agent_file(root: Path, name: str, body: str = BODY) -> str:
    rel = f".claude/agents/{name}.md"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return rel


def _item(
    root: Path,
    name: str,
    *,
    scope: EquipmentScope = EquipmentScope.TASK,
    requested_by: RequestedBy | None = RequestedBy.PROPOSAL,
    task_refs: tuple[str, ...] = (),
    body: str = BODY,
) -> EquipmentItem:
    rel = _agent_file(root, name, body)
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=rel,
        source=EquipmentSource.GENERATED,
        capabilities=("implement",),
        subagent_type=name,
        version="1.0.0",
        origin_hash=content_hash(BODY),
        scope=scope,
        requested_by=requested_by,
        task_refs=task_refs,
    )


def _write(context_dir: Path, *items: EquipmentItem) -> None:
    write_manifest(
        context_dir,
        EquipmentManifest(schema_version=SCHEMA_VERSION, items=tuple(items)),
    )


def _candidates(context_dir: Path) -> dict[str, object]:
    return {c.slug: c for c in enumerate_equipment_candidates(context_dir)}


def test_done_proposal_orphans_pristine_task_item_for_delete(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "done")
    _write(
        context_dir,
        _item(tmp_path, "impl-p1", task_refs=("proposal:p1",)),
    )

    candidate = _candidates(context_dir)["impl-p1"]

    assert candidate.kind is CandidateKind.EQUIPMENT
    assert candidate.recommendation is None  # set by scan, not enumeration
    report = scan(context_dir, tmp_path)
    (row,) = [c for c in report.candidates if c.slug == "impl-p1"]
    assert row.recommendation == Recommendation.DELETE.value


def test_in_progress_proposal_blocks_its_task_item(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "in_progress")
    _write(context_dir, _item(tmp_path, "impl-p1", task_refs=("proposal:p1",)))

    assert _candidates(context_dir) == {}


def test_partial_checklist_blocks_done_proposal_ref(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "done", checklist="- [ ] open item\n")
    _write(context_dir, _item(tmp_path, "impl-p1", task_refs=("proposal:p1",)))

    assert _candidates(context_dir) == {}


def test_one_in_progress_ref_blocks_item_with_done_ref(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "done")
    _proposal(context_dir, "p2", "in_progress")
    _write(
        context_dir,
        _item(tmp_path, "impl-shared", task_refs=("proposal:p1", "proposal:p2")),
    )

    assert _candidates(context_dir) == {}


def test_user_modified_task_item_is_review(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "done")
    item = _item(tmp_path, "impl-p1", task_refs=("proposal:p1",))
    _write(context_dir, item)
    (tmp_path / item.path).write_text(BODY + "hand edit\n", encoding="utf-8")

    report = scan(context_dir, tmp_path)
    (row,) = [c for c in report.candidates if c.slug == "impl-p1"]

    assert row.recommendation == Recommendation.REVIEW.value
    assert "user-modified" in row.signals


def test_closed_audit_ref_counts_as_finished(tmp_path: Path):
    context_dir = _context(tmp_path)
    audit = context_dir / "audits" / "a1"
    audit.mkdir(parents=True)
    (audit / "report.md").write_text("# report\n", encoding="utf-8")
    _write(context_dir, _item(tmp_path, "impl-a1", task_refs=("audit:a1",)))

    assert set(_candidates(context_dir)) == {"impl-a1"}


def test_legacy_pristine_db_specialist_without_evidence_is_review(tmp_path: Path):
    context_dir = _context(tmp_path)
    db_name = f"{project_slug(tmp_path)}-db-specialist"
    _write(
        context_dir,
        _item(
            tmp_path,
            db_name,
            scope=EquipmentScope.PROJECT,
            requested_by=RequestedBy.LEGACY,
        ),
    )

    report = scan(context_dir, tmp_path)
    (row,) = [c for c in report.candidates if c.slug == db_name]

    assert row.recommendation == Recommendation.REVIEW.value
    assert "pristine" in row.signals


def test_legacy_specialist_the_baseline_still_produces_is_not_candidate(
    tmp_path: Path,
):
    context_dir = _context(tmp_path)
    _write(
        context_dir,
        _item(
            tmp_path,
            "generic-implementer",
            scope=EquipmentScope.PROJECT,
            requested_by=RequestedBy.LEGACY,
        ),
    )

    assert _candidates(context_dir) == {}


def test_add_specialist_item_is_never_candidate(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "done")
    _write(
        context_dir,
        _item(
            tmp_path,
            "impl-explicit",
            requested_by=RequestedBy.ADD_SPECIALIST,
            task_refs=("proposal:p1",),
        ),
        _item(
            tmp_path,
            "db-explicit",
            scope=EquipmentScope.PROJECT,
            requested_by=RequestedBy.ADD_SPECIALIST,
        ),
    )

    assert _candidates(context_dir) == {}


def test_scan_lists_orphaned_task_items_under_proposal(tmp_path: Path):
    context_dir = _context(tmp_path)
    _proposal(context_dir, "p1", "done")
    _write(context_dir, _item(tmp_path, "impl-p1", task_refs=("proposal:p1",)))

    report = scan(context_dir, tmp_path)
    (proposal,) = [c for c in report.candidates if c.kind is CandidateKind.PROPOSAL]

    assert "orphan:impl-p1" in proposal.signals


def test_corrupt_manifest_yields_no_equipment_candidates(tmp_path: Path):
    context_dir = _context(tmp_path)
    (context_dir / "equipment.json").write_text("{not json", encoding="utf-8")

    assert enumerate_equipment_candidates(context_dir) == ()
