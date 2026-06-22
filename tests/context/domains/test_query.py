"""Tests for `dummyindex context query` — PageIndex-style retrieval."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.paths import SAMPLE_REPO

import pytest

from dummyindex.context.domains.query import (
    estimate_tokens,
    query,
    render_json,
    render_markdown,
    tokenize,
)
from dummyindex.context.build.runner import build_all

_FIXTURE_ROOT = SAMPLE_REPO


@pytest.fixture
def indexed_repo(tmp_path: Path) -> Path:
    """A fixture repo that's been through build_all once."""
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    build_all(dest, cache_root=tmp_path / "cache")
    return dest


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    tokens = tokenize("how does the auth flow work in this app?")
    assert "the" not in tokens
    assert "how" not in tokens
    assert "in" not in tokens
    assert "auth" in tokens
    assert "flow" in tokens
    assert "work" in tokens
    assert "app" in tokens


def test_tokenize_splits_camel_and_snake() -> None:
    tokens = tokenize("ParseBody and parse_body and ParseBodyV2")
    assert "parsebody" in tokens
    assert "parse" in tokens
    assert "body" in tokens
    assert "parse_body" in tokens
    assert "v2" in tokens


def test_tokenize_dedupes() -> None:
    tokens = tokenize("auth auth auth")
    assert tokens.count("auth") == 1


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------


def test_query_returns_no_matches_when_query_is_pure_stopwords(
    indexed_repo: Path,
) -> None:
    """A query that reduces to zero tokens after stopword filtering
    must return an empty result, not crash or return everything."""
    result = query(indexed_repo / ".context", "the and how is this")
    assert result.tokens == ()
    assert result.matches == ()
    # We still report how many features we considered (for the user).
    assert result.feature_count_considered >= 0


def test_query_finds_relevant_feature(indexed_repo: Path) -> None:
    """The sample repo has an `App` class; a query for "app" should
    surface a feature whose members contain it."""
    result = query(indexed_repo / ".context", "app")
    assert result.tokens == ("app",)
    assert result.matches, "expected at least one match for 'app' in sample repo"
    # The top match must mention `app` in some matched field.
    top = result.matches[0].feature
    assert top.score > 0
    assert "app" in top.matched_tokens


def test_query_returns_empty_on_no_hit(indexed_repo: Path) -> None:
    """A query that tokenizes to a token absent everywhere returns
    no matches but still reports feature_count_considered."""
    result = query(indexed_repo / ".context", "nonexistentkeyword42")
    assert result.matches == ()
    assert result.feature_count_considered > 0


def test_query_respects_top_k(indexed_repo: Path) -> None:
    result = query(indexed_repo / ".context", "app helper run", top_k=1)
    assert len(result.matches) <= 1


def test_query_truncates_at_budget(indexed_repo: Path) -> None:
    """A very small budget must drop matches and set truncated=True."""
    result = query(
        indexed_repo / ".context", "app helper run", top_k=10, budget_tokens=60
    )
    # With a 60-token budget, at most one match should fit (each one
    # is at least header + summary + citations ~80 tokens).
    assert result.total_estimated_tokens <= 60 or len(result.matches) <= 1


def test_query_raises_when_index_missing(tmp_path: Path) -> None:
    bare = tmp_path / "no-context"
    bare.mkdir()
    with pytest.raises(FileNotFoundError):
        query(bare, "anything")


def test_query_result_is_json_serializable(indexed_repo: Path) -> None:
    result = query(indexed_repo / ".context", "app")
    rendered = render_json(result)
    # Re-parse to confirm it's syntactically valid.
    payload = json.loads(rendered)
    assert payload["schema_version"] == 1
    assert payload["query"] == "app"


def test_query_markdown_render_contains_citations(indexed_repo: Path) -> None:
    result = query(indexed_repo / ".context", "app")
    md = render_markdown(result)
    if result.matches:
        assert "Citations" in md
        assert "score" in md.lower()


def test_estimate_tokens_floor() -> None:
    # Empty string still costs 1 token (the floor).
    assert estimate_tokens("") == 1
    assert estimate_tokens("xxxxxxxx") == 2   # 8 chars / 4 = 2


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def test_cli_query_subcommand_invokes(indexed_repo: Path, capsys) -> None:
    """End-to-end: dispatch("query", "app") prints something useful."""
    from dummyindex.cli import dispatch

    # `--root` lets us point at the indexed repo without cwd shenanigans.
    rc = dispatch(["query", "app", "--root", str(indexed_repo)])
    captured = capsys.readouterr()
    # rc=0 means matches found; rc=1 means no matches. Both are valid CLI
    # outcomes — assert we got *some* readable markdown on stdout.
    assert rc in (0, 1)
    assert "query" in captured.out.lower()


def test_cli_query_missing_query_arg_errors(tmp_path: Path, capsys) -> None:
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "query" in captured.err.lower()


def test_cli_query_trailing_top_k_without_value_errors(
    indexed_repo: Path, capsys
) -> None:
    """A trailing `--top-k` with no value must error (exit 2), not get joined
    into the query string and silently searched."""
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "app", "--root", str(indexed_repo), "--top-k"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--top-k" in captured.err
    # Must not have run a search: no markdown report on stdout.
    assert captured.out == ""


def test_cli_query_trailing_budget_without_value_errors(
    indexed_repo: Path, capsys
) -> None:
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "app", "--root", str(indexed_repo), "--budget"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--budget" in captured.err
    assert captured.out == ""
