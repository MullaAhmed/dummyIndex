"""Tests for dummyindex.context.output.claude_md — reconcile_claude_md.

Covers every branch of the single-seam CLAUDE.md reconciliation helper:
plain/legacy/whitespace residue, pre-existing canonical merge, idempotency,
inode-shared single file, unbalanced + duplicate markers, prose that quotes
the marker substrings, an unreadable root, and an injected write failure.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from dummyindex.context.output import claude_md as claude_md_mod
from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER
from dummyindex.context.output.claude_md import (
    ClaudeMdAction,
    reconcile_claude_md,
)


def _block_count(text: str) -> int:
    """Number of standalone managed blocks (whole-line BEGIN markers)."""
    return sum(1 for line in text.split("\n") if line.strip() == BEGIN_MARKER)


def _legacy_block() -> str:
    """A complete managed block as written by bootstrap (markers on own lines)."""
    return f"{BEGIN_MARKER}\nlegacy body\n{END_MARKER}"


def _canonical(tmp_path: Path) -> Path:
    return tmp_path / ".claude" / "CLAUDE.md"


def _root(tmp_path: Path) -> Path:
    return tmp_path / "CLAUDE.md"


# --------------------------------------------------------------------------
# Branch: root has a managed block + user residue → consolidate into canonical
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_root_block_plus_residue_consolidates(tmp_path: Path) -> None:
    root = _root(tmp_path)
    root.write_text(
        f"# My notes\n\nKeep me.\n\n{_legacy_block()}\n", encoding="utf-8"
    )

    result = reconcile_claude_md(tmp_path)

    canonical = _canonical(tmp_path)
    assert result.action == ClaudeMdAction.CONSOLIDATED
    assert not root.exists()
    text = canonical.read_text(encoding="utf-8")
    assert "Keep me." in text
    assert "legacy body" not in text  # old block stripped
    assert _block_count(text) == 1  # exactly ONE fresh managed block


# --------------------------------------------------------------------------
# Branch: root has ONLY a managed block (whitespace residue) → one block
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_root_block_only_whitespace_residue(tmp_path: Path) -> None:
    root = _root(tmp_path)
    root.write_text(f"\n\n{_legacy_block()}\n\n  \n", encoding="utf-8")

    result = reconcile_claude_md(tmp_path)

    canonical = _canonical(tmp_path)
    assert result.action == ClaudeMdAction.CONSOLIDATED
    assert not root.exists()
    text = canonical.read_text(encoding="utf-8")
    assert _block_count(text) == 1
    assert "legacy body" not in text


# --------------------------------------------------------------------------
# Branch: root is plain user content, no block → consolidated, text preserved
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_root_plain_user_content_no_block(tmp_path: Path) -> None:
    root = _root(tmp_path)
    root.write_text("# Project rules\n\nAlways be kind.\n", encoding="utf-8")

    result = reconcile_claude_md(tmp_path)

    canonical = _canonical(tmp_path)
    assert result.action == ClaudeMdAction.CONSOLIDATED
    assert not root.exists()
    text = canonical.read_text(encoding="utf-8")
    assert "# Project rules" in text
    assert "Always be kind." in text
    assert _block_count(text) == 1


# --------------------------------------------------------------------------
# Branch: pre-existing canonical (user + block) AND a root file → merge, no dup
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_merge_existing_canonical_and_root_no_duplication(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(
        f"Canonical user note.\n\n{_legacy_block()}\n", encoding="utf-8"
    )
    root = _root(tmp_path)
    root.write_text("Root user note.\n", encoding="utf-8")

    result = reconcile_claude_md(tmp_path)

    assert result.action == ClaudeMdAction.CONSOLIDATED
    assert not root.exists()
    text = canonical.read_text(encoding="utf-8")
    assert "Canonical user note." in text
    assert "Root user note." in text
    # No duplication of either body, and exactly one managed block.
    assert text.count("Canonical user note.") == 1
    assert text.count("Root user note.") == 1
    assert _block_count(text) == 1


# --------------------------------------------------------------------------
# Branch: idempotent second run → noop, byte-identical canonical
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_idempotent_second_run_is_noop(tmp_path: Path) -> None:
    root = _root(tmp_path)
    root.write_text("# Notes\n\nStable text.\n", encoding="utf-8")

    first = reconcile_claude_md(tmp_path)
    assert first.action == ClaudeMdAction.CONSOLIDATED
    canonical = _canonical(tmp_path)
    after_first = canonical.read_text(encoding="utf-8")

    second = reconcile_claude_md(tmp_path)
    assert second.action == ClaudeMdAction.NOOP
    assert canonical.read_text(encoding="utf-8") == after_first  # byte-identical


# --------------------------------------------------------------------------
# Branch: inode/symlink — root and canonical are the same file
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_inode_shared_file_not_consolidated_or_deleted(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(
        f"Shared user note.\n\n{_legacy_block()}\n", encoding="utf-8"
    )
    root = _root(tmp_path)
    try:
        os.symlink(canonical, root)
    except (OSError, NotImplementedError):  # pragma: no cover
        os.link(canonical, root)  # fall back to hardlink

    result = reconcile_claude_md(tmp_path)

    assert result.action in (ClaudeMdAction.NOOP, ClaudeMdAction.UPDATED)
    # File survives intact — never deleted, user content preserved, one block.
    assert root.exists()
    assert canonical.exists()
    text = canonical.read_text(encoding="utf-8")
    assert "Shared user note." in text
    assert _block_count(text) == 1


# --------------------------------------------------------------------------
# Branch: unbalanced markers in ROOT → no raise, degrades to NOOP, root intact
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_unbalanced_markers_in_root_degrades_to_noop(tmp_path: Path) -> None:
    root = _root(tmp_path)
    # A BEGIN line with no closing END line → unbalanced.
    root.write_text(f"# Notes\n\n{BEGIN_MARKER}\ndangling block\n", encoding="utf-8")

    result = reconcile_claude_md(tmp_path)  # must not raise

    assert result.action == ClaudeMdAction.NOOP
    assert result.warnings  # a warning is recorded
    assert root.exists()  # root left untouched
    assert not _canonical(tmp_path).exists()  # nothing written


# --------------------------------------------------------------------------
# Branch: unbalanced markers in CANONICAL → no raise, degrades to NOOP
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_unbalanced_markers_in_canonical_degrades_to_noop(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(f"{END_MARKER}\norphan end\n", encoding="utf-8")
    root = _root(tmp_path)
    root.write_text("Root note.\n", encoding="utf-8")

    result = reconcile_claude_md(tmp_path)  # must not raise

    assert result.action == ClaudeMdAction.NOOP
    assert result.warnings
    assert root.exists()  # root left untouched on degraded canonical


# --------------------------------------------------------------------------
# Branch: DUPLICATE (balanced) blocks → strip all, emit exactly one
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_duplicate_balanced_blocks_collapse_to_one(tmp_path: Path) -> None:
    root = _root(tmp_path)
    block = _legacy_block()
    root.write_text(
        f"User text.\n\n{block}\n\nmore user text.\n\n{block}\n", encoding="utf-8"
    )

    result = reconcile_claude_md(tmp_path)  # balanced (2 begin / 2 end) → proceeds

    assert result.action == ClaudeMdAction.CONSOLIDATED
    assert not root.exists()
    text = _canonical(tmp_path).read_text(encoding="utf-8")
    assert _block_count(text) == 1  # all stripped, exactly one re-emitted
    assert "User text." in text
    assert "more user text." in text
    assert "legacy body" not in text


# --------------------------------------------------------------------------
# Branch: user prose literally quotes the marker substrings mid-line
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_prose_quoting_markers_preserved_and_idempotent(tmp_path: Path) -> None:
    root = _root(tmp_path)
    # Markers embedded mid-line in prose — NOT standalone marker lines.
    prose = (
        f"We use a marker like `{BEGIN_MARKER}` inline and `{END_MARKER}` too.\n"
    )
    root.write_text(f"# Docs\n\n{prose}", encoding="utf-8")

    result = reconcile_claude_md(tmp_path)

    assert result.action == ClaudeMdAction.CONSOLIDATED
    canonical = _canonical(tmp_path)
    text = canonical.read_text(encoding="utf-8")
    assert prose.strip() in text  # quoted markers preserved verbatim
    assert _block_count(text) == 1  # the inline quotes are NOT counted as a block

    after_first = text
    second = reconcile_claude_md(tmp_path)  # idempotent second run
    assert second.action == ClaudeMdAction.NOOP
    assert canonical.read_text(encoding="utf-8") == after_first


# --------------------------------------------------------------------------
# Branch: OSError reading the root (root is a directory) → warning, no crash
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_unreadable_root_degrades_to_warning(tmp_path: Path) -> None:
    # Make the root path a directory so read_text raises OSError portably.
    root = _root(tmp_path)
    root.mkdir(parents=True)

    result = reconcile_claude_md(tmp_path)  # must not raise

    assert result.action == ClaudeMdAction.NOOP
    assert result.warnings
    assert root.exists()  # directory (root) left untouched
    assert not _canonical(tmp_path).exists()


# --------------------------------------------------------------------------
# Branch: injected canonical write failure → root intact, non-fatal warning
# --------------------------------------------------------------------------
@pytest.mark.unit
def test_injected_write_failure_leaves_root_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    root.write_text("# Notes\n\nImportant user content.\n", encoding="utf-8")

    def _boom(path: Path, content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(claude_md_mod, "write_text_atomic", _boom)

    result = reconcile_claude_md(tmp_path)  # must not raise

    assert result.action == ClaudeMdAction.NOOP
    assert result.warnings
    assert root.exists()  # root left intact when canonical write failed
    assert "Important user content." in root.read_text(encoding="utf-8")
    assert not _canonical(tmp_path).exists()
