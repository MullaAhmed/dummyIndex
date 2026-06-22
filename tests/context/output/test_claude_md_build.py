"""Integration: the real build / install paths consolidate a root CLAUDE.md.

The audit's HIGH bug was that a pre-existing ``<root>/CLAUDE.md`` was left
dangling because neither real build path folded it into the managed setup.
These tests drive the actual seams — ``build_all(bootstrap=True)``, the context
``init`` dispatch, and the installer's ``_auto_init_project`` (including its
``status.enriched`` re-install branch) — over a copied ``SAMPLE_REPO`` and
assert the unified "fold → single canonical file" end state:

  * root ``./CLAUDE.md`` is gone, and
  * a single ``.claude/CLAUDE.md`` carries the user's text + exactly ONE
    managed block.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.build.runner import build_all
from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER
from dummyindex.installer.install import _auto_init_project

SAMPLE_REPO = Path(__file__).resolve().parent.parent.parent / "fixtures" / "sample_repo"

USER_BODY = "# Project notes\n\nHand-written house rules that must survive.\n"


def _seed_repo(tmp_path: Path, name: str) -> Path:
    """Copy the pristine SAMPLE_REPO into tmp_path so we never mutate it."""
    target = tmp_path / name
    shutil.copytree(SAMPLE_REPO, target)
    return target


def _plain_root_claude() -> str:
    """A root CLAUDE.md with only user content — no managed block."""
    return USER_BODY


def _managed_root_claude() -> str:
    """A root CLAUDE.md with user content wrapped around a legacy managed block."""
    return (
        f"{USER_BODY}\n"
        f"{BEGIN_MARKER}\nstale managed body\n{END_MARKER}\n\n"
        "More user content below the block.\n"
    )


def _assert_consolidated(target: Path) -> str:
    """Assert the unified end state and return the canonical file's text."""
    root = target / "CLAUDE.md"
    canonical = target / ".claude" / "CLAUDE.md"

    assert not root.exists(), (
        "root ./CLAUDE.md should be consolidated away, got leftover:\n"
        f"{root.read_text(encoding='utf-8') if root.exists() else '(removed)'}"
    )
    assert canonical.exists(), ".claude/CLAUDE.md should exist after the build"

    text = canonical.read_text(encoding="utf-8")
    # Exactly one managed block.
    assert text.count(BEGIN_MARKER) == 1, f"expected one BEGIN marker, got:\n{text}"
    assert text.count(END_MARKER) == 1, f"expected one END marker, got:\n{text}"
    # The user's hand-written content survived.
    assert "Hand-written house rules that must survive." in text
    return text


@pytest.mark.integration
@pytest.mark.parametrize(
    "root_factory",
    [_plain_root_claude, _managed_root_claude],
    ids=["plain-user-content", "legacy-managed-block"],
)
def test_build_all_consolidates_root_claude_md(tmp_path, root_factory) -> None:
    """``build_all(bootstrap=True)`` folds a seeded root CLAUDE.md."""
    target = _seed_repo(tmp_path, "build_all_target")
    (target / "CLAUDE.md").write_text(root_factory(), encoding="utf-8")

    build_all(
        target,
        out_root=target,
        bootstrap=True,
        dummyindex_version="9.9.9",
    )

    text = _assert_consolidated(target)
    # The stale legacy block body must not survive — only the fresh block.
    assert "stale managed body" not in text


@pytest.mark.integration
@pytest.mark.parametrize(
    "root_factory",
    [_plain_root_claude, _managed_root_claude],
    ids=["plain-user-content", "legacy-managed-block"],
)
def test_init_dispatch_consolidates_root_claude_md(tmp_path, root_factory) -> None:
    """The context ``init`` dispatch folds a seeded root CLAUDE.md."""
    target = _seed_repo(tmp_path, "init_dispatch_target")
    (target / "CLAUDE.md").write_text(root_factory(), encoding="utf-8")

    rc = dispatch(["init", str(target)])
    assert rc == 0

    text = _assert_consolidated(target)
    assert "stale managed body" not in text


def _make_enriched_context(target: Path) -> None:
    """Seed a minimal *enriched* .context/ so ``status.enriched`` is True.

    ``enriched_index_status`` reads ``features/INDEX.json`` OR scans the
    per-feature dirs on disk: any feature dir whose id is NOT ``community-*``
    proves curation survived. We create one such dir — the minimal real state
    that drives the ``status.enriched`` branch of ``_auto_init_project`` without
    monkeypatching the branch.
    """
    feature_dir = target / ".context" / "features" / "auth-flow"
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature.json").write_text(
        '{"feature_id": "auth-flow", "confidence": "INFERRED"}\n',
        encoding="utf-8",
    )


@pytest.mark.integration
def test_enriched_reinstall_consolidates_dangling_root_claude_md(tmp_path) -> None:
    """The ``status.enriched`` re-install branch also consolidates the root file.

    This is the HIGH bug: the enriched-preserved branch of
    ``_auto_init_project`` previously bootstrapped ``.claude/CLAUDE.md`` directly
    and never touched a dangling root ``./CLAUDE.md``. We reach the branch with
    real on-disk state (a curated feature dir), assert it is actually taken, then
    assert the root file is consolidated away.
    """
    target = _seed_repo(tmp_path, "enriched_reinstall_target")

    # First build an index, then upgrade it into an "enriched" state on disk.
    build_all(
        target,
        out_root=target,
        bootstrap=False,
        dummyindex_version="9.9.9",
    )
    _make_enriched_context(target)

    # Confirm we will actually exercise the enriched branch (not the full build).
    from dummyindex.context.build import enriched_index_status

    status = enriched_index_status(target / ".context")
    assert status.enriched is True, (
        "test setup failed to reach the status.enriched branch"
    )

    # Seed a dangling root CLAUDE.md (with user content) that the buggy branch
    # would have ignored.
    (target / "CLAUDE.md").write_text(_plain_root_claude(), encoding="utf-8")

    ok = _auto_init_project(target, no_superpowers=True)
    assert ok is True

    _assert_consolidated(target)


@pytest.mark.integration
def test_enriched_reinstall_merges_existing_canonical_without_duplication(
    tmp_path,
) -> None:
    """Enriched re-install merges an existing canonical body + root, no dupes."""
    target = _seed_repo(tmp_path, "enriched_merge_target")
    build_all(
        target,
        out_root=target,
        bootstrap=False,
        dummyindex_version="9.9.9",
    )
    _make_enriched_context(target)

    # Existing canonical already holds user content + a managed block.
    canonical = target / ".claude" / "CLAUDE.md"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(
        f"# Canonical notes\n\nExisting canonical content.\n\n"
        f"{BEGIN_MARKER}\nold body\n{END_MARKER}\n",
        encoding="utf-8",
    )
    # And a dangling root file with distinct user content.
    (target / "CLAUDE.md").write_text(_plain_root_claude(), encoding="utf-8")

    ok = _auto_init_project(target, no_superpowers=True)
    assert ok is True

    assert not (target / "CLAUDE.md").exists()
    text = canonical.read_text(encoding="utf-8")
    assert text.count(BEGIN_MARKER) == 1
    assert text.count(END_MARKER) == 1
    # Both bodies present, neither duplicated.
    assert text.count("Existing canonical content.") == 1
    assert text.count("Hand-written house rules that must survive.") == 1
    assert "old body" not in text
