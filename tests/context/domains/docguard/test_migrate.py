"""Tests for ``domains/docguard/migrate.py`` — stray-doc migration into homes.

Covers the spec's ``Migration (migrate-docs)`` Acceptance matrix. Per the
project marker convention, a test that drives a real ``git init`` / ``git mv``
is ``@pytest.mark.integration``; the pure-logic / ``Path.replace`` (non-git)
ones are ``@pytest.mark.unit``. Every throwaway repo is built under ``tmp_path``
— the host repo and ``SAMPLE_REPO`` are never touched.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.domains import docguard
from dummyindex.context.domains.audit.workspace import read_audit, report_written
from dummyindex.context.domains.docguard import migrate
from dummyindex.context.domains.docguard.enums import DocKind
from dummyindex.context.domains.docguard.errors import MigrationContainmentError
from dummyindex.context.domains.docguard.migrate import (
    apply_moves,
    enumerate_strays,
    plan_moves,
)
from dummyindex.context.domains.proposals.enums import ProposalStatus
from dummyindex.context.domains.proposals.models import Proposal
from dummyindex.context.domains.proposals.store import (
    read_proposal,
    validate_slug,
    write_proposal_json,
)

# ----- fixtures / helpers ---------------------------------------------------


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway repo root + its ``.context/`` dir (no git)."""
    root = tmp_path / "repo"
    context_dir = root / ".context"
    context_dir.mkdir(parents=True)
    return root, context_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _git_init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")


def _porcelain(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
    ).stdout


def _migrate(root: Path, context_dir: Path, *, force: bool = False):
    """Enumerate → plan → apply (``yes=True``) in one shot for a repo."""
    groups = enumerate_strays(root, context_dir)
    plan = plan_moves(root, context_dir, groups, force=force)
    return apply_moves(plan, yes=True, force=force)


# ----- dry-run --------------------------------------------------------------


