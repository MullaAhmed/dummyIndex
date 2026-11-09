"""`dummyindex context check --refs` lists durable docs citing disposable docs."""

from __future__ import annotations

from pathlib import Path

from dummyindex.cli import check


def _doc(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_refs_lists_citing_docs_rc1(tmp_path, capsys):
    _doc(tmp_path, ".context/PROJECT.md", "See .context/proposals/foo/spec.md\n")
    _doc(tmp_path, ".context/conventions/ok.md", "no citation\n")
    assert check.run(["--refs", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert ".context/PROJECT.md" in out
    assert "proposals/foo/" in out
    assert "ok.md" not in out


def test_budget_and_refs_both_run(tmp_path, capsys):
    _doc(tmp_path, ".context/PROJECT.md", "See .context/proposals/foo/spec.md\n")
    rc = check.run(["--budget", "--refs", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "context check --budget: ok" in out
    assert "proposals/foo/" in out


def test_refs_clean_rc0(tmp_path):
    _doc(tmp_path, ".context/PROJECT.md", "clean\n")
    assert check.run(["--refs", "--root", str(tmp_path)]) == 0
