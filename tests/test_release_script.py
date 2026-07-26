"""Unit tests for the pure decision logic in ``scripts/release.py``.

Only the version-math + notes-rendering functions are tested — the git /
GitHub side effects live in the workflow. ``scripts/`` isn't on the path
(``testpaths = ["tests"]``), so load the module by file path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "release_script", Path(__file__).resolve().parent.parent / "scripts" / "release.py"
)
release = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(release)


# ----- commit_type ----------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject,expected",
    [
        ("feat: add x", ("feat", False)),
        ("fix(parser): handle y", ("fix", False)),
        ("feat!: drop z", ("feat", True)),
        ("refactor(io)!: rework", ("refactor", True)),
        ("not a conventional commit", (None, False)),
        ("Merge branch 'main'", (None, False)),
    ],
)
def test_commit_type(subject, expected):
    assert release.commit_type(subject) == expected


# ----- decide_bump ----------------------------------------------------------


@pytest.mark.unit
def test_feat_is_minor():
    assert release.decide_bump(["feat: a", "chore: b"], ["", ""]) == "minor"


@pytest.mark.unit
def test_fix_is_patch():
    assert release.decide_bump(["fix: a", "docs: b"], ["", ""]) == "patch"


@pytest.mark.unit
def test_feat_outranks_fix():
    assert release.decide_bump(["fix: a", "feat: b"], ["", ""]) == "minor"


@pytest.mark.unit
def test_breaking_bang_is_minor_pre_1_0():
    # bump-minor-pre-major: a breaking change stays a minor while 0.x.
    assert release.decide_bump(["fix(api)!: drop field"], [""]) == "minor"


@pytest.mark.unit
def test_breaking_footer_is_minor():
    bodies = ["BREAKING CHANGE: the config key was renamed"]
    assert release.decide_bump(["fix: a"], bodies) == "minor"


@pytest.mark.unit
def test_no_releasable_commits_returns_none():
    subjects = ["docs: a", "chore: b", "ci: c", "test: d", "refactor: e", "perf: f"]
    assert release.decide_bump(subjects, [""] * len(subjects)) is None


@pytest.mark.unit
def test_empty_returns_none():
    assert release.decide_bump([], []) is None


@pytest.mark.unit
def test_release_named_commit_forces_minor():
    # A commit/PR that names a release cuts a full (minor) release even when no
    # feat/fix is present — 0.30.0 -> 0.31.0.
    assert release.decide_bump(["chore: prep", "release: 0.31.0"], ["", ""]) == "minor"


@pytest.mark.unit
def test_release_named_pr_outranks_fix_only():
    # A merged `release-*` PR (its subject names the release) forces minor,
    # overriding a fix-only patch.
    assert release.decide_bump(["fix: a", "release-0.31.0"], ["", ""]) == "minor"


@pytest.mark.unit
def test_release_scope_forces_minor():
    assert release.decide_bump(["chore(release): v0.31.0"], [""]) == "minor"


@pytest.mark.unit
def test_release_signal_is_case_insensitive():
    assert release.decide_bump(["Release 0.31.0"], [""]) == "minor"


@pytest.mark.unit
def test_released_substring_does_not_trigger():
    # Only the whole word "release" is a signal — "released" in an ordinary
    # non-releasable commit must not force a release.
    assert release.decide_bump(["docs: tidy the released notes"], [""]) is None


# ----- next_version ---------------------------------------------------------


@pytest.mark.unit
def test_minor_bump_zeros_patch():
    assert release.next_version("0.24.3", "minor") == "0.25.0"


@pytest.mark.unit
def test_patch_bump():
    assert release.next_version("0.24.0", "patch") == "0.24.1"


@pytest.mark.unit
def test_unknown_bump_raises():
    with pytest.raises(ValueError):
        release.next_version("1.2.3", "major")


# ----- describe / render_notes ----------------------------------------------


@pytest.mark.unit
def test_describe_keeps_scope_drops_type():
    assert release.describe("feat(plan): annotate tasks") == "**plan:** annotate tasks"


@pytest.mark.unit
def test_describe_without_scope():
    assert release.describe("fix: handle empty input") == "handle empty input"


@pytest.mark.unit
def test_describe_passthrough_non_conventional():
    assert release.describe("Merge pull request #1") == "Merge pull request #1"


@pytest.mark.unit
def test_render_notes_groups_and_orders_sections():
    subjects = [
        "fix: b crash",
        "feat(ui): a button",
        "docs: c readme",
        "chore: hidden",
        "test: also hidden",
    ]
    notes = release.render_notes(subjects)
    # Sections present in render order; hidden types absent.
    assert (
        notes.index("### Added")
        < notes.index("### Fixed")
        < notes.index("### Documentation")
    )
    assert "**ui:** a button" in notes
    assert "- b crash" in notes
    assert "hidden" not in notes


@pytest.mark.unit
def test_render_notes_empty_is_maintenance():
    assert release.render_notes(["chore: x"]) == "Maintenance release."


# ----- squashed_subjects / effective_subjects -------------------------------
#
# GitHub's "Squash and merge" collapses a branch into one commit whose *subject*
# is the PR title — which defaults to the branch name, e.g. the un-conventional
# `Feat/curated codebase scan (#10)`. The real conventional commits survive only
# as `* `-prefixed bullets in the body. Reading the subject alone silently
# skipped the release for PRs #9 and #10 (v0.34.0 was never cut).


@pytest.mark.unit
def test_squashed_subjects_recovers_bullets():
    body = "* feat(scan): add curated scan\n* fix(viewer): survive SVG failure\n"
    assert release.squashed_subjects(body) == [
        "feat(scan): add curated scan",
        "fix(viewer): survive SVG failure",
    ]


@pytest.mark.unit
def test_squashed_subjects_ignores_non_conventional_bullets():
    # GitHub bullets every squashed commit, including un-conventional ones.
    body = "* Update INDEX.md with confidence adjustments\n* feat: add plugins\n"
    assert release.squashed_subjects(body) == ["feat: add plugins"]


@pytest.mark.unit
def test_squashed_subjects_ignores_hyphen_prose_bullets():
    # Prose inside a commit message uses `- `; only GitHub's `* ` bullets are
    # commit subjects. Without this split, a body's own changelog-ish prose
    # would inflate the release notes.
    body = "* feat: real commit\n\nDetails:\n- docs: document --platform agents\n"
    assert release.squashed_subjects(body) == ["feat: real commit"]


@pytest.mark.unit
def test_squashed_subjects_empty_body():
    assert release.squashed_subjects("") == []


@pytest.mark.unit
def test_effective_subjects_expands_non_conventional_subject():
    commits = [("Feat/curated codebase scan (#10)", "* feat(scan): add scan\n")]
    assert release.effective_subjects(commits) == [
        "Feat/curated codebase scan (#10)",
        "feat(scan): add scan",
    ]


@pytest.mark.unit
def test_effective_subjects_keeps_conventional_subject_authoritative():
    # A maintainer-written conventional PR title already describes the squash;
    # expanding it too would duplicate every line in the changelog.
    commits = [("feat(codex): add Codex support", "* feat(a): x\n* fix(b): y\n")]
    assert release.effective_subjects(commits) == ["feat(codex): add Codex support"]


@pytest.mark.unit
def test_squash_merged_feature_pr_releases_minor():
    """The exact regression: PRs #9/#10 landed on main and cut no release."""
    commits = [
        ("Feat/curated codebase scan (#10)", "* feat(context): curated scan\n"),
        ("Feat/universal harness support (#9)", "* fix: unpin default plugins\n"),
    ]
    subjects = release.effective_subjects(commits)
    assert release.decide_bump(subjects, [b for _, b in commits]) == "minor"


@pytest.mark.unit
def test_squash_merged_fix_only_pr_releases_patch():
    commits = [("Fix/pointer capture (#11)", "* fix(viewer): defer capture\n")]
    subjects = release.effective_subjects(commits)
    assert release.decide_bump(subjects, [""]) == "patch"


@pytest.mark.unit
def test_squash_merged_chore_only_pr_still_skips_release():
    # The guard must stay one-way: recovering bullets must not turn a
    # genuinely non-releasable PR into a release.
    commits = [("Chore/tidy imports (#12)", "* chore: sort imports\n* test: add\n")]
    subjects = release.effective_subjects(commits)
    assert release.decide_bump(subjects, [""]) is None


@pytest.mark.unit
def test_squashed_notes_describe_the_work_not_the_branch_name():
    commits = [("Feat/curated codebase scan (#10)", "* feat(context): curated scan\n")]
    notes = release.render_notes(release.effective_subjects(commits))
    assert "**context:** curated scan" in notes
    # The branch-name subject is un-conventional, so it never reaches a section.
    assert "Feat/curated" not in notes
