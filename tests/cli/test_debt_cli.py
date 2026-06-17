"""CLI body tests for ``dummyindex context debt`` (``cli/debt.py``).

These pin the *CLI boundary* contract (the harvester itself is covered in
``tests/context/domains/debt/test_harvest.py``): the default stdout ledger, the
``--write`` persistence to ``.context/debt.md``, the ``--json`` stable
structure, the clean-repo no-debt message, repo-relative rows (no absolute path
leak), and the trailing ``N markers, M with no trigger.`` tally.

The module is a *flat* ``run(argv) -> int`` mirroring ``cli/query.py`` — it is
invoked directly here (it is not registered in ``cli/__init__.py`` until Wave 4).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import debt


def _write(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


@pytest.fixture
def debt_repo(tmp_path: Path) -> Path:
    """A tiny repo with a couple of ``# DEBT:``/``# TODO:``/``# HACK:`` markers.

    Two files (``api/routes.py`` sorts before ``zzz/last.py``) so the rendered
    ledger exercises the path-sorted, grouped-by-file ordering.
    """
    _write(
        tmp_path,
        "zzz/last.py",
        "def handler():\n"
        "    # TODO: refactor this\n"
        "    pass\n",
    )
    _write(
        tmp_path,
        "api/routes.py",
        "import threading\n"
        "# DEBT: global lock; upgrade: per-account when throughput matters\n"
        "# HACK: monkeypatch the client\n",
    )
    # Markdown must be ignored (Python-only harvest); proves no .md row leaks in.
    _write(tmp_path, "docs/notes.md", "# TODO: ignore me\n")
    return tmp_path


# ----- default: print the ledger to stdout ----------------------------------


@pytest.mark.integration
def test_default_prints_path_sorted_ledger(
    debt_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = debt.run(["--root", str(debt_repo)])
    assert rc == 0
    out = capsys.readouterr().out

    # Every marker is present, repo-relative.
    assert "api/routes.py:2" in out
    assert "api/routes.py:3" in out
    assert "zzz/last.py:2" in out
    # The structured trigger is rendered.
    assert "per-account when throughput matters" in out
    # The plain markers are flagged no-trigger.
    assert "no-trigger" in out

    # Path-sorted: api/ group renders before zzz/ group.
    assert out.index("api/routes.py") < out.index("zzz/last.py")


@pytest.mark.integration
def test_default_prints_tally(
    debt_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = debt.run(["--root", str(debt_repo)])
    assert rc == 0
    out = capsys.readouterr().out
    # 3 markers total (DEBT w/ trigger, HACK, TODO); 2 have no trigger.
    assert "3 markers, 2 with no trigger." in out


@pytest.mark.integration
def test_rows_never_contain_absolute_paths(
    debt_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    debt.run(["--root", str(debt_repo)])
    out = capsys.readouterr().out
    for leak in ("/home/", "/Users/", "/mnt/"):
        assert leak not in out, f"absolute path leaked: {leak!r}"


# ----- clean repo: the no-debt message --------------------------------------


@pytest.mark.integration
def test_clean_repo_prints_no_debt_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "clean.py", "x = 1  # an ordinary trailing comment\n")
    rc = debt.run(["--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "no" in out and "debt" in out
    # The tally line must not claim markers exist.
    assert "0 markers" in out or "no debt markers" in out


# ----- --write: persist .context/debt.md ------------------------------------


@pytest.mark.integration
def test_write_persists_context_debt_md(
    debt_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = debt.run(["--root", str(debt_repo), "--write"])
    assert rc == 0

    debt_md = debt_repo / ".context" / "debt.md"
    assert debt_md.is_file()
    file_body = debt_md.read_text(encoding="utf-8")
    stdout_body = capsys.readouterr().out

    # --write ALSO prints to stdout; the persisted file matches what was printed.
    assert file_body == stdout_body
    assert "3 markers, 2 with no trigger." in file_body
    assert "api/routes.py:2" in file_body


@pytest.mark.integration
def test_write_creates_context_dir_when_absent(debt_repo: Path) -> None:
    assert not (debt_repo / ".context").exists()
    rc = debt.run(["--root", str(debt_repo), "--write"])
    assert rc == 0
    assert (debt_repo / ".context" / "debt.md").is_file()


# ----- --json: stable parseable structure -----------------------------------


@pytest.mark.integration
def test_json_emits_stable_parseable_structure(
    debt_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = debt.run(["--root", str(debt_repo), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["total"] == 3
    assert payload["no_trigger_count"] == 2
    assert isinstance(payload["rows"], list)
    # Rows are the DebtLedger.to_dict() shape, repo-relative.
    paths = [row["rel_path"] for row in payload["rows"]]
    assert "api/routes.py" in paths
    assert all(not Path(p).is_absolute() for p in paths)


@pytest.mark.integration
def test_json_write_persists_markdown_not_json(debt_repo: Path) -> None:
    """``--write --json`` prints JSON to stdout but still persists *markdown*
    to ``.context/debt.md`` (the on-disk ledger is always the human view)."""
    rc = debt.run(["--root", str(debt_repo), "--json", "--write"])
    assert rc == 0
    debt_md = (debt_repo / ".context" / "debt.md").read_text(encoding="utf-8")
    # The persisted file is markdown (has the tally line), not a JSON blob.
    assert "3 markers, 2 with no trigger." in debt_md
    assert not debt_md.lstrip().startswith("{")


# ----- determinism ----------------------------------------------------------


@pytest.mark.integration
def test_repeated_runs_are_byte_identical(
    debt_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    debt.run(["--root", str(debt_repo)])
    first = capsys.readouterr().out
    debt.run(["--root", str(debt_repo)])
    second = capsys.readouterr().out
    assert first == second
