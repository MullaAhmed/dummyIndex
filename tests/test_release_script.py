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
