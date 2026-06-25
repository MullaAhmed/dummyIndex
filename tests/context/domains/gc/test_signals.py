"""Unit tests for ``domains/gc/signals.py:classify`` (deterministic tags only).

``classify`` is PURE: it reads only the ``Candidate`` fields plus the workspace
files under ``context_dir`` — never git, never ``enumerate``. The critical
correctness case is ``orphan-empty``: a freshly-scaffolded proposal's ``spec.md``
is *not* byte-equal to ``_spec_template`` (``apply_consistency`` injects a
``## Consistency`` block), but ``plan.md``/``checklist.md`` are untouched — so
``orphan-empty`` is decided off those two files, never ``spec.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.gc.enums import CandidateKind
from dummyindex.context.domains.gc.models import Candidate
from dummyindex.context.domains.gc.signals import classify
from dummyindex.context.domains.proposals.store import (
    _checklist_template,
    _plan_template,
    _spec_template,
)


def _write_proposal(
    context_dir: Path,
    slug: str,
    *,
    title: str,
    spec: str,
    plan: str,
    checklist: str,
    status: str | None = None,
) -> None:
    """Hand-build a ``.context/proposals/<slug>/`` workspace on disk."""
    workspace = context_dir / "proposals" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"slug": slug, "title": title}
    if status is not None:
        payload["status"] = status
    (workspace / "proposal.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (workspace / "spec.md").write_text(spec, encoding="utf-8")
    (workspace / "plan.md").write_text(plan, encoding="utf-8")
    (workspace / "checklist.md").write_text(checklist, encoding="utf-8")


def _proposal_candidate(slug: str, **kwargs: object) -> Candidate:
    return Candidate(
        kind=CandidateKind.PROPOSAL,
        slug=slug,
        rel_path=f"proposals/{slug}/",
        **kwargs,  # type: ignore[arg-type]
    )


# --- orphan-empty --------------------------------------------------------


@pytest.mark.unit
def test_orphan_empty_when_plan_and_checklist_are_raw_templates(tmp_path: Path):
    """A scaffold whose plan.md+checklist.md are the raw templates is orphan-empty.

    The spec.md carries an injected ``## Consistency`` block (mimicking
    ``apply_consistency``), so it is NOT byte-equal to the spec template — yet
    the proposal is still ``orphan-empty`` because the decision keys off
    plan.md+checklist.md only.
    """
    title = "Some abandoned scaffold"
    context_dir = tmp_path / ".context"
    consistency_injected_spec = (
        _spec_template(title).rstrip()
        + "\n\n<!-- dummyindex:consistency:begin -->\n## Consistency\n\n"
        "_No related features detected by the consistency scan._\n\n"
        "<!-- dummyindex:consistency:end -->\n"
    )
    _write_proposal(
        context_dir,
        "abandoned",
        title=title,
        spec=consistency_injected_spec,
        plan=_plan_template(title),
        checklist=_checklist_template(title),
    )
    signals = classify(_proposal_candidate("abandoned"), context_dir, tmp_path)
    assert "orphan-empty" in signals


@pytest.mark.unit
def test_orphan_empty_absent_when_plan_authored(tmp_path: Path):
    """An authored plan.md means NOT orphan-empty (the spec's regression case)."""
    title = "Real work"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "real",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title) + "\n2. _A real, authored second task._\n",
        checklist=_checklist_template(title),
    )
    signals = classify(_proposal_candidate("real"), context_dir, tmp_path)
    assert "orphan-empty" not in signals


@pytest.mark.unit
def test_orphan_empty_absent_when_checklist_authored(tmp_path: Path):
    """An authored checklist.md alone (plan still raw) is still NOT orphan-empty."""
    title = "Half done"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "half",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title),
        checklist=_checklist_template(title) + "- [ ] _A second, authored item._\n",
    )
    signals = classify(_proposal_candidate("half"), context_dir, tmp_path)
    assert "orphan-empty" not in signals


# --- checklist completion ------------------------------------------------


