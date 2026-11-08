from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.docbudget import (
    BudgetGroup,
    check,
    count_violations,
    lint_text,
    scan,
)
from dummyindex.context.domains.docbudget.constants import STYLE_CEILING

LONG_20 = " ".join(["word"] * 20) + "."
LONG_21 = " ".join(["word"] * 21) + "."


def _rules(text: str) -> list[str]:
    return [v.rule for v in lint_text(text)]


@pytest.mark.unit
def test_twenty_words_pass() -> None:
    assert lint_text(LONG_20) == ()


@pytest.mark.unit
def test_twenty_one_words_fail() -> None:
    (v,) = lint_text(LONG_21)
    assert v.rule == "long-sentence"
    assert v.line == 1


@pytest.mark.unit
def test_fenced_code_skipped() -> None:
    assert lint_text(f"```\n{LONG_21}\n```\n") == ()
    assert lint_text(f"~~~\n{LONG_21}\n~~~\n") == ()


@pytest.mark.unit
def test_html_comment_skipped() -> None:
    assert lint_text(f"<!-- {LONG_21} -->\n") == ()
    assert lint_text(f"<!--\n{LONG_21}\n-->\n") == ()


@pytest.mark.unit
def test_table_row_skipped() -> None:
    assert lint_text(f"| {LONG_21} |\n") == ()


@pytest.mark.unit
def test_heading_skipped() -> None:
    assert lint_text(f"# {LONG_21}\n") == ()


@pytest.mark.unit
def test_inline_code_counts_as_one_word() -> None:
    sentence = "Run " + "`" + " ".join(["x"] * 25) + "`" + " now."
    assert lint_text(sentence) == ()


@pytest.mark.unit
def test_just_inside_inline_code_not_flagged() -> None:
    assert lint_text("Set `just` as the flag.") == ()


@pytest.mark.unit
def test_justify_not_flagged() -> None:
    assert lint_text("We justify the choice here.") == ()


@pytest.mark.unit
def test_just_flagged_as_filler() -> None:
    (v,) = lint_text("This is just a test.")
    assert v.rule == "filler"
    assert v.excerpt == "This is just a test."


@pytest.mark.unit
def test_bold_sentence_split_after_emphasis_removed() -> None:
    # Star removal exposes "Bold. Next" so the split happens after "Bold.".
    text = "**Bold.** Next " + " ".join(["word"] * 19) + "."
    assert lint_text(text) == ()
    long_text = "**Bold.** Next " + " ".join(["word"] * 20) + "."
    (v,) = lint_text(long_text)
    assert v.rule == "long-sentence"


@pytest.mark.unit
def test_crlf_bom_matches_lf() -> None:
    body = f"# Title\n\n{LONG_21}\n\n- just item\n"
    lf = lint_text(body)
    crlf = lint_text("﻿" + body.replace("\n", "\r\n"))
    assert lf == crlf
    assert len(lf) == 2


@pytest.mark.unit
def test_list_items_are_separate_units() -> None:
    text = f"- {LONG_20}\n- {LONG_20}\n"
    assert lint_text(text) == ()
    text = f"- {LONG_21}\n- short one.\n"
    (v,) = lint_text(text)
    assert v.line == 1


@pytest.mark.unit
def test_count_violations_missing_file_is_zero(tmp_path: Path) -> None:
    assert count_violations(tmp_path / "missing.md") == 0


@pytest.mark.unit
def test_scan_style_excludes_naming_and_counts(tmp_path: Path) -> None:
    conv = tmp_path / ".context" / "conventions"
    conv.mkdir(parents=True)
    (conv / "a.md").write_text(f"{LONG_21}\n\njust once.\n", encoding="utf-8")
    (conv / "naming.md").write_text(f"{LONG_21}\n", encoding="utf-8")
    assert scan(tmp_path, BudgetGroup.STYLE) == {".context/conventions/a.md": 2}


@pytest.mark.unit
def test_check_style_unrecorded_violation_flagged(tmp_path: Path) -> None:
    conv = tmp_path / ".context" / "conventions"
    conv.mkdir(parents=True)
    (conv / "a.md").write_text(f"{LONG_21}\n", encoding="utf-8")
    (v,) = check(tmp_path, {}, BudgetGroup.STYLE)
    assert (v.path, v.words, v.limit, v.recorded) == (
        ".context/conventions/a.md",
        1,
        STYLE_CEILING,
        None,
    )