@pytest.mark.unit
def test_dry_run_moves_nothing(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    stray = root / "docs" / "specs" / "2026-06-08-widget-design.md"
    _write(stray, "# Widget\n\nbody\n")

    groups = enumerate_strays(root, context_dir)
    plan = plan_moves(root, context_dir, groups)
    result = apply_moves(plan, yes=False)

    assert result.dry_run is True
    assert result.moved == ()
    # The plan still describes the intended move (sorted, one group).
    assert [g.slug for g in plan.groups] == ["2026-06-08-widget"]
    # Nothing on disk changed.
    assert stray.is_file()
    assert not (context_dir / "proposals").exists()


# ----- tracked / untracked git paths (integration) --------------------------


@pytest.mark.integration
def test_tracked_path_shows_rename_in_index(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context_dir = root / ".context"
    _git_init(root)
    context_dir.mkdir()
    stray = root / "docs" / "specs" / "widget-design.md"
    _write(stray, "# Widget design\n\nbody\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")

    result = _migrate(root, context_dir)

    moved = {m.target_rel: m.method for m in result.moved}
    target = ".context/proposals/widget/spec.md"
    assert moved == {target: "git-mv"}
    # A rename recorded IN THE INDEX (R), distinguishing git mv from delete+create.
    porcelain = _porcelain(root)
    assert f"R  docs/specs/widget-design.md -> {target}" in porcelain
    assert not stray.exists()
    assert (root / target).is_file()


@pytest.mark.integration
def test_untracked_gitignored_path_ends_staged_at_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context_dir = root / ".context"
    _git_init(root)
    context_dir.mkdir()
    # The root-cause case: a .gitignore'd planning dir.
    _write(root / ".gitignore", "docs/superpowers/\n")
    stray = root / "docs" / "superpowers" / "plans" / "2026-06-09-thing.md"
    _write(stray, "# Thing\n\nbody\n")

    result = _migrate(root, context_dir)

    target = ".context/proposals/2026-06-09-thing/plan.md"
    assert {m.target_rel: m.method for m in result.moved} == {target: "replace+add"}
    # Staged (A) at the new path; source gone.
    assert f"A  {target}" in _porcelain(root)
    assert not stray.exists()
    assert (root / target).is_file()


# ----- non-git (Path.replace, no git invoked) -------------------------------


@pytest.mark.unit
def test_non_git_repo_uses_replace_and_invokes_no_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, context_dir = _repo(tmp_path)
    stray = root / "docs" / "specs" / "x-design.md"
    _write(stray, "# X design\n\nbody\n")

    def _boom(*_args, **_kwargs):
        raise AssertionError("git must not be invoked in a non-git repo")

    monkeypatch.setattr(migrate, "run_git", _boom)
    monkeypatch.setattr(migrate, "is_tracked", _boom)

    result = _migrate(root, context_dir)

    assert [m.method for m in result.moved] == ["replace"]
    assert (context_dir / "proposals" / "x" / "spec.md").is_file()
    assert not stray.exists()


# ----- overwrite refusal + --force fills missing only -----------------------


@pytest.mark.unit
def test_existing_home_skipped_without_force(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    home = context_dir / "proposals" / "widget"
    _write(home / "spec.md", "ORIGINAL\n")
    # A same-dir spec+plan pair → slug "widget".
    _write(root / "docs" / "specs" / "widget-design.md", "# New spec\n")
    _write(root / "docs" / "specs" / "widget.md", "# New plan\n")

    result = _migrate(root, context_dir, force=False)

    assert result.moved == ()
    assert [s.target_rel for s in result.skipped] == [".context/proposals/widget"]
    assert "already exists" in result.skipped[0].reason
    assert (home / "spec.md").read_text() == "ORIGINAL\n"


@pytest.mark.unit
def test_force_fills_missing_only_leaving_existing_byte_identical(
    tmp_path: Path,
) -> None:
    root, context_dir = _repo(tmp_path)
    home = context_dir / "proposals" / "widget"
    _write(home / "spec.md", "ORIGINAL SPEC — keep me\n")
    before_spec = (home / "spec.md").read_bytes()
    _write(root / "docs" / "specs" / "widget-design.md", "# New spec\n")
    _write(root / "docs" / "specs" / "widget.md", "# New plan\n")

    result = _migrate(root, context_dir, force=True)

    # Existing non-empty spec.md untouched; missing plan.md + proposal.json filled.
    assert (home / "spec.md").read_bytes() == before_spec
    assert (home / "plan.md").is_file()
    assert (home / "proposal.json").is_file()
    moved_targets = {m.target_rel for m in result.moved}
    assert ".context/proposals/widget/plan.md" in moved_targets
    skipped_targets = {s.target_rel for s in result.skipped}
    assert ".context/proposals/widget/spec.md" in skipped_targets


# ----- containment + symlink skips ------------------------------------------


@pytest.mark.unit
def test_containment_refuses_escaping_target_and_moves_nothing(
    tmp_path: Path,
) -> None:
    root, context_dir = _repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    # .context/proposals → outside (an escaping symlink), like a misconfigured repo.
    (context_dir / "proposals").symlink_to(outside, target_is_directory=True)
    stray = root / "docs" / "specs" / "y-design.md"
    _write(stray, "# Y\n")

    groups = enumerate_strays(root, context_dir)
    with pytest.raises(MigrationContainmentError):
        plan_moves(root, context_dir, groups)

    # Nothing moved: the escape target is empty and the source is untouched.
    assert list(outside.iterdir()) == []
    assert stray.is_file()


@pytest.mark.unit
def test_symlinked_stray_is_skipped(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    # A real stray (grouped) and a symlinked stray (skipped).
    real = root / "docs" / "specs" / "real-design.md"
    _write(real, "# Real\n")
    pointee = tmp_path / "pointee.md"
    _write(pointee, "# Ghost\n")
    ghost = root / "docs" / "specs" / "ghost-design.md"
    ghost.parent.mkdir(parents=True, exist_ok=True)
    ghost.symlink_to(pointee)

    groups = enumerate_strays(root, context_dir)

    slugs = {g.slug for g in groups}
    assert slugs == {"real"}  # ghost skipped via is_symlink()


# ----- source untouched + idempotency ---------------------------------------


@pytest.mark.unit
def test_source_code_and_guide_untouched_after_yes(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    py = root / "src" / "widget-design.md"  # *-design.md outside docs/ — not a stray
    _write(py, "# not a stray\n")
    guide = root / "docs" / "guide" / "01-intro.md"
    _write(guide, "# guide\n")
    code = root / "src" / "app.py"
    _write(code, "print('hi')\n")
    _write(root / "docs" / "specs" / "z-design.md", "# Z\n")

    py_before = py.read_bytes()
    guide_before = guide.read_bytes()
    code_before = code.read_bytes()

    _migrate(root, context_dir)

    assert py.read_bytes() == py_before
    assert guide.read_bytes() == guide_before
    assert code.read_bytes() == code_before


@pytest.mark.unit
def test_idempotent_second_run_finds_nothing(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    _write(root / "docs" / "specs" / "alpha-design.md", "# Alpha\n")

    first = _migrate(root, context_dir)
    assert len(first.moved) == 1

    # Second pass: no strays remain under docs/.
    groups = enumerate_strays(root, context_dir)
    assert groups == ()
    second = apply_moves(plan_moves(root, context_dir, groups), yes=True)
    assert second.moved == ()


# ----- titles ---------------------------------------------------------------


@pytest.mark.unit
def test_title_from_h1_and_fallback_to_base_slug(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    _write(root / "docs" / "specs" / "has-h1-design.md", "# Real Heading\n\nbody\n")
    _write(root / "docs" / "plans" / "2026-01-01-nofirst.md", "no heading here\n")

    plan = plan_moves(root, context_dir, enumerate_strays(root, context_dir))
    titles = {g.slug: g.title for g in plan.groups}

    assert titles["has-h1"] == "Real Heading"
    assert titles["2026-01-01-nofirst"] == "2026-01-01-nofirst"  # base_slug fallback


# ----- proposal.json byte-stability + round-trip ----------------------------


@pytest.mark.unit
def test_proposal_json_byte_stable_and_round_trips(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    _write(root / "docs" / "specs" / "export-design.md", "# Add export\n\nbody\n")

    _migrate(root, context_dir)

    home = context_dir / "proposals" / "export"
    expected = (
        json.dumps(
            Proposal(
                slug="export", title="Add export", status=ProposalStatus.DONE
            ).to_dict(),
            indent=2,
        )
        + "\n"
    )
    assert (home / "proposal.json").read_text(encoding="utf-8") == expected
    # Round-trips through the proposals reader + slug validator.
    proposal = read_proposal(context_dir, "export")
    assert proposal.status is ProposalStatus.DONE
    assert proposal.title == "Add export"
    assert validate_slug(proposal.slug) == "export"


@pytest.mark.unit
def test_migrated_proposal_is_terminal_with_no_template_checklist(
    tmp_path: Path,
) -> None:
    root, context_dir = _repo(tmp_path)
    _write(root / "docs" / "specs" / "feat-design.md", "# Feat\n")

    _migrate(root, context_dir)

    home = context_dir / "proposals" / "feat"
    # Terminal status, and NO checklist.md / spec/plan template siblings minted
    # (so gc/_checklist_partial cannot read the migrated proposal as in-flight).
    assert read_proposal(context_dir, "feat").status is ProposalStatus.DONE
    assert not (home / "checklist.md").exists()
    assert (home / "spec.md").is_file()  # the relocated stray, not a template
    assert not (home / "plan.md").exists()  # no plan member ⇒ no template plan


# ----- audit workspace ------------------------------------------------------


@pytest.mark.unit
def test_audit_stray_lands_as_well_formed_workspace(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    _write(
        root / "docs" / "internal" / "audits" / "cache-REPORT.md",
        "# Cache audit\n\nfindings\n",
    )

    result = _migrate(root, context_dir)

    home = context_dir / "audits" / "cache-report"
    assert {m.kind for m in result.moved} == {DocKind.AUDIT}
    # ensure_audit scaffolded a well-formed workspace; the report content landed.
    for name in ("audit.json", "description.md", "catalog.json"):
        assert (home / name).is_file(), f"missing {name}"
    assert (home / "findings").is_dir()
    assert (home / "report.md").read_text(encoding="utf-8") == (
        "# Cache audit\n\nfindings\n"
    )
    assert report_written(context_dir, "cache-report") is True
    assert read_audit(context_dir, "cache-report").slug == "cache-report"


# ----- paired spec/plan group ----------------------------------------------


@pytest.mark.unit
def test_same_dir_spec_plan_pair_is_one_group_two_moves(tmp_path: Path) -> None:
    root, context_dir = _repo(tmp_path)
    _write(root / "docs" / "specs" / "widget-design.md", "# Widget\n")
    _write(root / "docs" / "specs" / "widget.md", "# Widget plan\n")

    result = _migrate(root, context_dir)

    targets = sorted(m.target_rel for m in result.moved)
    assert targets == [
        ".context/proposals/widget/plan.md",
        ".context/proposals/widget/spec.md",
    ]
    # Exactly one proposal.json for the pair.
    assert (context_dir / "proposals" / "widget" / "proposal.json").is_file()


# ----- write_proposal_json (the narrow writer) ------------------------------


@pytest.mark.unit
def test_write_proposal_json_writes_only_proposal_json(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()

    rel = write_proposal_json(
        context_dir, "demo", "Demo title", status=ProposalStatus.DONE
    )

    assert rel == "proposals/demo/proposal.json"
    home = context_dir / "proposals" / "demo"
    assert sorted(p.name for p in home.iterdir()) == ["proposal.json"]
    # No template spec/plan/checklist that would collide with a later git mv.
    for template in ("spec.md", "plan.md", "checklist.md"):
        assert not (home / template).exists()
    assert read_proposal(context_dir, "demo").status is ProposalStatus.DONE


# ----- public-surface re-exports stay intact --------------------------------


@pytest.mark.unit
def test_docguard_package_still_exports_classifier_surface() -> None:
    # T2 must not disturb the docguard public surface (a sibling owns __init__).
    assert hasattr(docguard, "classify_doc_path")
    assert hasattr(docguard, "group_strays")
