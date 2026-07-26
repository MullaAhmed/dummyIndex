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
from dummyindex.installer.link import relative_link_value


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


def _require_real_symlinks(tmp_path: Path) -> None:
    """Skip the calling test when this environment cannot create symlinks.

    Mirrors `tests/test_install_link_primitives.py`'s guard of the same
    name — only real-symlink tests need it; the `MATERIALIZED` case is a
    plain regular file and needs no capability check.
    """
    probe = tmp_path / ".check-versions-symlink-probe"
    target = tmp_path / ".check-versions-symlink-target"
    target.mkdir(exist_ok=True)
    try:
        probe.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
        return
    probe.unlink()


def _seed_agents_family(root: Path, version: str) -> None:
    """Real `.agents/skills/dummyindex` — the link target — stamped."""
    agents_dir = root / ".agents" / "skills" / "dummyindex"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / ".dummyindex_version").write_text(version, encoding="utf-8")


def _link_claude_family(root: Path) -> None:
    """`.claude/skills/dummyindex` as the real relative symlink to `.agents`."""
    claude_skills = root / ".claude" / "skills"
    claude_skills.mkdir(parents=True, exist_ok=True)
    (claude_skills / "dummyindex").symlink_to(
        relative_link_value("dummyindex"), target_is_directory=True
    )


def _materialize_claude_family(root: Path) -> None:
    """`.claude/skills/dummyindex` as a REGULAR FILE holding the exact link
    value — the `core.symlinks=false` Windows-checkout shape."""
    claude_skills = root / ".claude" / "skills"
    claude_skills.mkdir(parents=True, exist_ok=True)
    (claude_skills / "dummyindex").write_text(
        relative_link_value("dummyindex"), encoding="utf-8"
    )


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


# ----- link-state labels (symlink-single-source-install, check --versions) ---


@pytest.mark.integration
def test_versions_reports_linked_ours_healthy_as_linked_and_coherent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fully-linked layout (real `.agents`, `.claude` symlinked to it)
    reads a coherent stamp AND names the Claude row as linked — the
    "consistent versions, not duplicated" acceptance case."""
    _require_real_symlinks(tmp_path)
    _prime(tmp_path, skill_stamp=None, meta_version="0.31.0")
    _seed_agents_family(tmp_path, "0.31.0")
    _link_claude_family(tmp_path)
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "coherent" in out.lower()
    assert "repo Claude skill (linked)" in out
    assert "0.31.0" in out
    assert "materialized link" not in out


@pytest.mark.integration
def test_versions_reports_dangling_link_as_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`OURS_DANGLING` is still `OURS_*` — the symlink is ours, only its
    `.agents` target is missing — so the row still says `(linked)`."""
    _require_real_symlinks(tmp_path)
    _prime(tmp_path, skill_stamp=None, meta_version="0.31.0")
    _link_claude_family(tmp_path)  # no `.agents/skills/dummyindex` target
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "repo Claude skill (linked)" in out


@pytest.mark.integration
def test_versions_reports_materialized_file_with_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`MATERIALIZED` (the `core.symlinks=false` Windows-checkout shape: a
    REGULAR FILE holding the exact link value) reports its own label plus
    the `git config core.symlinks true` + re-checkout remediation — no real
    symlink capability is needed for this state."""
    _prime(tmp_path, skill_stamp=None, meta_version="0.31.0")
    _materialize_claude_family(tmp_path)
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "repo Claude skill (materialized link" in out
    assert "core.symlinks" in out
    assert "re-checkout" in out


@pytest.mark.integration
def test_versions_plain_real_copy_has_no_link_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: an ordinary (non-linked) real `.claude` copy is
    unchanged — no `(linked)`/`(materialized link)` suffix is added."""
    _prime(tmp_path, skill_stamp="0.31.0", meta_version="0.31.0")
    monkeypatch.setattr(check, "_running_version", lambda: "0.31.0")

    rc = check.run(["--versions", str(tmp_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "coherent" in out.lower()
    # Coherent + not linked: no per-layer breakdown at all (unchanged from
    # before this change), and definitely no link-state suffix.
    assert "(linked)" not in out
    assert "materialized link" not in out
