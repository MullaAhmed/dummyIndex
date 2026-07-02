"""Unit tests for ``domains/docguard/classify.py`` (pure, filesystem-free).

``classify_doc_path`` / ``group_strays`` reason only over the repo-relative path
*shape* — these tests build path objects under a synthetic root and never touch
disk, so every test is ``@pytest.mark.unit``. The matrix mirrors the spec's
Acceptance: the labelled fixture rows, the location-gate negative controls, the
managed-location exclusion, slug derivation (awkward + unslug-able), and the
``(directory, stem)`` pairing / collision behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.docguard.classify import (
    classify_doc_path,
    group_strays,
)
from dummyindex.context.domains.docguard.enums import DocKind, DocRole
from dummyindex.context.domains.docguard.errors import DocPathError
from dummyindex.context.domains.proposals.store import validate_slug

# Synthetic repo root — a pure path anchor; nothing is created on disk.
ROOT = Path("/repo")


def _classify(rel: str):
    """Classify a repo-relative POSIX path under the synthetic root."""
    return classify_doc_path(ROOT, ROOT / rel)


# ----- labelled fixture matrix (planning rows) ------------------------------


@pytest.mark.unit
def test_docs_specs_design_is_proposal_spec() -> None:
    dc = _classify("docs/specs/2026-06-08-x-design.md")
    assert dc.is_planning_doc is True
    assert dc.kind is DocKind.PROPOSAL
    assert dc.in_managed_location is False
    assert dc.role is DocRole.SPEC
    assert dc.pairing_stem == "2026-06-08-x"
    assert dc.suggested_slug == "2026-06-08-x"
    assert dc.suggested_home == ".context/proposals/2026-06-08-x"


@pytest.mark.unit
def test_docs_plans_plain_is_proposal_plan() -> None:
    dc = _classify("docs/plans/2026-06-08-x.md")
    assert dc.is_planning_doc is True
    assert dc.kind is DocKind.PROPOSAL
    assert dc.role is DocRole.PLAN
    assert dc.pairing_stem == "2026-06-08-x"
    assert dc.suggested_slug == "2026-06-08-x"
    assert dc.suggested_home == ".context/proposals/2026-06-08-x"


@pytest.mark.unit
def test_docs_superpowers_plans_is_proposal() -> None:
    dc = _classify("docs/superpowers/plans/2026-06-08-x.md")
    assert dc.is_planning_doc is True
    assert dc.kind is DocKind.PROPOSAL
    assert dc.suggested_slug == "2026-06-08-x"


@pytest.mark.unit
def test_docs_internal_audits_report_is_audit() -> None:
    dc = _classify("docs/internal/audits/2026-06-08-auth-REPORT.md")
    assert dc.is_planning_doc is True
    assert dc.kind is DocKind.AUDIT
    assert dc.suggested_slug == "2026-06-08-auth-report"
    assert dc.suggested_home == ".context/audits/2026-06-08-auth-report"


# ----- negative controls ----------------------------------------------------


@pytest.mark.unit
def test_design_outside_docs_is_none() -> None:
    # The location gate: a *-design.md outside docs/ is NOT a stray.
    dc = _classify("src/widget-design.md")
    assert dc.is_planning_doc is False
    assert dc.kind is DocKind.NONE
    assert dc.suggested_slug is None
    assert dc.suggested_home is None


@pytest.mark.unit
def test_design_under_docs_is_stray() -> None:
    # Positive counterpart proving the location gate is the deciding factor:
    # the SAME filename under docs/ IS a stray.
    dc = _classify("docs/widget-design.md")
    assert dc.is_planning_doc is True
    assert dc.kind is DocKind.PROPOSAL
    assert dc.role is DocRole.SPEC
    assert dc.suggested_slug == "widget"


@pytest.mark.unit
def test_docs_guide_is_none() -> None:
    dc = _classify("docs/guide/01-x.md")
    assert dc.is_planning_doc is False
    assert dc.kind is DocKind.NONE


@pytest.mark.unit
def test_root_readme_is_none() -> None:
    dc = _classify("README.md")
    assert dc.is_planning_doc is False
    assert dc.kind is DocKind.NONE


@pytest.mark.unit
def test_non_markdown_is_none() -> None:
    # Even under a planning segment, a non-.md file is never a planning doc.
    dc = _classify("docs/specs/2026-06-08-x-design.txt")
    assert dc.is_planning_doc is False
    assert dc.kind is DocKind.NONE


# ----- managed location -----------------------------------------------------


@pytest.mark.unit
def test_context_proposal_is_none_and_managed() -> None:
    dc = _classify(".context/proposals/foo/spec.md")
    assert dc.is_planning_doc is False
    assert dc.kind is DocKind.NONE
    assert dc.in_managed_location is True


@pytest.mark.unit
def test_context_audit_is_managed() -> None:
    dc = _classify(".context/audits/foo/report.md")
    assert dc.is_planning_doc is False
    assert dc.in_managed_location is True


# ----- containment / errors -------------------------------------------------


@pytest.mark.unit
def test_path_outside_repo_raises_doc_path_error() -> None:
    with pytest.raises(DocPathError):
        classify_doc_path(ROOT, Path("/elsewhere/docs/specs/x-design.md"))


# ----- slug derivation ------------------------------------------------------


@pytest.mark.unit
def test_awkward_filename_slugifies_to_valid_slug() -> None:
    # A date-prefixed name with spaces/caps/punctuation slugifies to a value
    # that round-trips through validate_slug.
    dc = _classify("docs/plans/2026-06-08-Spaces & Caps!.md")
    assert dc.is_planning_doc is True
    assert dc.suggested_slug == "2026-06-08-spaces-caps"
    assert validate_slug(dc.suggested_slug) == dc.suggested_slug


@pytest.mark.unit
def test_unsluggable_filename_is_planning_but_has_no_slug() -> None:
    # A content-free stem (no alphanumerics) is a planning doc but unslug-able:
    # represented with suggested_slug/home = None, never raised.
    dc = _classify("docs/specs/___.md")
    assert dc.is_planning_doc is True
    assert dc.kind is DocKind.PROPOSAL
    assert dc.suggested_slug is None
    assert dc.suggested_home is None


# ----- pairing / grouping ---------------------------------------------------


@pytest.mark.unit
def test_pairing_design_and_plan_resolve_to_one_slug() -> None:
    # A dir with both x-design.md (spec) and x.md (plan) → exactly one group,
    # one slug, two roles. Noise paths (README, an out-of-docs design) are
    # filtered out, proving group_strays keeps only placeable strays.
    paths = [
        ROOT / "docs/specs/x-design.md",
        ROOT / "docs/specs/x.md",
        ROOT / "README.md",
        ROOT / "src/x-design.md",
    ]
    groups = group_strays(ROOT, paths)
    assert len(groups) == 1
    grp = groups[0]
    assert grp.slug == "x"
    assert grp.kind is DocKind.PROPOSAL
    assert grp.directory == "docs/specs"
    assert grp.spec_path == "docs/specs/x-design.md"
    assert grp.plan_path == "docs/specs/x.md"
    assert grp.collision is False


@pytest.mark.unit
def test_pairing_spec_only_pins_slug_and_file() -> None:
    groups = group_strays(ROOT, [ROOT / "docs/specs/x-design.md"])
    assert len(groups) == 1
    grp = groups[0]
    assert grp.slug == "x"
    assert grp.spec_path == "docs/specs/x-design.md"
    assert grp.plan_path is None


@pytest.mark.unit
def test_pairing_plan_only_pins_slug_and_file() -> None:
    groups = group_strays(ROOT, [ROOT / "docs/plans/x.md"])
    assert len(groups) == 1
    grp = groups[0]
    assert grp.slug == "x"
    assert grp.plan_path == "docs/plans/x.md"
    assert grp.spec_path is None


@pytest.mark.unit
def test_same_slug_in_different_dirs_is_disambiguated_and_reported() -> None:
    # Two strays in different dirs slugifying to the same base → the first
    # (deterministic sorted order) keeps the bare slug, the second is suffixed
    # and flagged as a collision.
    paths = [
        ROOT / "docs/specs/dup.md",
        ROOT / "docs/plans/dup.md",
    ]
    groups = group_strays(ROOT, paths)
    assert len(groups) == 2
    by_dir = {g.directory: g for g in groups}

    first = by_dir["docs/plans"]  # sorts before docs/specs
    assert first.slug == "dup"
    assert first.base_slug == "dup"
    assert first.collision is False

    second = by_dir["docs/specs"]
    assert second.slug == "dup-2"
    assert second.base_slug == "dup"
    assert second.collision is True
    assert second.suggested_home == ".context/proposals/dup-2"
