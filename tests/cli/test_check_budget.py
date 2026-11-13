"""`dummyindex context check --budget|--style [--update-ratchet]` wiring tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.cli import check

DOC = ".context/PROJECT.md"
SKILL = "dummyindex/skills/x/SKILL.md"
LONG = " ".join(["w"] * 21) + "."


def _write(root: Path, rel: str, words: int) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(" ".join(["w"] * words), encoding="utf-8")


def _ratchet(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _run(root: Path, *flags: str) -> int:
    return check.run(["--budget", *flags, "--root", str(root)])


def _style(root: Path, *flags: str) -> int:
    return check.run(["--style", *flags, "--root", str(root)])


def _doc(root: Path, text: str) -> None:
    p = root / DOC
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_grown_doc_fails_with_path(tmp_path, capsys):
    _write(tmp_path, DOC, 20)
    _ratchet(tmp_path, ".context/doc-budget.txt", f"{DOC}\t10\n")
    assert _run(tmp_path) == 1
    assert DOC in capsys.readouterr().out


def test_unchanged_and_shrunk_pass(tmp_path):
    _write(tmp_path, DOC, 10)
    _write(tmp_path, SKILL, 5)
    _ratchet(tmp_path, ".context/doc-budget.txt", f"{DOC}\t10\n")
    _ratchet(tmp_path, "tests/data/skill-budget.txt", f"{SKILL}\t9\n")
    assert _run(tmp_path) == 0


def test_skills_group_grown_fails(tmp_path, capsys):
    _write(tmp_path, SKILL, 9)
    _ratchet(tmp_path, "tests/data/skill-budget.txt", f"{SKILL}\t5\n")
    assert _run(tmp_path) == 1
    assert SKILL in capsys.readouterr().out


def test_update_lowers_but_refuses_raise(tmp_path, capsys):
    _write(tmp_path, DOC, 20)
    _write(tmp_path, ".context/conventions/a.md", 3)
    _ratchet(
        tmp_path,
        ".context/doc-budget.txt",
        f"{DOC}\t10\n.context/conventions/a.md\t8\n",
    )
    assert _run(tmp_path, "--update-ratchet") == 1
    out = capsys.readouterr().out
    assert DOC in out
    text = (tmp_path / ".context/doc-budget.txt").read_text(encoding="utf-8")
    assert f"{DOC}\t10" in text
    assert ".context/conventions/a.md\t3" in text


def test_update_clean_seeds_rc0(tmp_path):
    _write(tmp_path, DOC, 4)
    assert _run(tmp_path, "--update-ratchet") == 0
    assert f"{DOC}\t4" in (tmp_path / ".context/doc-budget.txt").read_text(
        encoding="utf-8"
    )


@pytest.mark.unit
def test_update_ratchet_requires_budget_or_style(tmp_path, capsys):
    assert check.run(["--update-ratchet", "--root", str(tmp_path)]) == 2
    assert "requires --budget or --style" in capsys.readouterr().err


@pytest.mark.unit
def test_budget_update_leaves_style_ratchet_untouched(tmp_path):
    _write(tmp_path, DOC, 4)
    _ratchet(tmp_path, ".context/doc-budget.txt", f"{DOC}\t10\n")
    _ratchet(tmp_path, ".context/style-budget.txt", f"{DOC}\t7\n")
    before = (tmp_path / ".context/style-budget.txt").read_bytes()
    assert _run(tmp_path, "--update-ratchet") == 0
    assert (tmp_path / ".context/style-budget.txt").read_bytes() == before


@pytest.mark.unit
def test_style_update_leaves_doc_budget_untouched(tmp_path):
    _write(tmp_path, DOC, 4)
    _ratchet(tmp_path, ".context/doc-budget.txt", f"{DOC}\t99\n")
    before = (tmp_path / ".context/doc-budget.txt").read_bytes()
    assert _style(tmp_path, "--update-ratchet") == 0
    assert (tmp_path / ".context/doc-budget.txt").read_bytes() == before


@pytest.mark.unit
def test_style_without_ratchet_prints_details_and_hint(tmp_path, capsys):
    _doc(tmp_path, LONG + "\n")
    assert _style(tmp_path) == 0
    out = capsys.readouterr().out
    assert f"{DOC}:1: long-sentence:" in out
    assert (
        "no style ratchet; seed it with: dummyindex context check --style --update-ratchet"
        in out
    )


@pytest.mark.unit
def test_style_recorded_zero_then_long_sentence_fails(tmp_path, capsys):
    _ratchet(tmp_path, ".context/style-budget.txt", f"# ruleset 1\n{DOC}\t0\n")
    _doc(tmp_path, LONG + "\n")
    assert _style(tmp_path) == 1
    assert DOC in capsys.readouterr().out


@pytest.mark.unit
def test_style_clean_and_recorded_passes(tmp_path, capsys):
    _doc(tmp_path, "Short clean sentence here.\n")
    _ratchet(tmp_path, ".context/style-budget.txt", f"# ruleset 1\n{DOC}\t0\n")
    assert _style(tmp_path) == 0
    assert "context check --style: ok" in capsys.readouterr().out


@pytest.mark.unit
def test_style_update_seeds_ratchet(tmp_path):
    _doc(tmp_path, "Short clean sentence here.\n")
    assert _style(tmp_path, "--update-ratchet") == 0
    text = (tmp_path / ".context/style-budget.txt").read_text(encoding="utf-8")
    assert f"{DOC}\t0" in text


@pytest.mark.unit
def test_advice_printed_and_exit_zero(tmp_path, capsys):
    _doc(tmp_path, "We are using the tool. The file is written by the tool.\n")
    _ratchet(tmp_path, ".context/style-budget.txt", f"# ruleset 1\n{DOC}\t0\n")
    assert _style(tmp_path) == 0
    out = capsys.readouterr().out
    assert f"advice: {DOC}:1: ing-form:" in out
    assert f"advice: {DOC}:1: passive:" in out


@pytest.mark.unit
def test_stale_ruleset_prints_hint_exit_zero(tmp_path, capsys):
    _doc(tmp_path, LONG + "\n")
    _ratchet(tmp_path, ".context/style-budget.txt", f"# ruleset 0\n{DOC}\t0\n")
    assert _style(tmp_path) == 0
    assert "re-seed" in capsys.readouterr().out


@pytest.mark.unit
def test_stale_ruleset_update_rewrites_header(tmp_path):
    _doc(tmp_path, LONG + "\n")
    ratchet = tmp_path / ".context/style-budget.txt"
    _ratchet(tmp_path, ".context/style-budget.txt", f"# ruleset 0\n{DOC}\t0\n")
    assert _style(tmp_path, "--update-ratchet") == 0
    text = ratchet.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "# ruleset 1"
    assert f"{DOC}\t1" in text
