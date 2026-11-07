"""Closeout drafts are written beside the GC cache and never overwrite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.proposals import CloseoutError, closeout_from_file
from dummyindex.context.domains.proposals.draft import (
    draft_manifest,
    draft_path,
    write_draft,
)
from dummyindex.context.domains.proposals.errors import ProposalSlugError
from dummyindex.context.domains.proposals.retirement import (
    ADMIN_FILES,
    workspace_inventory,
)


@pytest.fixture(autouse=True)
def _fixed_head(monkeypatch):
    monkeypatch.setattr(
        "dummyindex.context.domains.proposals.closeout.head_commit",
        lambda _root: "revision-one",
    )


def _proposal(tmp_path: Path, slug: str = "feat", checklist: str | None = None) -> Path:
    context = tmp_path / ".context"
    workspace = context / "proposals" / slug
    workspace.mkdir(parents=True)
    (workspace / "proposal.json").write_text(
        json.dumps({"slug": slug, "title": "T", "status": "planned"}), encoding="utf-8"
    )
    if checklist is not None:
        (workspace / "checklist.md").write_text(checklist, encoding="utf-8")
    (workspace / "notes.md").write_text("notes\n", encoding="utf-8")
    return context


def _audit(tmp_path: Path, slug: str = "aud") -> Path:
    context = tmp_path / ".context"
    workspace = context / "audits" / slug
    workspace.mkdir(parents=True)
    (workspace / "audit.json").write_text("{}", encoding="utf-8")
    return context


@pytest.mark.unit
def test_write_draft_records_inventory_and_discards(tmp_path):
    context = _proposal(tmp_path, checklist="- [x] a\n- [x] b\n")
    workspace = context / "proposals" / "feat"
    before = workspace_inventory(workspace)

    path = write_draft(context, "proposal", "feat")

    assert path == context / "cache" / "gc" / "closeout-proposal-feat.json"
    assert path == draft_path(context, "proposal", "feat")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["reviewed_files"] == workspace_inventory(workspace) == before
    assert data["state"] == "implemented"
    assert data["disposition"] == "completed"
    assert set(data["discarded"]) == set(before) - ADMIN_FILES
    assert all(reason == "" for reason in data["discarded"].values())


@pytest.mark.unit
@pytest.mark.parametrize("checklist", [None, ""])
def test_missing_or_empty_checklist_drafts_planned(tmp_path, checklist):
    context = _proposal(tmp_path, checklist=checklist)

    manifest = draft_manifest(context, "proposal", "feat")

    assert manifest["state"] == "planned"
    assert manifest["disposition"] == "abandoned"


@pytest.mark.unit
def test_incomplete_checklist_drafts_planned(tmp_path):
    context = _proposal(tmp_path, checklist="- [x] a\n- [ ] b\n")

    assert draft_manifest(context, "proposal", "feat")["state"] == "planned"


@pytest.mark.unit
def test_audit_draft_tracks_report(tmp_path):
    context = _audit(tmp_path)

    assert draft_manifest(context, "audit", "aud")["state"] == "planned"

    (context / "audits" / "aud" / "report.md").write_text("done\n", encoding="utf-8")
    manifest = draft_manifest(context, "audit", "aud")
    assert manifest["state"] == "implemented"
    assert manifest["disposition"] == "completed"


@pytest.mark.unit
def test_second_draft_refuses_and_keeps_first_bytes(tmp_path):
    context = _proposal(tmp_path, checklist="- [x] a\n")
    path = write_draft(context, "proposal", "feat")
    first = path.read_bytes()

    with pytest.raises(CloseoutError, match="draft exists"):
        write_draft(context, "proposal", "feat")

    assert path.read_bytes() == first


@pytest.mark.unit
def test_bad_slug_and_missing_workspace_fail(tmp_path):
    context = _proposal(tmp_path)

    with pytest.raises(ProposalSlugError):
        write_draft(context, "proposal", "../x")
    with pytest.raises(CloseoutError, match="workspace not found"):
        write_draft(context, "proposal", "missing")
    with pytest.raises(CloseoutError, match="closeout kind"):
        draft_manifest(context, "plan", "feat")


@pytest.mark.unit
def test_unedited_draft_is_rejected_on_closeout(tmp_path):
    context = _proposal(tmp_path, checklist="- [x] a\n- [x] b\n")
    path = write_draft(context, "proposal", "feat")

    with pytest.raises(
        CloseoutError, match="discarded entries require an explicit reason"
    ):
        closeout_from_file(context, "proposal", "feat", path)
