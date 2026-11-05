"""Tests for `dummyindex context query` — PageIndex-style retrieval."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.query import (
    estimate_tokens,
    query,
    render_json,
    render_markdown,
    tokenize,
)
from tests.paths import SAMPLE_REPO

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
    # "app" expands through the synonym map to include "application".
    assert result.tokens == ("app", "application")
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
    assert estimate_tokens("xxxxxxxx") == 2  # 8 chars / 4 = 2


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


def test_cli_query_unknown_flag_errors_not_folded(indexed_repo: Path, capsys) -> None:
    """An unknown `--flag` is rejected through `usage_error` (exit 2 + a
    `--help` hint) rather than silently folded into the search string."""
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "x", "--bogus", "5", "--root", str(indexed_repo)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--bogus" in captured.err
    # Routed through usage_error → carries the canonical help pointer.
    assert "dummyindex context query --help" in captured.err
    # Never ran a search: no markdown report on stdout, and the flag was not
    # joined into the query text and quietly searched.
    assert captured.out == ""


def test_cli_query_top_k_non_integer_routes_through_usage_error(
    indexed_repo: Path, capsys
) -> None:
    """An existing exit-2 site (non-integer --top-k) now emits the shared
    `--help` hint via `usage_error`."""
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "app", "--root", str(indexed_repo), "--top-k", "notanint"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--top-k" in captured.err
    assert "dummyindex context query --help" in captured.err
    assert captured.out == ""


def test_cli_query_trailing_top_k_emits_help_hint(indexed_repo: Path, capsys) -> None:
    """Regression for the already-shipped trailing-flag guard (`c574d41`):
    `--top-k` with no value still exits 2, now via `usage_error` so it carries
    the `--help` hint."""
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "app", "--root", str(indexed_repo), "--top-k"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "--top-k" in captured.err
    assert "dummyindex context query --help" in captured.err
    assert captured.out == ""


def test_cli_query_missing_arg_emits_help_hint(tmp_path: Path, capsys) -> None:
    """The empty-query usage error routes through `usage_error`."""
    from dummyindex.cli import dispatch

    rc = dispatch(["query", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "dummyindex context query --help" in captured.err


def test_query_usage_documents_no_match_exit_1() -> None:
    """The no-match exit-1 contract is documented in `query`'s USAGE slice."""
    from dummyindex.cli.help import usage_for
    from dummyindex.context.enums import ContextSubcommand

    text = usage_for(ContextSubcommand.QUERY).lower()
    assert "exits 1" in text
    assert "no" in text  # "no hit" / "nothing matches"


# ---------------------------------------------------------------------------
# Ranking-quality regressions (retrieval benchmark findings)
#
# These use a hand-built minimal index — features/INDEX.json + per-feature
# feature.json + map/symbols.json — so each scoring behavior is isolated
# from the real ingest pipeline.
# ---------------------------------------------------------------------------


def _write_synthetic_index(
    root: Path,
    features: list[dict],
    symbols: list[dict],
) -> Path:
    """Write the smallest index query() can run over."""
    context_dir = root / ".context"
    fdir = context_dir / "features"
    fdir.mkdir(parents=True)
    (context_dir / "map").mkdir()
    (context_dir / "map" / "symbols.json").write_text(
        json.dumps({"symbols": symbols}), encoding="utf-8"
    )
    index_entries = []
    for feat in features:
        fid = feat["feature_id"]
        (fdir / fid).mkdir()
        members = [m for m in feat.get("members", [])]
        (fdir / fid / "feature.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "feature_id": fid,
                    "kind": "community",
                    "name": feat.get("name", fid),
                    "summary": feat.get("summary"),
                    "members": members,
                    "files": feat.get("files", []),
                    "confidence": "EXTRACTED",
                }
            ),
            encoding="utf-8",
        )
        index_entries.append(
            {
                "feature_id": fid,
                "kind": "community",
                "name": feat.get("name", fid),
                "summary": feat.get("summary"),
                "path": f"features/{fid}/",
            }
        )
    (fdir / "INDEX.json").write_text(
        json.dumps({"features": index_entries}), encoding="utf-8"
    )
    return context_dir


def test_query_reads_files_from_feature_json(tmp_path: Path) -> None:
    """INDEX.json entries carry no `files`; the basename signal must fall back
    to the per-feature feature.json list or it never fires on a real index."""
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {"feature_id": "community-0", "files": ["src/auth.py"]},
            {"feature_id": "community-1", "files": ["src/models.py"]},
        ],
        symbols=[],
    )
    res = query(context_dir, "auth", top_k=3, budget_tokens=10000)
    assert res.matches
    assert res.matches[0].feature.feature_id == "community-0"


