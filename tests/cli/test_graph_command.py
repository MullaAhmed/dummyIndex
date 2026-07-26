"""Tests for `dummyindex context graph` dispatch (wire-only CLI contract).

Unit tests run against the synthetic node-link fixture from
``tests/context/domains/test_graph_query.py``; the integration smoke runs
the verbs read-only against this repo's real
``.context/features/symbol-graph.json`` when it is present, asserting only
stable signals (exit codes, citation-path shapes) — never live community
ids or member lists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import _HANDLERS, dispatch, graph
from dummyindex.context.enums import ContextSubcommand
from tests.context.domains.test_graph_query import write_graph
from tests.paths import REPO_ROOT

_REAL_GRAPH = REPO_ROOT / ".context" / "features" / "symbol-graph.json"


@pytest.mark.unit
def test_graph_handler_is_registered() -> None:
    assert _HANDLERS[ContextSubcommand.GRAPH] is graph.run


@pytest.mark.unit
def test_graph_help_lists_every_verb(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert dispatch(["graph", "--help"]) == 0
    out = capsys.readouterr().out
    for verb in (
        "callers-of",
        "callees-of",
        "impact",
        "path",
        "neighbors",
        "dead-code",
        "community",
    ):
        assert verb in out, f"`graph --help` does not document {verb!r}"


@pytest.mark.unit
def test_graph_without_verb_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = dispatch(["graph"])
    assert rc == 2
    assert "usage" in capsys.readouterr().err


@pytest.mark.unit
def test_graph_unknown_verb_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = dispatch(["graph", "explode"])
    assert rc == 2
    assert "unknown graph verb" in capsys.readouterr().err


@pytest.mark.unit
def test_graph_wrong_arity_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = dispatch(["graph", "path", "only_one"])
    assert rc == 2
    assert "takes 2 positional argument(s)" in capsys.readouterr().err


@pytest.mark.unit
def test_graph_scoped_flags_are_rejected_on_other_verbs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch(["graph", "callers-of", "x", "--depth", "3"]) == 2
    assert "--depth only applies" in capsys.readouterr().err
    assert dispatch(["graph", "impact", "x", "--hops", "3"]) == 2
    assert "--hops only applies" in capsys.readouterr().err


@pytest.mark.unit
def test_graph_bad_limit_is_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dispatch(["graph", "dead-code", "--limit", "zero"]) == 2
    assert "must be an integer" in capsys.readouterr().err
    assert dispatch(["graph", "dead-code", "--limit", "0"]) == 2
    assert "must be >= 1" in capsys.readouterr().err


@pytest.mark.unit
def test_graph_missing_artifact_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(["graph", "dead-code", "--root", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "symbol graph not found" in err
    assert "symbol-graph.json" in err


@pytest.mark.unit
def test_graph_callers_of_prints_cited_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_graph(tmp_path)
    rc = dispatch(["graph", "callers-of", "lib.py:util", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# graph callers-of lib_util" in out
    assert "src/app.py:L10" in out  # caller definition
    assert "at src/app.py:L14" in out  # call site
    assert "Entry point of the app." in out  # docstring attached


@pytest.mark.unit
def test_graph_json_output_is_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_graph(tmp_path)
    rc = dispatch(["graph", "callees-of", "main", "--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verb"] == "callees-of"
    assert payload["subject"]["node_id"] == "app_main"
    assert [r["node_id"] for r in payload["rows"]] == ["app_helper", "lib_util"]


@pytest.mark.unit
def test_graph_unknown_symbol_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_graph(tmp_path)
    rc = dispatch(["graph", "callers-of", "no_such_thing", "--root", str(tmp_path)])
    assert rc == 1
    assert "unknown symbol" in capsys.readouterr().err


@pytest.mark.unit
def test_graph_ambiguous_symbol_exits_1_and_lists_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_graph(tmp_path)
    rc = dispatch(["graph", "callers-of", "util", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ambiguous symbol" in err
    assert "lib_util" in err
    assert "other_util" in err


@pytest.mark.unit
def test_graph_no_path_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_graph(tmp_path)
    rc = dispatch(["graph", "path", "island", "main", "--root", str(tmp_path)])
    assert rc == 1
    assert "no path" in capsys.readouterr().out


@pytest.mark.unit
def test_graph_dead_code_is_bounded_and_cited(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_graph(tmp_path)
    rc = dispatch(["graph", "dead-code", "--root", str(tmp_path), "--limit", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 of 7 row(s) (truncated by --limit)" in out
    assert "src/app.py:L1" in out


# ----- read-only smoke against this repo's real artifact --------------------


@pytest.mark.integration
@pytest.mark.skipif(not _REAL_GRAPH.is_file(), reason="no real symbol graph")
def test_graph_smoke_on_real_artifact(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every verb answers on the real graph; assert only stable shapes."""
    root = str(REPO_ROOT)
    rc = dispatch(["graph", "dead-code", "--root", root, "--limit", "3"])
    out = capsys.readouterr().out
    assert rc == 0
    assert ".py:L" in out  # rows carry file:line citations

    rc = dispatch(
        ["graph", "callers-of", "resolve_context_root", "--root", root, "--limit", "5"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "resolve_context_root" in out
    assert ".py:L" in out

    rc = dispatch(
        ["graph", "neighbors", "resolve_context_root", "--root", root, "--limit", "5"]
    )
    assert rc == 0
    assert ".py:L" in capsys.readouterr().out
