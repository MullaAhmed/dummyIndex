"""Tests for `dummyindex install` / `uninstall` (Claude-only CLI surface)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.__main__ import SKILL_REL, _parse_install_args, install, uninstall


@pytest.mark.unit
def test_parse_defaults_user_scope_no_dir() -> None:
    assert _parse_install_args([]) == ("user", None)


@pytest.mark.unit
def test_parse_scope_long_form() -> None:
    assert _parse_install_args(["--scope", "project"]) == ("project", None)


@pytest.mark.unit
def test_parse_scope_equals_form() -> None:
    assert _parse_install_args(["--scope=project"]) == ("project", None)


@pytest.mark.unit
def test_parse_dir_long_form(tmp_path: Path) -> None:
    scope, project_dir = _parse_install_args(["--scope", "project", "--dir", str(tmp_path)])
    assert scope == "project"
    assert project_dir == tmp_path


@pytest.mark.unit
def test_parse_dir_equals_form(tmp_path: Path) -> None:
    scope, project_dir = _parse_install_args([f"--dir={tmp_path}"])
    assert scope == "user"
    assert project_dir == tmp_path


@pytest.mark.integration
def test_install_project_scope_writes_repo_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install(scope="project", project_dir=tmp_path)
    expected = tmp_path / SKILL_REL
    assert expected.exists()
    body = expected.read_text(encoding="utf-8")
    assert "dummyindex" in body
    # Project install must NOT touch the user-global ~/.claude/CLAUDE.md
    out = capsys.readouterr().out
    assert "~/.claude/CLAUDE.md" not in out
    assert "skill registered" not in out


@pytest.mark.integration
def test_install_project_scope_writes_version_stamp(tmp_path: Path) -> None:
    install(scope="project", project_dir=tmp_path)
    version_file = (tmp_path / SKILL_REL).parent / ".dummyindex_version"
    assert version_file.exists()
    assert version_file.read_text(encoding="utf-8").strip()  # non-empty


@pytest.mark.integration
def test_install_copies_companion_markdowns(tmp_path: Path) -> None:
    """SKILL.md references agents/, council/, retrieval/ — they must all install."""
    install(scope="project", project_dir=tmp_path)
    skill_dir = (tmp_path / SKILL_REL).parent
    # SKILL.md itself
    assert (skill_dir / "SKILL.md").exists()
    # All three companion subdirs
    for subdir in ("agents", "council", "retrieval"):
        sub = skill_dir / subdir
        assert sub.is_dir(), f"missing {sub}"
        # Each has at least one markdown
        mds = list(sub.glob("*.md"))
        assert mds, f"no markdowns under {sub}"
    # Personas: all six
    personas = {p.stem for p in (skill_dir / "agents").glob("*.md")}
    assert personas == {
        "architect",
        "chairman",
        "database-engineer",
        "product-manager",
        "security-analyst",
        "senior-developer",
    }


@pytest.mark.integration
def test_uninstall_removes_companion_markdowns(tmp_path: Path) -> None:
    install(scope="project", project_dir=tmp_path)
    skill_dir = (tmp_path / SKILL_REL).parent
    assert (skill_dir / "agents").is_dir()  # precondition

    from dummyindex.__main__ import uninstall as uninstall_fn
    uninstall_fn(scope="project", project_dir=tmp_path)
    assert not (tmp_path / SKILL_REL).exists()
    # Companion dirs removed too
    for subdir in ("agents", "council", "retrieval"):
        assert not (skill_dir / subdir).exists(), (
            f"{subdir} should have been removed by uninstall"
        )


@pytest.mark.integration
def test_uninstall_project_scope_removes_skill(tmp_path: Path) -> None:
    install(scope="project", project_dir=tmp_path)
    skill_path = tmp_path / SKILL_REL
    assert skill_path.exists()

    uninstall(scope="project", project_dir=tmp_path)
    assert not skill_path.exists()


@pytest.mark.unit
def test_install_rejects_unknown_scope(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as exc:
        install(scope="bogus", project_dir=tmp_path)
    assert exc.value.code == 1
    assert "must be 'user' or 'project'" in capsys.readouterr().err


@pytest.mark.unit
def test_uninstall_silent_when_nothing_to_remove(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    uninstall(scope="project", project_dir=tmp_path)
    assert "nothing to remove" in capsys.readouterr().out


@pytest.mark.unit
def test_parse_accepts_legacy_platform_flag() -> None:
    """`dummyindex install --platform claude` from old docs still works."""
    assert _parse_install_args(["--platform", "claude"]) == ("user", None)
    assert _parse_install_args(["--platform=claude"]) == ("user", None)


@pytest.mark.unit
def test_parse_rejects_unknown_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        _parse_install_args(["--definitely-not-a-flag"])
    assert exc.value.code == 2
    assert "unknown install argument" in capsys.readouterr().err


@pytest.mark.integration
def test_install_user_scope_uses_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default scope writes to $HOME/.claude/skills/dummyindex/SKILL.md and
    registers in $HOME/.claude/CLAUDE.md."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    # Path.home() reads HOME on POSIX.
    install(scope="user")

    skill_dst = fake_home / SKILL_REL
    assert skill_dst.exists()
    claude_md = fake_home / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "dummyindex" in claude_md.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "skill installed" in out
    assert str(skill_dst) in out