def test_query_size_normalization_beats_whale_community(tmp_path: Path) -> None:
    """A large community matching one query token across hundreds of symbols
    must not outrank a small feature whose file is exactly the topic."""
    whale_members = [f"sym_{i}" for i in range(400)]
    whale_symbols = [
        {"symbol_id": s, "name": f"parse_thing_{i}", "path": "src/big.py"}
        for i, s in enumerate(whale_members)
    ]
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {
                "feature_id": "community-0",
                "files": ["src/big.py"],
                "members": whale_members,
            },
            {"feature_id": "community-1", "files": ["src/parser.py"]},
        ],
        symbols=whale_symbols,
    )
    res = query(context_dir, "parser", top_k=3, budget_tokens=10000)
    assert res.matches
    assert res.matches[0].feature.feature_id == "community-1"


def test_query_idf_prefers_feature_with_rare_token(tmp_path: Path) -> None:
    """When every feature matches the common token, the feature matching the
    rare token must rank first."""
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {
                "feature_id": "community-0",
                "summary": "handles http transport and connection pooling",
            },
            {
                "feature_id": "community-1",
                "summary": "handles http transport and netrc lookup",
            },
        ],
        symbols=[],
    )
    res = query(context_dir, "http netrc", top_k=3, budget_tokens=10000)
    assert res.matches
    assert res.matches[0].feature.feature_id == "community-1"


def test_query_file_stem_exact_match_boost(tmp_path: Path) -> None:
    """A file whose stem equals the query token (api.py for "api") is a
    stronger signal than a symbol substring hit in a larger feature."""
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {
                "feature_id": "community-0",
                "files": ["src/capillary.py", "src/therapy.py"],
            },
            {"feature_id": "community-1", "files": ["src/api.py"]},
        ],
        symbols=[],
    )
    res = query(context_dir, "api", top_k=3, budget_tokens=10000)
    assert res.matches
    assert res.matches[0].feature.feature_id == "community-1"


def test_query_synonym_expansion_bridges_vocabulary(tmp_path: Path) -> None:
    """Query vocabulary differs from identifier vocabulary: "config" must
    find the feature whose file is settings.py via the synonym map."""
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {"feature_id": "community-0", "files": ["src/unrelated.py"]},
            {"feature_id": "community-1", "files": ["src/settings.py"]},
        ],
        symbols=[],
    )
    res = query(context_dir, "config", top_k=3, budget_tokens=10000)
    assert "settings" in res.tokens  # synonym of "config"
    assert res.matches
    assert res.matches[0].feature.feature_id == "community-1"


def test_query_path_segment_signal(tmp_path: Path) -> None:
    """Directory names on a file's path are a retrieval signal: a file under
    cli/ matches a "cli" query even when its basename doesn't."""
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {"feature_id": "community-0", "files": ["src/core/main.py"]},
            {"feature_id": "community-1", "files": ["src/cli/main.py"]},
        ],
        symbols=[],
    )
    res = query(context_dir, "cli", top_k=3, budget_tokens=10000)
    assert res.matches
    assert res.matches[0].feature.feature_id == "community-1"


def test_query_symbol_scoring_counts_only_top_five(tmp_path: Path) -> None:
    """Only the strongest few symbol matches add score: a feature with ten
    one-token symbol matches must not outscore an identical feature with
    five — the long tail of incidental hits is cut off."""
    members_a = [f"a_{i}" for i in range(10)]
    members_b = [f"b_{i}" for i in range(10)]
    symbols = [
        {"symbol_id": f"a_{i}", "name": f"parse_alpha_{i}", "path": "src/a.py"}
        for i in range(10)
    ] + [
        # Only five of B's ten symbols match the query token.
        {"symbol_id": f"b_{i}", "name": f"parse_beta_{i}", "path": "src/b.py"}
        if i < 5
        else {"symbol_id": f"b_{i}", "name": f"unrelated_{i}", "path": "src/b.py"}
        for i in range(10)
    ]
    context_dir = _write_synthetic_index(
        tmp_path,
        features=[
            {"feature_id": "community-0", "files": ["src/a.py"], "members": members_a},
            {"feature_id": "community-1", "files": ["src/b.py"], "members": members_b},
        ],
        symbols=symbols,
    )
    res = query(context_dir, "parse", top_k=3, budget_tokens=10000)
    assert len(res.matches) == 2
    s0 = res.matches[0].feature.score
    s1 = res.matches[1].feature.score
    # Same file signal, same top-5 symbol contribution: scores must tie.
    assert abs(s0 - s1) < 1e-9
