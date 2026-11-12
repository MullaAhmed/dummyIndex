"""Tests for ``domains/restyle/snapshot.py`` (protected tokens and their diff)."""

from __future__ import annotations

import pytest

from dummyindex.context.domains.docguard.citations import citations
from dummyindex.context.domains.restyle.errors import TokenLossError
from dummyindex.context.domains.restyle.snapshot import (
    assert_tokens_kept,
    diff_tokens,
    protected_tokens,
)

BASE = (
    "# Title\n\n"
    "See `dummyindex/x.py:12` for the rule. It lists 3 steps.\n\n"
    "Run this:\n\n```\nprint(1)\n```\n\n"
    "Do not skip it. It must pass. Use [docs](docs/a.md).\n"
)


@pytest.mark.unit
def test_contraction_expansion_keeps_negation_count():
    old = "Don't skip the check."
    new = "Do not skip the check."
    diff = diff_tokens(old, new)
    assert diff.lost == ()
    assert diff.added == ()


@pytest.mark.unit
def test_lost_path_line_citation_fails_and_is_named():
    new = BASE.replace("`dummyindex/x.py:12`", "`dummyindex/x.py`")
    diff = diff_tokens(BASE, new)
    assert "dummyindex/x.py:12" in diff.lost
    with pytest.raises(TokenLossError, match=r"dummyindex/x\.py:12"):
        assert_tokens_kept(BASE, new)


@pytest.mark.unit
def test_lost_numeral_fails_and_is_named():
    new = BASE.replace("3 steps", "several steps")
    diff = diff_tokens(BASE, new)
    assert "3" in diff.lost
    with pytest.raises(TokenLossError, match=r"\b3\b"):
        assert_tokens_kept(BASE, new)


@pytest.mark.unit
def test_lost_negation_fails_and_is_named():
    new = BASE.replace("Do not skip it.", "Check it.")
    diff = diff_tokens(BASE, new)
    assert "not" in diff.lost
    with pytest.raises(TokenLossError, match=r"\bnot\b"):
        assert_tokens_kept(BASE, new)


@pytest.mark.unit
def test_added_inline_code_warns_without_failing():
    new = BASE + "\nAlso `new_helper()` is used.\n"
    diff = diff_tokens(BASE, new)
    assert diff.lost == ()
    assert "new_helper()" in diff.added
    assert assert_tokens_kept(BASE, new) == ("new_helper()",)


@pytest.mark.unit
def test_heading_level_change_fails():
    new = BASE.replace("# Title", "## Title")
    assert "#" in diff_tokens(BASE, new).lost


@pytest.mark.unit
def test_fenced_block_and_link_target_are_protected():
    new = BASE.replace("print(1)", "print(2)").replace("docs/a.md", "docs/b.md")
    lost = diff_tokens(BASE, new).lost
    assert "docs/a.md" in lost
    assert "print(1)" in lost


@pytest.mark.unit
def test_protected_tokens_returns_counter_of_negations():
    tokens = protected_tokens("no, never, not, only, must, cannot")
    for word in ("no", "never", "not", "only", "must", "cannot"):
        assert tokens[word] == 1


@pytest.mark.unit
def test_public_citations_wraps_regex():
    assert citations("see proposals/foo-bar/spec.md") == {"proposals/foo-bar/"}
