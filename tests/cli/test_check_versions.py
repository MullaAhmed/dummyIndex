"""Tests for `dummyindex context check --versions` — multi-layer skew report.

Detection-only: reports divergence between the running CLI, the repo's
installed skill stamp, the `.context/meta.json` stamp, and a PATH-shadowing
venv binary. Warn-only — always exit 0, never block, never touch the network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import check


def _prime(root: Path, *, skill_stamp: str | None, meta_version: str | None) -> None:
    ctx = root / ".context"
    ctx.mkdir(parents=True, exist_ok=True)
    if meta_version is not None:
        (ctx / "meta.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "dummyindex_version": meta_version,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                    "root": str(root),
                }
            ),
            encoding="utf-8",
        )
    if skill_stamp is not None:
        skill_dir = root / ".claude" / "skills" / "dummyindex"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / ".dummyindex_version").write_text(skill_stamp, encoding="utf-8")


@pytest.mark.integration
def test_versions_reports_skew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prime(tmp_path, skill_stamp="0.22.0", meta_version="0.15.0")
    monkeypatch.setattr(check, "_running_version", lambda: "0.25.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0  # warn-only, never blocks
    out = capsys.readouterr().out
    assert "0.25.0" in out  # running CLI
    assert "0.22.0" in out  # skill stamp
    assert "0.15.0" in out  # meta stamp
    # Names the skew + nudges the user to update.
    assert "skew" in out.lower() or "mismatch" in out.lower()
    assert "/dummyindex-update" in out


@pytest.mark.integration
def test_versions_coherent_when_all_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prime(tmp_path, skill_stamp="0.25.0", meta_version="0.25.0")
    monkeypatch.setattr(check, "_running_version", lambda: "0.25.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "coherent" in out.lower()


@pytest.mark.integration
def test_versions_tolerates_missing_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # No skill stamp, no meta.json — only the running CLI is known.
    (tmp_path / ".context").mkdir(parents=True)
    monkeypatch.setattr(check, "_running_version", lambda: "0.25.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0  # missing layers must not error


@pytest.mark.integration
def test_versions_warns_on_shadowed_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prime(tmp_path, skill_stamp="0.25.0", meta_version="0.25.0")
    monkeypatch.setattr(check, "_running_version", lambda: "0.25.0")
    # Running binary differs from the global on PATH → shadow.
    monkeypatch.setattr(check, "_running_binary", lambda: Path("/venv/bin/dummyindex"))
    monkeypatch.setattr(check, "_global_binary", lambda: Path("/usr/local/bin/dummyindex"))

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "shadow" in out.lower()
    assert "/venv/bin/dummyindex" in out
