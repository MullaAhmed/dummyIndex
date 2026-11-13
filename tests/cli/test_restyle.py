"""`dummyindex context restyle` CLI: exit codes and output over the real dispatcher."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.build.meta import new_meta, write_meta

TESTING = "conventions/testing.md"
BASE_TESTING = (
    "# Testing\n\n"
    "See `dummyindex/x.py:12` for the rule. It lists 3 steps. Do not skip it.\n\n"
    "The tool doesn't run. Testing is fast.\n"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(root: Path, *args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = dispatch(["restyle", *args, "--root", str(root)])
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture()
def curated(tmp_path: Path) -> Path:
    """A curated index: feature ``auth`` (spec) and the ``testing`` convention."""
    context = tmp_path / ".context"
    _write(
        context / "features" / "auth" / "spec.md",
        "# Auth\n\nThe login flow checks the session.\n",
    )
    _write(context / TESTING, BASE_TESTING)
    meta = dataclasses.replace(new_meta(tmp_path, "0.0.0"), indexed_commit="a" * 40)
    write_meta(context / "meta.json", meta)
    return tmp_path


def _rewrite_testing(root: Path, text: str) -> None:
    (root / ".context" / TESTING).write_text(text, encoding="utf-8")


def _finish_all(root: Path) -> None:
    """Run ``next``/``done`` until every unit is done, leaving the docs as they are."""
    while True:
        rc, out, _ = _run(root, "next", "--json")
        assert rc == 0
        unit = json.loads(out)["unit"]
        if unit is None:
            return
        rc, _, err = _run(root, "done", unit["unit_id"])
        assert rc == 0, err


@pytest.mark.unit
def test_plan_lists_units_with_counts(curated: Path) -> None:
    rc, out, _ = _run(curated, "plan")
    assert rc == 0
    assert "auth" in out
    assert TESTING in out
    assert "strict" in out and "advice" in out


@pytest.mark.unit
def test_plan_json_parses(curated: Path) -> None:
    rc, out, _ = _run(curated, "plan", "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["status"] == "ready"
    assert {unit["unit_id"] for unit in payload["units"]} == {"auth", TESTING}


@pytest.mark.unit
def test_plan_on_empty_index_says_nothing_to_restyle(tmp_path: Path) -> None:
    write_meta(
        tmp_path / ".context" / "meta.json",
        dataclasses.replace(new_meta(tmp_path, "0.0.0"), indexed_commit="a" * 40),
    )
    rc, out, _ = _run(tmp_path, "plan")
    assert rc == 0
    assert "nothing to restyle" in out


@pytest.mark.unit
def test_begin_without_scope_flag_is_refused(curated: Path) -> None:
    rc, _, err = _run(curated, "begin")
    assert rc != 0
    assert "--all" in err or "--max-units" in err


@pytest.mark.unit
def test_begin_refused_while_a_run_is_unfinished(curated: Path) -> None:
    assert _run(curated, "begin", "--all")[0] == 0
    rc, _, err = _run(curated, "begin", "--all")
    assert rc != 0
    assert "unfinished" in err


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rewritten", "lost"),
    [
        (
            BASE_TESTING.replace("`dummyindex/x.py:12`", "the file"),
            "dummyindex/x.py:12",
        ),
        (BASE_TESTING.replace("3 steps", "some steps"), "3"),
        (BASE_TESTING.replace("Do not skip", "Skip"), "not"),
    ],
    ids=["path-line", "numeral", "negation"],
)
def test_done_refuses_lost_token(curated: Path, rewritten: str, lost: str) -> None:
    assert _run(curated, "begin", "--all")[0] == 0
    _rewrite_testing(curated, rewritten)
    rc, _, err = _run(curated, "done", TESTING)
    assert rc == 1
    assert TESTING in err
    assert f"lost {lost}" in err


@pytest.mark.unit
def test_done_accepts_dont_to_do_not(curated: Path) -> None:
    assert _run(curated, "begin", "--all")[0] == 0
    _rewrite_testing(curated, BASE_TESTING.replace("doesn't run", "does not run"))
    rc, _, err = _run(curated, "done", TESTING)
    assert rc == 0, err


@pytest.mark.unit
def test_stamp_then_plan_reports_already_restyled(curated: Path) -> None:
    assert _run(curated, "begin", "--all")[0] == 0
    _finish_all(curated)
    rc, _, err = _run(curated, "stamp")
    assert rc == 0, err
    rc, out, _ = _run(curated, "plan")
    assert rc == 0
    assert "already restyled" in out


@pytest.mark.unit
def test_status_json_parses(curated: Path) -> None:
    assert _run(curated, "begin", "--all")[0] == 0
    rc, out, _ = _run(curated, "status", "--json")
    assert rc == 0
    assert json.loads(out)["total"] == 2


@pytest.mark.unit
def test_partial_stamp_reports_coverage_and_plan_stays_ready(curated: Path) -> None:
    rc, out, err = _run(curated, "begin", "--max-units", "1")
    assert rc == 0, err
    rc, _, err = _run(curated, "done", "auth")
    assert rc == 0, err
    rc, out, err = _run(curated, "stamp")
    assert rc == 0, err
    assert "not stamped" in out
    assert "1/2" in out
    rc, out, _ = _run(curated, "plan", "--json")
    assert rc == 0
    assert json.loads(out)["status"] == "ready"


@pytest.mark.unit
def test_partial_stamp_json_reports_null_ruleset(curated: Path) -> None:
    assert _run(curated, "begin", "--max-units", "1")[0] == 0
    assert _run(curated, "done", "auth")[0] == 0
    rc, out, err = _run(curated, "stamp", "--json")
    assert rc == 0, err
    payload = json.loads(out)
    assert payload["ruleset"] is None
    assert payload["covered"] == 1
    assert payload["total"] == 2


@pytest.mark.unit
def test_plan_after_partial_stamp_is_not_already_restyled(curated: Path) -> None:
    assert _run(curated, "begin", "--max-units", "1")[0] == 0
    assert _run(curated, "done", "auth")[0] == 0
    assert _run(curated, "stamp")[0] == 0
    rc, out, _ = _run(curated, "plan")
    assert rc == 0
    assert "already restyled" not in out
