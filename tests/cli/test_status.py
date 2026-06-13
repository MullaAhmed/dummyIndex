"""`dummyindex context status` — a read-only overview that never mutates.

Models repeatedly guessed `dummyindex --status` / `dummyindex status` because
the only statuses were buried per-domain. This composes the existing read-only
helpers (enriched-index verdict, commit-anchored drift, equipment manifest,
proposal counts) into one summary and exits 0 even on an un-indexed repo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.mark.unit
def test_status_uninitialized_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No .context/ → exit 0, says 'not initialized', writes nothing."""
    from dummyindex.cli import dispatch

    before = _snapshot(tmp_path)
    code = dispatch(["status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "not initialized" in out.lower() or "not indexed" in out.lower()
    assert _snapshot(tmp_path) == before


@pytest.mark.unit
def test_status_json_uninitialized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from dummyindex.cli import dispatch

    code = dispatch(["status", "--json", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["initialized"] is False


@pytest.mark.unit
def test_status_indexed_repo_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fixture .context reports index presence + equipment + drift fields."""
    from dummyindex.cli import dispatch

    context_dir = tmp_path / ".context"
    (context_dir / "map").mkdir(parents=True)
    (context_dir / "meta.json").write_text(
        json.dumps(
            {
                "dummyindex_version": "0.25.0",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "root": str(tmp_path),
                "file_count": 3,
                "symbol_count": 9,
                "indexed_commit": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (context_dir / "equipment.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "items": [
                    {
                        "kind": "agent",
                        "name": "x-implementer",
                        "path": ".claude/agents/x.md",
                        "source": "generated",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    before = _snapshot(tmp_path)
    code = dispatch(["status", "--json", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["initialized"] is True
    assert payload["equipment"]["present"] is True
    assert payload["equipment"]["items"] == 1
    assert "drift" in payload
    assert _snapshot(tmp_path) == before


@pytest.mark.unit
def test_top_level_status_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dummyindex status` aliases to `context status` like ingest→init."""
    from dummyindex import __main__

    monkeypatch.setattr(
        __main__.sys, "argv", ["dummyindex", "status", "--root", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.strip()
