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


def _write_config(context_dir: Path, payload: dict) -> None:
    context_dir.mkdir(parents=True, exist_ok=True)
    (context_dir / "config.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _indexed_meta(tmp_path: Path) -> None:
    """Write the minimal .context fixture so status treats the repo as indexed."""
    context_dir = tmp_path / ".context"
    (context_dir / "map").mkdir(parents=True, exist_ok=True)
    (context_dir / "meta.json").write_text(
        json.dumps(
            {
                "dummyindex_version": "0.27.0",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "root": str(tmp_path),
                "file_count": 1,
                "symbol_count": 1,
                "indexed_commit": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_status_surfaces_depth_wired_and_config_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """status renders effective depth per command, wired classification counts,
    and a config-writer-version line labelled apart from the build stamp."""
    from dummyindex.cli import dispatch

    context_dir = tmp_path / ".context"
    _indexed_meta(tmp_path)
    _write_config(
        context_dir,
        {
            "schema_version": 2,
            "scope": "repo",
            "scope_path": None,
            "mode": "deep",
            "model": "sonnet-4.6",
            "auto_refresh_hook": True,
            "external_docs": [],
            "reconcile_exclude": [],
            "command_depths": {"reconcile": "light"},
            "wired": [
                {
                    "kind": "plugin",
                    "target": "superpowers@claude-plugins-official",
                    "version": None,
                },
                {"kind": "skill", "target": "some-skill", "version": None},
            ],
            "dummyindex_version": "9.9.9",
        },
    )

    code = dispatch(["status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0

    # Effective depth per command: reconcile overridden to light, others fall
    # back to the global `mode` (deep).
    assert "reconcile=light" in out
    assert "ingest=deep" in out
    assert "audit=deep" in out
    assert "build=deep" in out

    # Wired classification counts (skill entry => needs-user; the plugin is
    # declared-but-absent => acted, since no settings.json decision exists).
    assert "2 declared" in out
    assert "1 acted" in out
    assert "1 needs-user" in out

    # Config-writer-version line, distinct from the build/CLI version line.
    assert "config:     written by 9.9.9" in out
    assert "9.9.9" not in out.split("config:")[0]  # not on the build line


@pytest.mark.unit
def test_status_classifies_satisfied_wired_plugin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A plugin already decided in .claude/settings.json counts satisfied,
    NOT acted — status reads presence, it never wires."""
    from dummyindex.cli import dispatch

    context_dir = tmp_path / ".context"
    _indexed_meta(tmp_path)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"superpowers@claude-plugins-official": True}})
        + "\n",
        encoding="utf-8",
    )
    _write_config(
        context_dir,
        {
            "schema_version": 2,
            "scope": "repo",
            "scope_path": None,
            "mode": "standard",
            "model": "sonnet-4.6",
            "auto_refresh_hook": True,
            "external_docs": [],
            "reconcile_exclude": [],
            "command_depths": {},
            "wired": [
                {
                    "kind": "plugin",
                    "target": "superpowers@claude-plugins-official",
                    "version": None,
                }
            ],
            "dummyindex_version": "1.0.0",
        },
    )

    code = dispatch(["status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "1 satisfied" in out
    assert "0 acted" in out


@pytest.mark.unit
def test_status_does_not_mutate_config(tmp_path: Path) -> None:
    """status is read-only: config.json bytes are identical before and after."""
    from dummyindex.cli import dispatch

    context_dir = tmp_path / ".context"
    _indexed_meta(tmp_path)
    _write_config(
        context_dir,
        {
            "schema_version": 2,
            "scope": "repo",
            "scope_path": None,
            "mode": "standard",
            "model": "sonnet-4.6",
            "auto_refresh_hook": True,
            "external_docs": [],
            "reconcile_exclude": [],
            "command_depths": {"build": "deep"},
            "wired": [
                {
                    "kind": "plugin",
                    "target": "superpowers@claude-plugins-official",
                    "version": None,
                }
            ],
            "dummyindex_version": "1.0.0",
        },
    )
    config_path = context_dir / "config.json"
    settings_path = tmp_path / ".claude" / "settings.json"
    before_config = config_path.read_bytes()
    fs_before = _snapshot(tmp_path)

    code = dispatch(["status", "--root", str(tmp_path)])

    assert code == 0
    assert config_path.read_bytes() == before_config
    # status must never wire — no settings.json materialized as a side effect.
    assert not settings_path.exists()
    assert _snapshot(tmp_path) == fs_before


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
