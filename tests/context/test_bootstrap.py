"""Tests for dummyindex.context.bootstrap — CLAUDE.md managed-block writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.bootstrap import (
    BEGIN_MARKER,
    END_MARKER,
    UnbalancedMarkersError,
    bootstrap_claude_md,
    generate_managed_block,
)


def _wrote_block(content: str) -> bool:
    return BEGIN_MARKER in content and END_MARKER in content


def _block_span(content: str) -> tuple[int, int]:
    begin = content.index(BEGIN_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)
    return begin, end


@pytest.mark.unit
def test_creates_file_when_missing(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    assert not claude_md.exists()
    result = bootstrap_claude_md(claude_md)
    assert claude_md.exists()
    assert result == claude_md.read_text(encoding="utf-8")
    assert _wrote_block(result)
    assert result.endswith("\n")


@pytest.mark.unit
def test_appends_to_existing_without_block(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# My project\n\nExisting content here.\n", encoding="utf-8")
    bootstrap_claude_md(claude_md)
    final = claude_md.read_text(encoding="utf-8")
    assert "# My project" in final
    assert "Existing content here." in final
    assert _wrote_block(final)
    # Block should come AFTER existing content
    assert final.index("# My project") < final.index(BEGIN_MARKER)


@pytest.mark.unit
def test_replaces_existing_block_in_place(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    initial = bootstrap_claude_md(claude_md)
    assert _wrote_block(initial)
    second = bootstrap_claude_md(claude_md)
    assert second == initial  # idempotent


@pytest.mark.unit
def test_replaces_block_when_content_changes(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    bootstrap_claude_md(claude_md, block_body="# OLD")
    bootstrap_claude_md(claude_md, block_body="# NEW")
    final = claude_md.read_text(encoding="utf-8")
    assert "# NEW" in final
    assert "# OLD" not in final
    assert final.count(BEGIN_MARKER) == 1
    assert final.count(END_MARKER) == 1


@pytest.mark.unit
def test_block_in_middle_preserves_surrounding_content(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    block = f"{BEGIN_MARKER}\nOLD BODY\n{END_MARKER}"
    claude_md.write_text(
        f"# Heading\n\nBefore block.\n\n{block}\n\nAfter block.\n",
        encoding="utf-8",
    )
    bootstrap_claude_md(claude_md, block_body="NEW BODY")
    final = claude_md.read_text(encoding="utf-8")
    assert "Before block." in final
    assert "After block." in final
    assert "NEW BODY" in final
    assert "OLD BODY" not in final
    assert final.count(BEGIN_MARKER) == 1


@pytest.mark.unit
def test_raises_on_unbalanced_begin_without_end(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(f"# Project\n\n{BEGIN_MARKER}\nNo end here.\n", encoding="utf-8")
    with pytest.raises(UnbalancedMarkersError, match="begin marker"):
        bootstrap_claude_md(claude_md)


@pytest.mark.unit
def test_raises_on_end_without_begin(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(f"# Project\n\n{END_MARKER}\nNo begin.\n", encoding="utf-8")
    with pytest.raises(UnbalancedMarkersError, match="end marker"):
        bootstrap_claude_md(claude_md)


@pytest.mark.unit
def test_raises_on_duplicate_blocks(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    block = f"{BEGIN_MARKER}\nbody\n{END_MARKER}"
    claude_md.write_text(f"{block}\n\nsome content\n\n{block}\n", encoding="utf-8")
    with pytest.raises(UnbalancedMarkersError, match="dummyindex managed blocks"):
        bootstrap_claude_md(claude_md)


@pytest.mark.unit
def test_atomic_write_no_tmp_remains(tmp_path: Path) -> None:
    claude_md = tmp_path / "CLAUDE.md"
    bootstrap_claude_md(claude_md)
    assert not list(tmp_path.glob("CLAUDE.md.tmp"))


@pytest.mark.unit
def test_generated_block_is_short_pointer() -> None:
    """The managed block is a 3-line pointer at .context/HOW_TO_USE.md.
    Detailed navigation lives in HOW_TO_USE.md, not duplicated here."""
    body = generate_managed_block()
    assert ".context/HOW_TO_USE.md" in body
    assert "dummyindex context rebuild --changed" in body
    # Must stay small — duplicating navigation rules in CLAUDE.md was the bug
    # the shrink fixed. Be generous with the cap but enforce a ceiling.
    assert len(body.splitlines()) <= 10, (
        f"managed block is {len(body.splitlines())} lines; should stay terse"
    )


@pytest.mark.unit
def test_create_in_nonexistent_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "fresh" / "repo" / "CLAUDE.md"
    bootstrap_claude_md(nested)
    assert nested.exists()
    assert _wrote_block(nested.read_text(encoding="utf-8"))
