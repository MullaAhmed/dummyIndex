"""Tests for `dummyindex install` / `uninstall` (Claude-only CLI surface)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.__main__ import SKILL_REL, _parse_install_args, install, uninstall


@pytest.mark.unit
def test_parse_defaults_user_scope_no_dir() -> None:
    assert _parse_install_args([]) == ("user", None, False)


@pytest.mark.unit
def test_parse_scope_long_form() -> None:
    assert _parse_install_args(["--scope", "project"]) == ("project", None, False)


@pytest.mark.unit
def test_parse_scope_equals_form() -> None:
    assert _parse_install_args(["--scope=project"]) == ("project", None, False)


@pytest.mark.unit
def test_parse_dir_long_form(tmp_path: Path) -> None:
    scope, project_dir, skill_only = _parse_install_args(
        ["--scope", "project", "--dir", str(tmp_path)]
    )
    assert scope == "project"
    assert project_dir == tmp_path
    assert skill_only is False


@pytest.mark.unit
def test_parse_dir_equals_form(tmp_path: Path) -> None:
    scope, project_dir, skill_only = _parse_install_args([f"--dir={tmp_path}"])
    assert scope == "user"
    assert project_dir == tmp_path
    assert skill_only is False


@pytest.mark.unit
def test_parse_skill_only_flag() -> None:
    """`--skill-only` opts out of the auto-init step added in v0.13.4."""
    assert _parse_install_args(["--skill-only"]) == ("user", None, True)
    assert _parse_install_args(["--scope=project", "--skill-only"]) == (
        "project",
        None,
        True,
    )


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
    assert _parse_install_args(["--platform", "claude"]) == ("user", None, False)
    assert _parse_install_args(["--platform=claude"]) == ("user", None, False)


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
    # Chdir into a clean tmp dir (no .git/) so the v0.13.4 auto-init step
    # doesn't fire and try to index the test runner's cwd.
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.chdir(clean_cwd)
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
    # No .git/ in clean_cwd, so auto-init was skipped and the message says so.
    assert "skipped project init" in out


# ----- auto-init added in v0.13.4 -------------------------------------------
# When `install` is run with a project_dir (or from a cwd) that contains
# a `.git/`, the install also builds .context/, writes CLAUDE.md, and
# installs the auto-refresh hooks — so a fresh user gets the full setup in
# one command instead of needing `install` + `ingest` separately.


def _make_repo_with_source(target: Path) -> None:
    """Minimal git repo with one Python source file — enough for `build_all`
    to produce a non-empty `.context/` without depending on the sample
    fixture's exact structure."""
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir()
    # A bare-enough .git/ — build_all only looks for the marker dir; it
    # doesn't run actual git commands during scaffold.
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (target / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n",
        encoding="utf-8",
    )


@pytest.mark.integration
def test_install_auto_init_runs_when_project_is_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`install --scope project --dir <repo>` on a real git repo also builds
    `.context/`, writes CLAUDE.md, and installs the auto-refresh hooks."""
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)

    # Skill landed in repo's .claude/ as usual.
    assert (repo / SKILL_REL).exists()
    # Auto-init produced .context/.
    assert (repo / ".context").is_dir()
    assert (repo / ".context" / "INDEX.md").exists()
    # Auto-init wrote a project CLAUDE.md.
    project_claude_md = repo / ".claude" / "CLAUDE.md"
    assert project_claude_md.exists()
    # Auto-init installed the three hooks.
    assert (repo / ".git" / "hooks" / "post-commit").exists()
    settings = repo / ".claude" / "settings.json"
    assert settings.exists()
    assert "DUMMYINDEX_AUTO_REFRESH" in settings.read_text(encoding="utf-8")

    out = capsys.readouterr().out
    assert ".context/" in out
    assert "hooks" in out


@pytest.mark.integration
def test_install_skill_only_skips_auto_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--skill-only` opts out of auto-init even when cwd is a git repo —
    useful for re-running the installer without touching project state."""
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, skill_only=True)

    # Skill installed.
    assert (repo / SKILL_REL).exists()
    # But auto-init artifacts did NOT appear.
    assert not (repo / ".context").exists()
    assert not (repo / ".git" / "hooks" / "post-commit").exists()


@pytest.mark.integration
def test_install_no_auto_init_when_not_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A target directory without `.git/` triggers a friendly skip message,
    not a silent half-install."""
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "app.py").write_text("print('hi')\n", encoding="utf-8")
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=bare)

    assert (bare / SKILL_REL).exists()
    assert not (bare / ".context").exists()
    out = capsys.readouterr().out
    assert "skipped project init" in out
    assert "no .git/" in out
