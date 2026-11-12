"""Tests for ``domains/restyle/run.py`` — the restyle run loop over hand-built ``.context/`` shapes."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from dummyindex.context.build.meta import new_meta, read_meta, write_meta
from dummyindex.context.domains.docbudget.constants import STE_RULESET_VERSION
from dummyindex.context.domains.docbudget.ratchet import (
    measure,
    read_ratchet,
    write_ratchet,
)
from dummyindex.context.domains.fleet import create_run
from dummyindex.context.domains.restyle.errors import DocTokenLossError, RestyleRunError
from dummyindex.context.domains.restyle.run import (
    begin,
    done,
    plan,
    stamp,
    status,
)
from dummyindex.context.domains.restyle.run import (
    next_unit as restyle_next_unit,
)

BASE_TESTING = (
    "# Testing\n\n"
    "See `dummyindex/x.py:12` for the rule. It lists 3 steps. Do not skip it.\n\n"
    "The tool doesn't run. Testing is fast.\n"
)
TESTING = "conventions/testing.md"
OLD_MTIME_NS = 1_600_000_000_000_000_000


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _tree(context: Path) -> dict[str, bytes]:
    return {
        p.relative_to(context).as_posix(): p.read_bytes()
        for p in context.rglob("*")
        if p.is_file()
    }


def _meta(root: Path, **changes: object) -> None:
    base = dataclasses.replace(new_meta(root, "0.0.0"), indexed_commit="a" * 40)
    write_meta(root / ".context" / "meta.json", dataclasses.replace(base, **changes))


@pytest.fixture
def ctx(tmp_path: Path) -> Path:
    """A curated index: feature ``auth`` (spec + flow), one convention, plus exempt and workspace docs."""
    context = tmp_path / ".context"
    _write(context / "features" / "INDEX.json", '{"features": []}\n')
    _write(
        context / "features" / "auth" / "spec.md",
        "# Auth\n\nThe login flow checks the session.\n",
    )
    _write(
        context / "features" / "auth" / "flows" / "login.md",
        "# Login\n\nThe user sends a form.\n",
    )
    _write(context / "features" / "auth" / "feature.json", '{"files": []}\n')
    _write(context / "conventions" / "testing.md", BASE_TESTING)
    _write(
        context / "conventions" / "naming.md", "# Naming\n\nThe names doesn't matter.\n"
    )
    _write(
        context / "proposals" / "p1" / "spec.md", "# Draft\n\nThe draft doesn't run.\n"
    )
    _write(context / "cache" / "doc-basis.json", '{"basis": 1}\n')
    _write(context / "map" / "symbols.json", "{}\n")
    _write(context / "tree.json", "{}\n")
    _meta(tmp_path)
    write_ratchet(context / "doc-budget.txt", {".context/" + TESTING: 5})
    write_ratchet(context / "style-budget.txt", {".context/" + TESTING: 0})
    os.utime(context / "conventions" / "testing.md", ns=(OLD_MTIME_NS, OLD_MTIME_NS))
    return context


def _finish_all(context: Path) -> None:
    done(context, "auth")
    done(context, TESTING)


@pytest.mark.unit
def test_plan_lists_units_counts_and_writes_nothing(ctx: Path) -> None:
    before = _tree(ctx)
    result = plan(ctx)
    assert _tree(ctx) == before
    assert [u.unit_id for u in result.units] == ["auth", TESTING]
    assert result.doc_count == 3
    assert result.strict == 1  # "doesn't"
    assert result.advice == 1  # "Testing"
    assert result.status == "ready"


@pytest.mark.unit
def test_plan_nothing_to_restyle_without_curated_docs(tmp_path: Path) -> None:
    context = tmp_path / ".context"
    _write(context / "features" / "INDEX.json", '{"features": []}\n')
    _meta(tmp_path)
    result = plan(context)
    assert result.status == "nothing_to_restyle"
    assert result.units == ()
    with pytest.raises(RestyleRunError, match="nothing to restyle"):
        begin(context, all_units=True, max_units=None, force=False)


@pytest.mark.unit
def test_plan_reports_already_restyled_at_current_ruleset(ctx: Path) -> None:
    _meta(ctx.parent, restyled_ruleset=STE_RULESET_VERSION)
    assert plan(ctx).status == "already_restyled"


@pytest.mark.unit
def test_begin_requires_all_or_max_units(ctx: Path) -> None:
    with pytest.raises(RestyleRunError, match="--all"):
        begin(ctx, all_units=False, max_units=None, force=False)


@pytest.mark.unit
def test_begin_max_units_takes_first_units(ctx: Path) -> None:
    result = begin(ctx, all_units=False, max_units=1, force=False)
    assert result.units == ("auth",)
    assert result.doc_count == 2


@pytest.mark.unit
def test_begin_refuses_unfinished_run_and_names_resume_command(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    with pytest.raises(RestyleRunError) as err:
        begin(ctx, all_units=True, max_units=None, force=False)
    assert "dummyindex context restyle next" in str(err.value)
    assert "dummyindex context restyle status" in str(err.value)


@pytest.mark.unit
def test_begin_refuses_restyled_index_until_force(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    _finish_all(ctx)
    stamp(ctx)
    with pytest.raises(RestyleRunError, match="already restyled"):
        begin(ctx, all_units=True, max_units=None, force=False)
    # Same-second run names would collide; age the finished run so the new one is newest.
    first = next((ctx / "fleet").glob("restyle-*"))
    first.rename(first.parent / "restyle-20000101-000000")
    result = begin(ctx, all_units=True, max_units=None, force=True)
    assert result.run_dir.name.startswith("restyle-")
    assert result.run_dir.name != "restyle-20000101-000000"


@pytest.mark.unit
def test_next_unit_gives_docs_and_brief_then_none(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    nxt = restyle_next_unit(ctx)
    assert nxt is not None and nxt.unit_id == "auth"
    assert {p.name for p in nxt.docs} == {"spec.md", "login.md"}
    assert "Repo docs follow ASD-STE100" in nxt.brief
    assert "Change the words, not the facts." in nxt.brief
    assert "Protected" in nxt.brief
    done(ctx, "auth")
    assert restyle_next_unit(ctx).unit_id == TESTING
    done(ctx, TESTING)
    assert restyle_next_unit(ctx) is None


@pytest.mark.unit
def test_done_passes_when_contraction_expands(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    path = ctx / "conventions" / "testing.md"
    path.write_text(BASE_TESTING.replace("doesn't", "does not"), encoding="utf-8")
    result = done(ctx, TESTING)
    assert result.unit_id == TESTING
    assert result.strict == ()
    assert [v.rule for _, v in result.advice] == ["ing-form"]
    assert status(ctx)["done"] == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("old", "new", "token"),
    [
        ("`dummyindex/x.py:12`", "`dummyindex/x.py`", "dummyindex/x.py:12"),
        ("3 steps", "several steps", "3"),
        ("Do not skip it.", "Check it.", "not"),
    ],
)
def test_done_refuses_lost_token_and_names_it(
    ctx: Path, old: str, new: str, token: str
) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    path = ctx / "conventions" / "testing.md"
    path.write_text(BASE_TESTING.replace(old, new), encoding="utf-8")
    with pytest.raises(DocTokenLossError) as err:
        done(ctx, TESTING)
    message = str(err.value)
    assert TESTING in message
    assert token in message
    assert status(ctx)["done"] == 0


@pytest.mark.unit
def test_done_restores_snapshot_mtime(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    path = ctx / "conventions" / "testing.md"
    path.write_text(BASE_TESTING.replace("doesn't", "does not"), encoding="utf-8")
    assert path.stat().st_mtime_ns != OLD_MTIME_NS
    done(ctx, TESTING)
    assert path.stat().st_mtime_ns == OLD_MTIME_NS


@pytest.mark.unit
def test_stamp_refuses_pending_units(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    with pytest.raises(RestyleRunError, match="pending"):
        stamp(ctx)


@pytest.mark.unit
def test_stamp_records_ruleset_and_reseeds_grown_doc(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    path = ctx / "conventions" / "testing.md"
    grown = (
        BASE_TESTING.replace("doesn't", "does not")
        + "The tool also writes a log file in the cache folder.\n"
    )
    path.write_text(grown, encoding="utf-8")
    protected = ("features/INDEX.json", "cache/doc-basis.json")
    before = {rel: (ctx / rel).read_bytes() for rel in protected}
    anchor = read_meta(ctx / "meta.json").indexed_commit
    _finish_all(ctx)

    stamp(ctx)

    assert read_meta(ctx / "meta.json").restyled_ruleset == STE_RULESET_VERSION
    assert read_meta(ctx / "meta.json").indexed_commit == anchor
    assert {rel: (ctx / rel).read_bytes() for rel in protected} == before
    words = measure(path)
    assert words > 5
    assert read_ratchet(ctx / "doc-budget.txt")[".context/" + TESTING] == words
    assert plan(ctx).status == "already_restyled"


@pytest.mark.unit
def test_maintain_run_rejected_by_name(ctx: Path) -> None:
    maintain = create_run(
        ctx,
        ("auth",),
        stages_for_feature={"auth": ((1, "specify"),)},
    )
    with pytest.raises(RestyleRunError, match="maintain"):
        status(ctx, run=maintain.run_dir.name)
    with pytest.raises(RestyleRunError, match="maintain"):
        restyle_next_unit(ctx, run=str(maintain.run_dir))


@pytest.mark.unit
def test_status_wraps_run_status(ctx: Path) -> None:
    begin(ctx, all_units=True, max_units=None, force=False)
    report = status(ctx)
    assert report["total"] == 2
    assert report["pending"] == 2
    assert report["complete"] is False