@pytest.mark.unit
def test_checklist_partial(tmp_path: Path):
    title = "Partial"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "partial",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title) + "\n2. _authored so not orphan-empty._\n",
        checklist=(
            "# Checklist — Partial\n\n"
            "- [x] First item done.\n"
            "- [ ] Second item still open.\n"
        ),
    )
    signals = classify(_proposal_candidate("partial"), context_dir, tmp_path)
    assert "checklist-partial" in signals
    assert "checklist-complete" not in signals


@pytest.mark.unit
def test_checklist_complete(tmp_path: Path):
    title = "Complete"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "complete",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title) + "\n2. _authored so not orphan-empty._\n",
        checklist=(
            "# Checklist — Complete\n\n"
            "- [x] First item done.\n"
            "- [x] Second item done.\n"
        ),
    )
    signals = classify(_proposal_candidate("complete"), context_dir, tmp_path)
    assert "checklist-complete" in signals
    assert "checklist-partial" not in signals


# --- audit report-written ------------------------------------------------


@pytest.mark.unit
def test_audit_report_written(tmp_path: Path):
    context_dir = tmp_path / ".context"
    workspace = context_dir / "audits" / "finished"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "report.md").write_text("# findings\n", encoding="utf-8")
    candidate = Candidate(
        kind=CandidateKind.AUDIT, slug="finished", rel_path="audits/finished/"
    )
    signals = classify(candidate, context_dir, tmp_path)
    assert "report-written" in signals


@pytest.mark.unit
def test_audit_report_absent(tmp_path: Path):
    context_dir = tmp_path / ".context"
    workspace = context_dir / "audits" / "open"
    workspace.mkdir(parents=True, exist_ok=True)
    candidate = Candidate(
        kind=CandidateKind.AUDIT, slug="open", rel_path="audits/open/"
    )
    signals = classify(candidate, context_dir, tmp_path)
    assert "report-written" not in signals


# --- cross-cutting: untracked / age / status ----------------------------


@pytest.mark.unit
def test_untracked_emitted_from_candidate_field(tmp_path: Path):
    title = "Untracked"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "untracked",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title),
        checklist=_checklist_template(title),
    )
    signals = classify(
        _proposal_candidate("untracked", tracked=False), context_dir, tmp_path
    )
    assert "untracked" in signals


@pytest.mark.unit
def test_tracked_candidate_has_no_untracked_tag(tmp_path: Path):
    title = "Tracked"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "tracked",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title),
        checklist=_checklist_template(title),
    )
    signals = classify(
        _proposal_candidate("tracked", tracked=True), context_dir, tmp_path
    )
    assert "untracked" not in signals


@pytest.mark.unit
def test_age_days_emitted(tmp_path: Path):
    title = "Aged"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "aged",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title),
        checklist=_checklist_template(title),
    )
    signals = classify(
        _proposal_candidate("aged", age_days=12), context_dir, tmp_path
    )
    assert "age-12d" in signals


@pytest.mark.unit
def test_age_days_none_emits_no_age_tag(tmp_path: Path):
    title = "No age"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "noage",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title),
        checklist=_checklist_template(title),
    )
    signals = classify(
        _proposal_candidate("noage", age_days=None), context_dir, tmp_path
    )
    assert not any(s.startswith("age-") for s in signals)


@pytest.mark.unit
def test_status_tag_emitted(tmp_path: Path):
    title = "Done one"
    context_dir = tmp_path / ".context"
    _write_proposal(
        context_dir,
        "doneone",
        title=title,
        spec=_spec_template(title),
        plan=_plan_template(title) + "\n2. _authored._\n",
        checklist=_checklist_template(title),
        status="done",
    )
    signals = classify(
        _proposal_candidate("doneone", status="done"), context_dir, tmp_path
    )
    assert "status:done" in signals


@pytest.mark.unit
def test_audit_is_never_orphan_empty(tmp_path: Path):
    """orphan-empty only applies to proposals/archived, never audits."""
    context_dir = tmp_path / ".context"
    workspace = context_dir / "audits" / "fresh"
    workspace.mkdir(parents=True, exist_ok=True)
    candidate = Candidate(
        kind=CandidateKind.AUDIT, slug="fresh", rel_path="audits/fresh/"
    )
    signals = classify(candidate, context_dir, tmp_path)
    assert "orphan-empty" not in signals
