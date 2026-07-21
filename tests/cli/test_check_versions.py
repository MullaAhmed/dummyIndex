"""Tests for `dummyindex context check --versions` — multi-layer skew report.

Detection-only: reports divergence between the running CLI, the repo's
installed Claude/Codex skill stamps at repo and user scope, the
`.context/meta.json` stamp, and a PATH-shadowing venv binary. Warn-only —
always exit 0, never block, never touch the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import check


@pytest.fixture(autouse=True)
def _isolated_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep user-scope stamp discovery deterministic and off the real home."""
    user_home = tmp_path / "user-home"
    user_home.mkdir()
    monkeypatch.setattr(check, "_user_home", lambda: user_home)


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


def _stamp(base: Path, host: str, version: str) -> None:
    host_dir = ".claude" if host == "Claude" else ".agents"
    skill_dir = base / host_dir / "skills" / "dummyindex"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / ".dummyindex_version").write_text(version, encoding="utf-8")


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
    assert "dummyindex-update" in out
    assert "/dummyindex-update" not in out
    assert "$dummyindex-update" not in out


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
def test_versions_reads_codex_skill_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prime(tmp_path, skill_stamp=None, meta_version="0.31.0")
    skill_dir = tmp_path / ".agents" / "skills" / "dummyindex"
    skill_dir.mkdir(parents=True)
    (skill_dir / ".dummyindex_version").write_text("0.31.0", encoding="utf-8")
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    assert check.run(["--versions", str(tmp_path)]) == 0
    assert "coherent" in capsys.readouterr().out.lower()


@pytest.mark.integration
def test_versions_compares_coexisting_claude_and_codex_stamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prime(tmp_path, skill_stamp="0.31.0", meta_version="0.31.0")
    _stamp(tmp_path, "Codex", "0.31.0")
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    assert check.run(["--versions", str(tmp_path)]) == 0
    assert "coherent" in capsys.readouterr().out.lower()


@pytest.mark.integration
def test_versions_surfaces_every_host_and_scope_when_one_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    user_home = tmp_path / "user-home"
    _prime(tmp_path, skill_stamp="0.31.0", meta_version="0.31.0")
    _stamp(tmp_path, "Codex", "0.30.0")
    _stamp(user_home, "Claude", "0.29.0")
    _stamp(user_home, "Codex", "0.28.0")
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    assert check.run(["--versions", str(tmp_path)]) == 0
    out = capsys.readouterr().out

    assert "skew" in out.lower()
    for label, version in (
        ("repo Claude skill", "0.31.0"),
        ("repo Codex skill", "0.30.0"),
        ("user Claude skill", "0.29.0"),
        ("user Codex skill", "0.28.0"),
    ):
        assert label in out
        assert version in out
    assert "dummyindex-update" in out
    assert "/dummyindex-update" not in out
    assert "$dummyindex-update" not in out


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
    monkeypatch.setattr(
        check, "_global_binary", lambda: Path("/usr/local/bin/dummyindex")
    )

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "shadow" in out.lower()
    assert "/venv/bin/dummyindex" in out
