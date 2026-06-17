"""Unit tests for the ``context.debt`` harvester.

Covers the Python-only enumeration, the true-comment matching rule, the raw
structured ``# DEBT: <ceiling>; upgrade: <trigger>`` parse, the ``no_trigger``
tagging rule, repo-relative POSIX paths (no absolute leak), unreadable-file
skips, and deterministic (path, line) ordering.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.debt import (
    DebtLedger,
    DebtRow,
    harvest_debt,
)


# ----- model shape ----------------------------------------------------------


@pytest.mark.unit
def test_debt_row_is_frozen() -> None:
    row = DebtRow(
        rel_path="a.py",
        line=1,
        marker="TODO",
        ceiling="refactor",
        trigger=None,
        no_trigger=True,
    )
    with pytest.raises((AttributeError, TypeError)):
        row.line = 2  # type: ignore[misc]


@pytest.mark.unit
def test_debt_row_to_dict_round_trip() -> None:
    row = DebtRow(
        rel_path="pkg/mod.py",
        line=7,
        marker="DEBT",
        ceiling="global lock",
        trigger="per-account if throughput matters",
        no_trigger=False,
    )
    assert row.to_dict() == {
        "rel_path": "pkg/mod.py",
        "line": 7,
        "marker": "DEBT",
        "ceiling": "global lock",
        "trigger": "per-account if throughput matters",
        "no_trigger": False,
    }


@pytest.mark.unit
def test_empty_ledger_tallies_zero() -> None:
    ledger = DebtLedger(rows=())
    assert ledger.total == 0
    assert ledger.no_trigger_count == 0
    assert ledger.to_dict() == {"total": 0, "no_trigger_count": 0, "rows": []}


# ----- harvest fixtures -----------------------------------------------------


def _write(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


@pytest.fixture
def debt_repo(tmp_path: Path) -> Path:
    """A small repo exercising every marker shape + a few false-positives."""
    # Structured DEBT: ceiling + upgrade trigger captured.
    _write(
        tmp_path,
        "src/locks.py",
        "import threading\n"
        "\n"
        "    # DEBT: global lock; upgrade: per-account if throughput matters\n"
        "lock = threading.Lock()\n",
    )
    # Plain TODO + a DEBT with a ceiling but no upgrade clause -> both no_trigger.
    _write(
        tmp_path,
        "src/handlers.py",
        "def handle():\n"
        "    # TODO: refactor\n"
        "    pass\n"
        "# DEBT: just a ceiling\n",
    )
    # A marker token inside a string-continuation line is NOT a comment.
    # A marker token inside a real (indented) comment IS counted.
    _write(
        tmp_path,
        "src/strings.py",
        'BANNER = (\n'
        '    "# TODO: this lives inside a string, not a comment"\n'
        ")\n"
        "    # FIXME: but this real comment counts\n",
    )
    # Markdown must NOT be scanned (Python-only).
    _write(
        tmp_path,
        "docs/notes.md",
        "# TODO: this markdown heading must be ignored\n"
        "Some prose.\n",
    )
    return tmp_path


@pytest.mark.unit
def test_structured_debt_captures_trigger(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    rows = {r.rel_path: r for r in ledger.rows if r.rel_path == "src/locks.py"}
    row = rows["src/locks.py"]
    assert row.marker == "DEBT"
    assert row.ceiling == "global lock"
    assert row.trigger == "per-account if throughput matters"
    assert row.no_trigger is False


@pytest.mark.unit
def test_plain_todo_is_no_trigger(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    todo = next(r for r in ledger.rows if r.marker == "TODO")
    assert todo.rel_path == "src/handlers.py"
    assert todo.ceiling == "refactor"
    assert todo.trigger is None
    assert todo.no_trigger is True


@pytest.mark.unit
def test_debt_with_only_ceiling_is_no_trigger(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    row = next(
        r
        for r in ledger.rows
        if r.rel_path == "src/handlers.py" and r.marker == "DEBT"
    )
    assert row.ceiling == "just a ceiling"
    assert row.trigger is None
    assert row.no_trigger is True


@pytest.mark.unit
def test_string_continuation_is_not_matched_but_real_comment_is(
    debt_repo: Path,
) -> None:
    ledger = harvest_debt(debt_repo)
    strings_rows = [r for r in ledger.rows if r.rel_path == "src/strings.py"]
    # The in-string "# TODO:" must NOT be counted; only the real # FIXME: comment.
    assert len(strings_rows) == 1
    assert strings_rows[0].marker == "FIXME"
    assert strings_rows[0].ceiling == "but this real comment counts"


@pytest.mark.unit
def test_markdown_is_not_scanned(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    assert all(not r.rel_path.endswith(".md") for r in ledger.rows)
    assert all("notes.md" not in r.rel_path for r in ledger.rows)


@pytest.mark.unit
def test_paths_are_repo_relative_posix(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    rendered = ledger.to_dict()
    blob = repr(rendered)
    for leak in ("/home/", "/Users/", "/mnt/", "\\"):
        assert leak not in blob, f"absolute/native path leaked: {leak!r}"
    for row in ledger.rows:
        assert not Path(row.rel_path).is_absolute()
        assert "/" in row.rel_path or row.rel_path.count("/") == 0  # POSIX form


@pytest.mark.unit
def test_rows_are_sorted_by_path_then_line(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    keys = [(r.rel_path, r.line) for r in ledger.rows]
    assert keys == sorted(keys)


@pytest.mark.unit
def test_no_trigger_count_tally(debt_repo: Path) -> None:
    ledger = harvest_debt(debt_repo)
    expected = sum(1 for r in ledger.rows if r.no_trigger)
    assert ledger.no_trigger_count == expected
    assert ledger.total == len(ledger.rows)
    # Three no-trigger markers: plain TODO, DEBT-only-ceiling, real FIXME.
    assert ledger.no_trigger_count == 3


@pytest.mark.unit
def test_deterministic_across_runs(debt_repo: Path) -> None:
    first = harvest_debt(debt_repo)
    second = harvest_debt(debt_repo)
    assert first.to_dict() == second.to_dict()


@pytest.mark.unit
def test_unreadable_binary_file_is_skipped(tmp_path: Path) -> None:
    # A valid .py marker so we know the harvester ran.
    _write(tmp_path, "ok.py", "# TODO: keep me\n")
    # A binary blob with a .py suffix that is not valid UTF-8 -> must be skipped,
    # never raise.
    bad = tmp_path / "blob.py"
    bad.write_bytes(b"\xff\xfe\x00\x01# TODO: invisible\n")
    ledger = harvest_debt(tmp_path)  # must not raise
    # The readable file's marker is harvested ...
    assert any(r.rel_path == "ok.py" for r in ledger.rows)
    # ... and the unreadable blob contributes no rows at all.
    assert all(r.rel_path != "blob.py" for r in ledger.rows)


@pytest.mark.unit
def test_malformed_empty_marker_degrades_without_raising(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "edge.py",
        "# DEBT:\n"  # empty marker
        "# TODO:   \n"  # whitespace-only ceiling
        "# DEBT: ; upgrade: trig\n",  # empty ceiling, present trigger
    )
    ledger = harvest_debt(tmp_path)  # must not raise
    by_line = {r.line: r for r in ledger.rows}
    # Empty DEBT: -> no_trigger, empty ceiling, no raise.
    assert by_line[1].no_trigger is True
    assert by_line[1].trigger is None
    # Whitespace-only TODO -> no_trigger.
    assert by_line[2].no_trigger is True
    # Empty ceiling but a real upgrade clause -> trigger captured, not no_trigger.
    assert by_line[3].trigger == "trig"
    assert by_line[3].no_trigger is False


@pytest.mark.unit
def test_clean_repo_yields_empty_ledger(tmp_path: Path) -> None:
    _write(tmp_path, "clean.py", "x = 1  # an ordinary trailing comment\n")
    ledger = harvest_debt(tmp_path)
    assert ledger.rows == ()
    assert ledger.total == 0
