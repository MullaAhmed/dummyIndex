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


SEVEN = " ".join(f"Item {i} runs fast." for i in range(7))


@pytest.mark.unit
def test_long_paragraph_flagged_once() -> None:
    (v,) = lint_text(SEVEN + "\n")
    assert v.rule == "long-paragraph"
    assert v.severity == "strict"


@pytest.mark.unit
def test_six_sentences_pass() -> None:
    assert lint_text(" ".join(f"Item {i} runs fast." for i in range(6)) + "\n") == ()


@pytest.mark.unit
def test_ordered_list_marker_is_not_a_sentence() -> None:
    six = "3. Run it. Read it. Check it. Keep it. Ship it. Tag it.\n"
    assert lint_text(six) == ()
    seven = "3. Run it. Read it. Check it. Keep it. Ship it. Tag it. Done.\n"
    (v,) = lint_text(seven)
    assert v.rule == "long-paragraph"


@pytest.mark.unit
@pytest.mark.parametrize("marker", ["1)", "-", "*", "+"])
def test_list_marker_variants_are_not_sentences(marker: str) -> None:
    six = f"{marker} Run it. Read it. Check it. Keep it. Ship it. Tag it.\n"
    assert lint_text(six) == ()


@pytest.mark.unit
def test_numbers_in_body_do_not_split() -> None:
    assert lint_text("Rule 5.1 says it. Version 3.2 is out.\n") == ()


@pytest.mark.unit
def test_long_paragraph_backticked_passes() -> None:
    text = " ".join(f"`Item {i} runs fast.`" for i in range(7)) + "\n"
    assert lint_text(text) == ()


@pytest.mark.unit
def test_contraction_flagged_once() -> None:
    (v,) = lint_text("It's ready.\n")
    assert v.rule == "contraction"
    assert v.severity == "strict"


@pytest.mark.unit
def test_contraction_backticked_passes() -> None:
    assert lint_text("Set `It's` now.\n") == ()


@pytest.mark.unit
def test_semicolon_flagged_once() -> None:
    (v,) = lint_text("Keep it short; keep it clear.\n")
    assert v.rule == "semicolon"
    assert v.severity == "strict"


@pytest.mark.unit
def test_semicolon_backticked_passes() -> None:
    assert lint_text("Set `a;b` now.\n") == ()


@pytest.mark.unit
def test_ing_form_is_advice_and_not_counted(tmp_path: Path) -> None:
    (v,) = lint_text("We are using the tool.\n")
    assert v.rule == "ing-form"
    assert v.severity == "advice"
    assert count_violations(_write_doc(tmp_path, "We are using the tool.\n")) == 0


@pytest.mark.unit
def test_ing_allowlist_passes() -> None:
    assert lint_text("The string is a thing during setup.\n") == ()


@pytest.mark.unit
def test_passive_is_advice() -> None:
    (v,) = lint_text("The file is written by the tool.\n")
    assert v.rule == "passive"
    assert v.severity == "advice"


@pytest.mark.unit
def test_frontmatter_skipped() -> None:
    long_desc = " ".join(["word"] * 40)
    text = f"---\ndescription: {long_desc}\n---\n\nShort sentence here.\n"
    assert lint_text(text) == ()


@pytest.mark.unit
def test_crlf_bom_matches_lf_for_new_rules() -> None:
    body = f"{SEVEN}\n\nIt's ready; go.\n"
    assert lint_text("﻿" + body.replace("\n", "\r\n")) == lint_text(body)


def _write_doc(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "doc.md"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.unit
def test_blockquote_two_lines_split_into_two_sentences() -> None:
    text = "> One short sentence here.\n> Another short sentence here.\n"
    assert lint_text(text) == ()
    assert _rules("> One sentence here.\n> Two sentence here.\n") == []


@pytest.mark.unit
def test_blockquote_seven_sentences_is_one_long_paragraph() -> None:
    text = "\n".join(f"> Sentence number {i} here." for i in range(7)) + "\n"
    assert _rules(text) == ["long-paragraph"]


@pytest.mark.unit
def test_blockquote_blank_quote_line_breaks_paragraph() -> None:
    sentences = [f"> Sentence number {i} here." for i in range(6)]
    text = "\n".join(sentences + [">"] + sentences) + "\n"
    assert _rules(text) == []


@pytest.mark.unit
def test_blockquote_heading_skipped() -> None:
    assert lint_text("> ## Heading, don't\n") == ()


@pytest.mark.unit
def test_nested_blockquote_split_and_counted() -> None:
    text = "> > One short sentence here.\n> > Another short sentence here.\n"
    assert lint_text(text) == ()
    text7 = "\n".join(f"> > Sentence number {i} here." for i in range(7)) + "\n"
    assert _rules(text7) == ["long-paragraph"]


@pytest.mark.unit
def test_blockquote_list_item_is_separate_unit() -> None:
    assert lint_text(f"> - {LONG_21}\n") != ()
    assert lint_text("> - Short item.\n> - Other short item.\n") == ()


@pytest.mark.unit
def test_blockquote_lines_are_separate_sentences_for_length() -> None:
    first = "Alpha " + " ".join(["word"] * 14) + "."
    second = "Beta " + " ".join(["word"] * 14) + "."
    assert _rules(f"> {first}\n> {second}\n") == []
