"""`dummyindex context check --budget [--update-ratchet]` wiring tests."""

from __future__ import annotations

from pathlib import Path

from dummyindex.cli import check

DOC = ".context/PROJECT.md"
SKILL = "dummyindex/skills/x/SKILL.md"


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


def test_update_ratchet_requires_budget(tmp_path):
    assert check.run(["--update-ratchet", "--root", str(tmp_path)]) == 2
