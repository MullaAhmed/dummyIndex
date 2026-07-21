"""Tests for the Claude Code + Codex installer surfaces."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest

import dummyindex.context.default_plugins as default_plugins_module
from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    SKIP_INSTALL_ENV,
    RunResult,
    WiredEntry,
    WiredKind,
    default_wired,
)
from dummyindex.context.domains.config import (
    CONFIG_SCHEMA_VERSION,
    default_config,
    read_config,
    write_config,
)
from dummyindex.context.output.bootstrap import ALWAYS_ON_OUTPUT_POLICY
from dummyindex.installer import (
    CODEX_SKILL_REL,
    SKILL_REL,
    install,
    parse_install_args,
    parse_uninstall_args,
    uninstall,
)


class _RecordingRunner:
    """Successful injected Claude runner with exact argv/provenance capture."""

    def __init__(self, capture_output: Callable[[], str] | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.output_before_first_call: str | None = None
        self._capture_output = capture_output

    def __call__(self, argv: list[str], _cwd: Path) -> RunResult:
        if not self.calls and self._capture_output is not None:
            self.output_before_first_call = self._capture_output()
        self.calls.append(tuple(argv))
        return RunResult(0, "ok", "")


_DEFAULT_TARGETS = tuple(plugin.target for plugin in DEFAULT_PLUGINS)
installer_module = import_module("dummyindex.installer.install")


@pytest.mark.unit
def test_parse_defaults_user_scope_no_dir() -> None:
    assert parse_install_args([]) == (
        "user",
        None,
        False,
        False,
        False,
        False,
        "claude",
    )


@pytest.mark.unit
def test_parse_scope_long_form() -> None:
    assert parse_install_args(["--scope", "project"]) == (
        "project",
        None,
        False,
        False,
        False,
        False,
        "claude",
    )


@pytest.mark.unit
def test_parse_scope_equals_form() -> None:
    assert parse_install_args(["--scope=project"]) == (
        "project",
        None,
        False,
        False,
        False,
        False,
        "claude",
    )


@pytest.mark.unit
def test_parse_dir_long_form(tmp_path: Path) -> None:
    (
        scope,
        project_dir,
        skill_only,
        no_onboarding,
        defaults,
        no_superpowers,
        platform,
    ) = parse_install_args(["--scope", "project", "--dir", str(tmp_path)])
    assert scope == "project"
    assert project_dir == tmp_path
    assert skill_only is False
    assert no_onboarding is False
    assert defaults is False
    assert no_superpowers is False
    assert platform == "claude"


@pytest.mark.unit
def test_parse_dir_equals_form(tmp_path: Path) -> None:
    scope, project_dir, skill_only, _no_onboarding, _defaults, *_ = parse_install_args(
        [f"--dir={tmp_path}"]
    )
    assert scope == "user"
    assert project_dir == tmp_path
    assert skill_only is False


@pytest.mark.unit
def test_parse_skill_only_flag() -> None:
    """`--skill-only` opts out of the auto-init step added in v0.13.4."""
    assert parse_install_args(["--skill-only"]) == (
        "user",
        None,
        True,
        False,
        False,
        False,
        "claude",
    )
    assert parse_install_args(["--scope=project", "--skill-only"]) == (
        "project",
        None,
        True,
        False,
        False,
        False,
        "claude",
    )


@pytest.mark.unit
def test_parse_no_onboarding_and_defaults_flags() -> None:
    """v0.14: --no-onboarding and --defaults document the CI intent."""
    assert parse_install_args(["--no-onboarding"]) == (
        "user",
        None,
        False,
        True,
        False,
        False,
        "claude",
    )
    assert parse_install_args(["--defaults"]) == (
        "user",
        None,
        False,
        False,
        True,
        False,
        "claude",
    )
    assert parse_install_args(["--no-onboarding", "--defaults"]) == (
        "user",
        None,
        False,
        True,
        True,
        False,
        "claude",
    )


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--no-default-plugins", "--no-superpowers"])
def test_parse_default_plugin_opt_out_aliases(flag: str) -> None:
    assert parse_install_args([flag]) == (
        "user",
        None,
        False,
        False,
        False,
        True,
        "claude",
    )
    assert parse_install_args([])[-1] == "claude"


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
def test_install_codex_project_scope_writes_discoverable_skill_family(
    tmp_path: Path,
) -> None:
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="codex",
    )

    main = tmp_path / CODEX_SKILL_REL
    assert main.exists()
    body = main.read_text(encoding="utf-8")
    assert body.startswith("---\n")
    assert "## Codex host compatibility" in body
    assert "$<skill-name>" in body
    assert "--platform codex" in body
    assert "native `/status`" in body
    assert "Claude's `Read`, `Write`, `Edit`, `Bash`" in body
    assert "Codex's native file reading/search" in body

    skills_root = tmp_path / ".agents" / "skills"
    for name in (
        "dummyindex-remember",
        "dummyindex-plan",
        "dummyindex-equip",
        "dummyindex-build",
        "dummyindex-audit",
        "dummyindex-gc",
        "dummyindex-update",
    ):
        sibling = skills_root / name / "SKILL.md"
        assert sibling.exists(), f"missing Codex skill ${name}"
        assert "## Codex host compatibility" in sibling.read_text(encoding="utf-8")

    build_skill = skills_root / "dummyindex-build" / "SKILL.md"
    build_text = build_skill.read_text(encoding="utf-8")
    reconcile_rel = Path("../dummyindex/council/65-reconcile.md")
    assert reconcile_rel.as_posix() in build_text
    assert (build_skill.parent / reconcile_rel).resolve().is_file()

    assert not (tmp_path / ".claude").exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    "linked_rel",
    [
        Path(".agents"),
        Path(".agents/skills/dummyindex"),
        Path(".agents/skills/dummyindex/agents"),
        Path(".agents/skills/dummyindex-plan"),
        Path(".agents/skills/dummyindex-audit/agents"),
    ],
)
def test_install_refuses_symlinked_skill_directory_without_touching_target(
    tmp_path: Path, linked_rel: Path
) -> None:
    target = tmp_path / "external-skill-directory"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("external content\n", encoding="utf-8")
    linked_dir = tmp_path / linked_rel
    linked_dir.parent.mkdir(parents=True, exist_ok=True)
    linked_dir.symlink_to(target, target_is_directory=True)

    with pytest.raises(SystemExit) as exc:
        install(
            scope="project",
            project_dir=tmp_path,
            skill_only=True,
            platform="codex",
        )

    assert exc.value.code == 1
    assert linked_dir.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "external content\n"
    assert not (tmp_path / ".agents" / "skills" / "dummyindex-update").exists()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("platform", "host_root", "installed_rel"),
    [
        ("claude", ".claude", SKILL_REL),
        ("codex", ".agents", CODEX_SKILL_REL),
    ],
)
def test_user_scope_install_and_uninstall_follow_host_root_dotfiles_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    host_root: str,
    installed_rel: Path,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    dotfiles_target = fake_home / "dotfiles" / host_root.lstrip(".")
    dotfiles_target.mkdir(parents=True)
    host_link = fake_home / host_root
    host_link.symlink_to(dotfiles_target, target_is_directory=True)
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(clean_cwd)

    install(scope="user", skill_only=True, platform=platform)

    assert host_link.is_symlink()
    assert (fake_home / installed_rel).is_file()
    if platform == "claude":
        assert (host_link / "commands" / "tokens.md").is_file()

    uninstall(scope="user", platform=platform)

    assert host_link.is_symlink()
    assert not (fake_home / installed_rel).exists()
    if platform == "claude":
        assert not (host_link / "commands" / "tokens.md").exists()


@pytest.mark.integration
@pytest.mark.parametrize("invalid_target", ["dangling", "loop", "file"])
def test_user_scope_install_rejects_unusable_host_root_symlink_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_target: str,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    host_link = fake_home / ".agents"
    if invalid_target == "dangling":
        host_link.symlink_to(fake_home / "missing", target_is_directory=True)
    elif invalid_target == "loop":
        host_link.symlink_to(host_link, target_is_directory=True)
    else:
        target_file = fake_home / "agents-file"
        target_file.write_text("not a directory\n", encoding="utf-8")
        host_link.symlink_to(target_file)
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(clean_cwd)

    with pytest.raises(SystemExit) as exc:
        install(scope="user", skill_only=True, platform="codex")

    assert exc.value.code == 1
    assert "refusing to install through user host root symlink" in (
        capsys.readouterr().err
    )
    assert host_link.is_symlink()


@pytest.mark.integration
def test_user_scope_both_prevalidates_host_root_links_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".agents").symlink_to(
        fake_home / "missing-agents", target_is_directory=True
    )
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(clean_cwd)

    with pytest.raises(SystemExit) as exc:
        install(scope="user", skill_only=True, platform="both")

    assert exc.value.code == 1
    assert not (fake_home / ".claude").exists()


@pytest.mark.integration
def test_user_scope_host_root_symlink_does_not_allow_deeper_skill_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    agents_target = fake_home / "dotfiles" / "agents"
    linked_skill = agents_target / "skills" / "dummyindex"
    linked_skill.parent.mkdir(parents=True)
    external = fake_home / "external-skill"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("user content\n", encoding="utf-8")
    linked_skill.symlink_to(external, target_is_directory=True)
    (fake_home / ".agents").symlink_to(agents_target, target_is_directory=True)
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(clean_cwd)

    with pytest.raises(SystemExit) as exc:
        install(scope="user", skill_only=True, platform="codex")

    assert exc.value.code == 1
    assert linked_skill.is_symlink()
    assert sentinel.read_text(encoding="utf-8") == "user content\n"


@pytest.mark.integration
def test_install_replaces_companion_file_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    agents_dir = tmp_path / ".agents" / "skills" / "dummyindex-audit" / "agents"
    agents_dir.mkdir(parents=True)
    external = tmp_path / "external-security.md"
    external.write_text("external content\n", encoding="utf-8")
    destination = agents_dir / "security.md"
    destination.symlink_to(external)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="codex",
    )

    assert not destination.is_symlink()
    assert destination.is_file()
    assert external.read_text(encoding="utf-8") == "external content\n"


@pytest.mark.integration
def test_install_both_writes_both_host_skill_trees(tmp_path: Path) -> None:
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
    )

    assert (tmp_path / SKILL_REL).exists()
    assert (tmp_path / CODEX_SKILL_REL).exists()
    assert (tmp_path / ".claude" / "commands" / "tokens.md").exists()


@pytest.mark.integration
def test_uninstall_codex_removes_only_codex_skill_family(tmp_path: Path) -> None:
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
    )

    uninstall(scope="project", project_dir=tmp_path, platform="codex")

    assert not (tmp_path / CODEX_SKILL_REL).exists()
    assert not (tmp_path / ".agents" / "skills" / "dummyindex-plan").exists()
    assert (tmp_path / SKILL_REL).exists()


@pytest.mark.integration
def test_uninstall_unlinks_symlinked_skill_dirs_without_touching_targets(
    tmp_path: Path,
) -> None:
    skills_root = tmp_path / ".agents" / "skills"
    skills_root.mkdir(parents=True)
    main_target = tmp_path / "external-main"
    main_target.mkdir()
    (main_target / "SKILL.md").write_text("main target\n", encoding="utf-8")
    (main_target / "agents").mkdir()
    (main_target / "agents" / "keep.md").write_text("keep main\n", encoding="utf-8")
    main_link = skills_root / "dummyindex"
    main_link.symlink_to(main_target, target_is_directory=True)

    sibling_target = tmp_path / "external-plan"
    sibling_target.mkdir()
    (sibling_target / "SKILL.md").write_text("plan target\n", encoding="utf-8")
    sibling_link = skills_root / "dummyindex-plan"
    sibling_link.symlink_to(sibling_target, target_is_directory=True)

    uninstall(scope="project", project_dir=tmp_path, platform="codex")

    assert not main_link.is_symlink()
    assert not sibling_link.is_symlink()
    assert (main_target / "SKILL.md").read_text(encoding="utf-8") == "main target\n"
    assert (main_target / "agents" / "keep.md").read_text(encoding="utf-8") == (
        "keep main\n"
    )
    assert (sibling_target / "SKILL.md").read_text(encoding="utf-8") == (
        "plan target\n"
    )


@pytest.mark.integration
def test_uninstall_does_not_follow_nested_sibling_directory_symlink(
    tmp_path: Path,
) -> None:
    sibling = tmp_path / ".agents" / "skills" / "dummyindex-plan"
    sibling.mkdir(parents=True)
    (sibling / "SKILL.md").write_text("installed\n", encoding="utf-8")
    external = tmp_path / "external-nested"
    external.mkdir()
    (external / "keep.md").write_text("keep nested\n", encoding="utf-8")
    (sibling / "nested").symlink_to(external, target_is_directory=True)

    uninstall(scope="project", project_dir=tmp_path, platform="codex")

    assert not sibling.exists()
    assert (external / "keep.md").read_text(encoding="utf-8") == "keep nested\n"


@pytest.mark.integration
def test_uninstall_codex_removes_managed_project_guidance_only(
    tmp_path: Path,
) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        bootstrap_project_agents_md,
    )

    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Team rules\n\nKeep this.\n", encoding="utf-8")
    bootstrap_project_agents_md(tmp_path)
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="codex",
    )

    uninstall(scope="project", project_dir=tmp_path, platform="codex")

    assert agents_md.exists()
    text = agents_md.read_text(encoding="utf-8")
    assert "# Team rules" in text
    assert "Keep this." in text
    assert AGENTS_BEGIN_MARKER not in text


@pytest.mark.integration
def test_uninstall_codex_reports_malformed_override_and_cleans_standard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        AGENTS_END_MARKER,
        bootstrap_project_agents_md,
    )

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="codex",
    )
    standard = bootstrap_project_agents_md(tmp_path)
    override = tmp_path / "AGENTS.override.md"
    malformed = f"{AGENTS_END_MARKER}\nKeep me.\n{AGENTS_BEGIN_MARKER}\n"
    override.write_text(malformed, encoding="utf-8")

    uninstall(scope="project", project_dir=tmp_path, platform="codex")

    assert not standard.exists()
    assert override.read_text(encoding="utf-8") == malformed
    err = capsys.readouterr().err
    assert str(override) in err
    assert "end marker before" in err


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
    # Personas: three role classes (dev + architect + three critics)
    personas = {p.stem for p in (skill_dir / "agents").glob("*.md")}
    assert personas == {
        "architect",
        "dev",
        "critic-database",
        "critic-security",
        "critic-product",
    }


@pytest.mark.integration
def test_install_copies_tokens_command(tmp_path: Path) -> None:
    """The bundled /tokens slash command lands in <scope>/.claude/commands/."""
    from dummyindex.installer import COMMANDS_REL

    install(scope="project", project_dir=tmp_path)
    command = tmp_path / COMMANDS_REL / "tokens.md"
    assert command.exists()
    assert "dummyindex usage" in command.read_text(encoding="utf-8")


@pytest.mark.integration
def test_install_and_uninstall_skip_symlinked_commands_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from dummyindex.installer import COMMANDS_REL

    external = tmp_path / "external-commands"
    external.mkdir()
    external_token = external / "tokens.md"
    external_token.write_text("external command\n", encoding="utf-8")
    commands_dir = tmp_path / COMMANDS_REL
    commands_dir.parent.mkdir(parents=True)
    commands_dir.symlink_to(external, target_is_directory=True)

    install(scope="project", project_dir=tmp_path, skill_only=True)
    assert "refusing to write through directory symlink" in capsys.readouterr().err

    uninstall(scope="project", project_dir=tmp_path)

    assert commands_dir.is_symlink()
    assert external_token.read_text(encoding="utf-8") == "external command\n"


@pytest.mark.integration
def test_install_replaces_command_file_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    from dummyindex.installer import COMMANDS_REL

    commands_dir = tmp_path / COMMANDS_REL
    commands_dir.mkdir(parents=True)
    external = tmp_path / "external-token.md"
    external.write_text("external command\n", encoding="utf-8")
    command = commands_dir / "tokens.md"
    command.symlink_to(external)

    install(scope="project", project_dir=tmp_path, skill_only=True)

    assert not command.is_symlink()
    assert "dummyindex usage" in command.read_text(encoding="utf-8")
    assert external.read_text(encoding="utf-8") == "external command\n"


@pytest.mark.integration
def test_uninstall_removes_tokens_command(tmp_path: Path) -> None:
    from dummyindex.installer import COMMANDS_REL
    from dummyindex.installer import uninstall as uninstall_fn

    install(scope="project", project_dir=tmp_path)
    command = tmp_path / COMMANDS_REL / "tokens.md"
    assert command.exists()  # precondition
    uninstall_fn(scope="project", project_dir=tmp_path)
    assert not command.exists()


@pytest.mark.integration
def test_install_upgrade_purges_stale_companion_markdowns(tmp_path: Path) -> None:
    """A v0.13.x -> v0.14 upgrade must leave exactly the current source set.

    The retired persona/stage files must NOT linger beside the new pipeline
    docs, or the orchestrator sees contradictory personas.
    """
    install(scope="project", project_dir=tmp_path)
    skill_dir = (tmp_path / SKILL_REL).parent
    # Simulate leftovers from a prior version's install.
    stale = {
        skill_dir / "agents" / "chairman.md",
        skill_dir / "agents" / "senior-developer.md",
        skill_dir / "council" / "20-stage1-perspectives.md",
        skill_dir / "council" / "40-stage3-synthesis.md",
    }
    for f in stale:
        f.write_text("# stale from a prior version\n", encoding="utf-8")

    # Re-install (the upgrade path).
    install(scope="project", project_dir=tmp_path)

    for f in stale:
        assert not f.exists(), f"stale file survived upgrade: {f}"
    personas = {p.stem for p in (skill_dir / "agents").glob("*.md")}
    assert "chairman" not in personas and "senior-developer" not in personas
    assert personas == {
        "architect",
        "dev",
        "critic-database",
        "critic-security",
        "critic-product",
    }


@pytest.mark.integration
def test_uninstall_removes_companion_markdowns(tmp_path: Path) -> None:
    install(scope="project", project_dir=tmp_path)
    skill_dir = (tmp_path / SKILL_REL).parent
    assert (skill_dir / "agents").is_dir()  # precondition

    from dummyindex.installer import uninstall as uninstall_fn

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
def test_parse_accepts_platform_flag() -> None:
    assert parse_install_args(["--platform", "claude"]) == (
        "user",
        None,
        False,
        False,
        False,
        False,
        "claude",
    )
    assert parse_install_args(["--platform=claude"]) == (
        "user",
        None,
        False,
        False,
        False,
        False,
        "claude",
    )
    assert parse_install_args(["--platform=codex"])[-1] == "codex"
    assert parse_install_args(["--platform", "both"])[-1] == "both"


@pytest.mark.unit
def test_parse_rejects_unknown_platform(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_install_args(["--platform", "cursor"])
    assert exc.value.code == 2
    assert "claude|codex|both" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--scope"], "--scope requires"),
        (["--dir"], "--dir requires"),
        (["--scope", "workspace"], "--scope must be"),
    ],
)
def test_parse_install_rejects_missing_values_and_unknown_scope(
    args: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_install_args(args)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--scope", "--platform=codex"], "--scope requires"),
        (["--dir", "--platform=codex"], "--dir requires"),
        (["--platform", "--skill-only"], "--platform requires"),
    ],
)
def test_parse_install_does_not_consume_an_option_as_a_missing_value(
    args: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_install_args(args)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.unit
def test_parse_rejects_unknown_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_install_args(["--definitely-not-a-flag"])
    assert exc.value.code == 2
    assert "unknown install argument" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_parse_install_help_prints_usage_and_exits_zero(
    flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Probing `install --help` must print usage and exit 0 — NOT run a full
    install (the 'probing the command IS running it' trap)."""
    with pytest.raises(SystemExit) as exc:
        parse_install_args([flag])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "install" in out.lower()
    assert "--skill-only" in out
    assert "--no-default-plugins   skip all default Claude plugins for this run" in out
    assert "--no-superpowers       compatibility alias for --no-default-plugins" in out


@pytest.mark.unit
def test_parse_uninstall_accepts_only_uninstall_options(tmp_path: Path) -> None:
    assert parse_uninstall_args([]) == ("user", None, "claude")
    assert parse_uninstall_args(
        ["--scope=project", f"--dir={tmp_path}", "--platform=codex"]
    ) == ("project", tmp_path, "codex")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--scope", "--platform=codex"], "--scope requires"),
        (["--dir", "--platform=codex"], "--dir requires"),
        (["--platform", "--scope=project"], "--platform requires"),
    ],
)
def test_parse_uninstall_does_not_consume_an_option_as_a_missing_value(
    args: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_uninstall_args(args)

    assert exc.value.code == 2
    assert message in capsys.readouterr().err


@pytest.mark.integration
def test_top_level_uninstall_missing_dir_value_does_not_remove_default_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dummyindex import __main__

    fake_home = tmp_path / "home"
    skill_path = fake_home / SKILL_REL
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("keep me\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(
        __main__.sys,
        "argv",
        ["dummyindex", "uninstall", "--dir", "--platform=codex"],
    )

    with pytest.raises(SystemExit) as exc:
        __main__.main()

    assert exc.value.code == 2
    assert skill_path.read_text(encoding="utf-8") == "keep me\n"


@pytest.mark.unit
@pytest.mark.parametrize(
    "install_only_flag",
    [
        "--skill-only",
        "--defaults",
        "--no-onboarding",
        "--no-default-plugins",
        "--no-superpowers",
    ],
)
def test_parse_uninstall_rejects_install_only_flags(
    install_only_flag: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_uninstall_args([install_only_flag])
    assert exc.value.code == 2
    assert "unknown uninstall argument" in capsys.readouterr().err


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_parse_uninstall_help_is_uninstall_specific(
    flag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_uninstall_args([flag])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage: dummyindex uninstall" in out
    assert "--skill-only" not in out


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


@pytest.mark.integration
def test_install_codex_user_scope_registers_global_agents_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(clean_cwd)

    install(scope="user", skill_only=True, platform="codex")

    assert (fake_home / CODEX_SKILL_REL).exists()
    global_agents = fake_home / ".codex" / "AGENTS.md"
    assert global_agents.exists()
    text = global_agents.read_text(encoding="utf-8")
    assert "$dummyindex" in text
    assert ".agents/skills/dummyindex" in text
    assert not (fake_home / ".claude").exists()


@pytest.mark.integration
def test_install_codex_user_scope_honors_codex_home_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    codex_home = tmp_path / "codex-config"
    codex_home.mkdir()
    override = codex_home / "AGENTS.override.md"
    override.write_text("# Global override\n", encoding="utf-8")
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(clean_cwd)

    install(scope="user", skill_only=True, platform="codex")

    assert (fake_home / CODEX_SKILL_REL).exists()
    assert "$dummyindex" in override.read_text(encoding="utf-8")
    assert not (codex_home / "AGENTS.md").exists()
    assert not (fake_home / ".codex").exists()


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
    `.context/`, writes CLAUDE.md, and installs the managed hooks."""
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
    # Auto-init installed the managed Claude hooks.
    assert not (repo / ".git" / "hooks" / "post-commit").exists()
    settings = repo / ".claude" / "settings.json"
    assert settings.exists()
    settings_text = settings.read_text(encoding="utf-8")
    assert "DUMMYINDEX_AUTO_REFRESH" in settings_text
    assert "SessionStart" in settings_text
    assert "PostToolUse" not in settings_text

    out = capsys.readouterr().out
    assert ".context/" in out
    assert "hooks" in out


@pytest.mark.integration
def test_install_codex_auto_init_writes_agents_without_claude_integrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, platform="codex")

    assert (repo / CODEX_SKILL_REL).exists()
    assert (repo / ".context" / "INDEX.md").exists()
    agents_md = repo / "AGENTS.md"
    assert agents_md.exists()
    text = agents_md.read_text(encoding="utf-8")
    assert "$dummyindex-plan" in text
    assert ".context/HOW_TO_USE.md" in text
    assert text.count(ALWAYS_ON_OUTPUT_POLICY) == 1
    assert not (repo / ".claude").exists()


@pytest.mark.integration
def test_uninstall_codex_user_scope_cleans_global_and_owned_auto_init_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    codex_home = tmp_path / "codex-config"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(repo)

    install(scope="user", platform="codex")

    global_agents = codex_home / "AGENTS.md"
    project_agents = repo / "AGENTS.md"
    assert global_agents.exists()
    assert project_agents.exists()

    uninstall(scope="user", platform="codex")

    assert not (fake_home / CODEX_SKILL_REL).exists()
    assert not global_agents.exists()
    assert not project_agents.exists()


@pytest.mark.integration
def test_uninstall_codex_user_scope_keeps_guidance_for_project_scope_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dummyindex.context.output.agents_md import (
        AGENTS_BEGIN_MARKER,
        bootstrap_project_agents_md,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    codex_home = tmp_path / "codex-config"
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(repo)

    install(
        scope="project",
        project_dir=repo,
        skill_only=True,
        platform="codex",
    )
    project_agents = bootstrap_project_agents_md(repo)
    install(scope="user", skill_only=True, platform="codex")

    uninstall(scope="user", platform="codex")

    assert (repo / CODEX_SKILL_REL).exists()
    assert project_agents.exists()
    assert AGENTS_BEGIN_MARKER in project_agents.read_text(encoding="utf-8")
    assert not (fake_home / CODEX_SKILL_REL).exists()
    assert not (codex_home / "AGENTS.md").exists()


@pytest.mark.integration
def test_install_codex_defaults_use_current_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, platform="codex", defaults=True)

    payload = json.loads(
        (repo / ".context" / "config.json").read_text(encoding="utf-8")
    )
    assert payload["model"] == "current"
    assert payload["auto_refresh_hook"] is False
    assert payload["wired"] == []
    assert payload["default_plugins_enabled"] is None


@pytest.mark.integration
def test_install_both_defaults_use_portable_model_and_claude_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, platform="both", defaults=True)

    payload = json.loads(
        (repo / ".context" / "config.json").read_text(encoding="utf-8")
    )
    assert payload["model"] == "current"
    assert payload["auto_refresh_hook"] is True
    assert [entry["target"] for entry in payload["wired"]] == list(_DEFAULT_TARGETS)
    assert payload["default_plugins_enabled"] is True


@pytest.mark.unit
def test_default_config_import_oserror_is_not_masked_by_configerror_nameerror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An early lazy-import failure must reach the best-effort handler.

    ``ConfigError`` used to be imported inside the guarded block. If an
    earlier import raised, evaluating ``except (OSError, ConfigError)`` raised
    a second ``NameError`` and hid the actionable failure.
    """
    import builtins

    from dummyindex.installer.install import _write_default_config

    real_import = builtins.__import__

    def fail_config_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dummyindex.context.domains.config":
            raise OSError("simulated config import failure")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_config_import)

    _write_default_config(tmp_path)

    assert "skipped (simulated config import failure)" in capsys.readouterr().err


@pytest.mark.integration
def test_install_auto_init_runs_for_submodule_git_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A submodule's `.git` is a *file* pointing at the superproject's module
    dir, not a directory. Auto-init must still fire (was the real-world bug:
    `install` printed "skipped project init" for a valid submodule)."""
    superproject = tmp_path / "super"
    module_dir = superproject / ".git" / "modules" / "backend"
    module_dir.mkdir(parents=True)
    submodule = superproject / "backend"
    submodule.mkdir()
    # Submodule pointer file (32-byte-ish), relative to the submodule dir.
    (submodule / ".git").write_text(
        "gitdir: ../.git/modules/backend\n", encoding="utf-8"
    )
    (submodule / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n",
        encoding="utf-8",
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=submodule)

    assert (submodule / SKILL_REL).exists()
    # Auto-init recognised the submodule as a repo and built .context/.
    assert (submodule / ".context").is_dir()
    assert (submodule / ".context" / "INDEX.md").exists()
    out = capsys.readouterr().out
    assert "skipped project init" not in out


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
    assert "no git repo at" in out


@pytest.mark.integration
def test_install_defaults_writes_config_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`install --defaults` on a git repo writes .context/config.json defaults."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, defaults=True)

    config_path = repo / ".context" / "config.json"
    assert config_path.exists()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["scope"] == "repo"
    assert payload["mode"] == "standard"
    assert payload["model"] == "sonnet-4.6"
    assert payload["auto_refresh_hook"] is True
    assert payload["external_docs"] == []
    assert "config.json" in capsys.readouterr().out


@pytest.mark.integration
def test_install_without_defaults_skips_config_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auto-init alone (no --defaults) must NOT write config.json — onboarding owns it."""
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)

    assert (repo / ".context").is_dir()
    assert not (repo / ".context" / "config.json").exists()


@pytest.mark.integration
def test_install_defaults_never_clobbers_existing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second `install --defaults` (or one over a hand-written config) must
    leave the existing config.json byte-for-byte unchanged and say so."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # First install writes the defaults.
    install(scope="project", project_dir=repo, defaults=True)
    config_path = repo / ".context" / "config.json"
    assert config_path.exists()

    # Hand-edit the config so we can prove it survives a re-run untouched.
    hand_written = config_path.read_text(encoding="utf-8").replace(
        '"sonnet-4.6"', '"opus-4.8"'
    )
    config_path.write_text(hand_written, encoding="utf-8")
    capsys.readouterr()  # drain output from the first install

    # Second install with --defaults must NOT overwrite it.
    install(scope="project", project_dir=repo, defaults=True)

    assert config_path.read_text(encoding="utf-8") == hand_written
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["model"] == "opus-4.8"  # the hand-written value, not the default
    assert "kept existing" in capsys.readouterr().out


@pytest.mark.integration
def test_install_no_onboarding_also_writes_config_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--no-onboarding` is load-bearing: it means "non-interactive, use
    defaults" just like `--defaults`, so it writes .context/config.json too."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, no_onboarding=True)

    config_path = repo / ".context" / "config.json"
    assert config_path.exists()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["model"] == "sonnet-4.6"
    assert "config.json" in capsys.readouterr().out


@pytest.mark.integration
def test_install_migrates_stale_config_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A plain re-install (the `/dummyindex-update` path — no flags) migrates a
    stale on-disk config.json (pre-v2 schema + legacy `opus-4.7` value) to the
    current schema/value in place, preserving every user choice."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    # Build the index once, then plant a config last written before the v2
    # schema bump and the opus rename.
    install(scope="project", project_dir=repo, defaults=True)
    config_path = repo / ".context" / "config.json"
    legacy = {
        "schema_version": 1,
        "scope": "repo",
        "scope_path": None,
        "mode": "deep",
        "model": "opus-4.7",
        "auto_refresh_hook": True,
        "external_docs": [],
        "reconcile_exclude": ["*.png"],
        "wire_superpowers": True,
    }
    config_path.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
    capsys.readouterr()  # drain first-install output

    # Plain re-install — exactly what `/dummyindex-update` runs.
    install(scope="project", project_dir=repo)

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == CONFIG_SCHEMA_VERSION  # schema migrated
    assert payload["model"] == "opus-4.8"  # legacy value migrated
    assert payload["mode"] == "deep"  # choice preserved
    assert payload["reconcile_exclude"] == ["*.png"]  # choice preserved
    assert [entry["target"] for entry in payload["wired"]] == list(_DEFAULT_TARGETS)
    assert payload["default_plugins_enabled"] is True
    assert "config.json" in capsys.readouterr().out  # migration reported


@pytest.mark.integration
def test_install_folds_equipped_plugin_into_wired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain re-install (the `/dummyindex-update` path) folds an equip-installed
    plugin recorded in equipment.json into config.wired, so a v1→v2 migration
    never silently drops it from the declared-intent ledger."""
    import json

    from dummyindex.context.domains.equip.enums import (
        EquipmentKind,
        EquipmentSource,
    )
    from dummyindex.context.domains.equip.lifecycle.manifest import write_manifest
    from dummyindex.context.domains.equip.models import (
        EquipmentItem,
        EquipmentManifest,
    )

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, defaults=True)
    context_dir = repo / ".context"

    # A repo equipped (under an older CLI) with an extra plugin recorded in
    # equipment.json + a stale v1 config that knows nothing about it.
    write_manifest(
        context_dir,
        EquipmentManifest(
            schema_version=4,
            items=(
                EquipmentItem(
                    kind=EquipmentKind.PLUGIN,
                    name="impeccable@impeccable",
                    path=".claude/settings.json",
                    source=EquipmentSource.MARKETPLACE,
                    version="1.0.0",
                ),
            ),
        ),
    )
    config_path = context_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "repo",
                "scope_path": None,
                "mode": "standard",
                "model": "sonnet-4.6",
                "auto_refresh_hook": True,
                "external_docs": [],
                "wire_superpowers": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Plain re-install — exactly what `/dummyindex-update` runs.
    install(scope="project", project_dir=repo)

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    targets = [e["target"] for e in payload["wired"]]
    assert "impeccable@impeccable" in targets  # equipped plugin survived the update
    assert "superpowers@claude-plugins-official" in targets  # default preserved


@pytest.mark.integration
def test_install_copies_memory_skill(tmp_path: Path) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True)
    skill = tmp_path / ".claude" / "skills" / "dummyindex-remember" / "SKILL.md"
    assert skill.exists()
    assert "name: dummyindex-remember" in skill.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.parametrize(
    "skill_label",
    [
        "dummyindex-plan",
        "dummyindex-equip",
        "dummyindex-build",
        "dummyindex-audit",
        "dummyindex-gc",
        "dummyindex-update",
    ],
)
def test_install_copies_sibling_skills(tmp_path: Path, skill_label: str) -> None:
    """Each sibling skill lands in its own top-level dir as a `/`-command."""
    install(scope="project", project_dir=tmp_path, skill_only=True)
    skill = tmp_path / ".claude" / "skills" / skill_label / "SKILL.md"
    assert skill.exists(), f"missing sibling skill {skill_label}"
    body = skill.read_text(encoding="utf-8")
    assert f"name: {skill_label}" in body
    # The __VERSION__ placeholder must be substituted with the package version.
    assert "__VERSION__" not in body


@pytest.mark.integration
def test_install_ships_no_template_files(tmp_path: Path) -> None:
    """*.tmpl render templates are package data, resolved package-relative by
    equip's renderer — installing them into repos ships inert files that
    mislead agents and pollute reconcile/lint surfaces. Skip them; genuinely
    consumed companions (audit's persona agents/) still ship."""
    install(scope="project", project_dir=tmp_path, skill_only=True)
    skills_root = tmp_path / ".claude" / "skills"
    assert not list(skills_root.rglob("*.tmpl"))
    # equip's templates/ dir must not be created at all (it holds only .tmpl).
    assert not (skills_root / "dummyindex-equip" / "templates").exists()
    # audit's agents/ companion is read from the installed skill dir — ships.
    assert list((skills_root / "dummyindex-audit" / "agents").glob("*.md"))


@pytest.mark.integration
def test_install_purges_stale_template_files(tmp_path: Path) -> None:
    """Upgrade heal: installs <= 0.25.0 shipped equip's *.md.tmpl twins; the
    next install must remove them (and the then-empty templates/ dir)."""
    stale_dir = tmp_path / ".claude" / "skills" / "dummyindex-equip" / "templates"
    stale_dir.mkdir(parents=True)
    (stale_dir / "implementer-agent.md.tmpl").write_text("stale\n", encoding="utf-8")

    install(scope="project", project_dir=tmp_path, skill_only=True)

    assert not list((tmp_path / ".claude" / "skills").rglob("*.tmpl"))
    assert not stale_dir.exists()


@pytest.mark.integration
def test_install_update_skill_stamps_version(tmp_path: Path) -> None:
    """/dummyindex-update's banner carries the concrete installed version."""
    from dummyindex.installer.common import PACKAGE_VERSION

    install(scope="project", project_dir=tmp_path, skill_only=True)
    skill = tmp_path / ".claude" / "skills" / "dummyindex-update" / "SKILL.md"
    assert f"Installed from dummyindex `{PACKAGE_VERSION}`" in skill.read_text(
        encoding="utf-8"
    )


@pytest.mark.integration
def test_uninstall_removes_update_skill(tmp_path: Path) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True)
    sib = tmp_path / ".claude" / "skills" / "dummyindex-update"
    assert sib.is_dir()  # precondition
    uninstall(scope="project", project_dir=tmp_path)
    assert not sib.exists()


# ----- C1/C6 P0: install must not destroy a curated index -------------------


def _curate_index(repo: Path) -> str:
    """Rename the first community feature to a named id (flips it INFERRED via
    the real council op). Returns the new id. Mirrors the curation a user does
    after the council runs."""
    import json

    from dummyindex.context.domains.features import rename_feature

    features_dir = repo / ".context" / "features"
    index = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    first_id = index["features"][0]["feature_id"]
    new_id = "auth-core"
    rename_feature(
        features_dir,
        from_id=first_id,
        to_id=new_id,
        new_name="Auth Core",
        new_summary="Curated by the council.",
    )
    return new_id


@pytest.mark.integration
def test_install_auto_init_preserves_enriched_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Re-running install on a curated repo must NOT re-cluster: feature ids
    unchanged, no community-* re-stubbing, hooks + CLAUDE.md intact."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)  # first build → deterministic index
    new_id = _curate_index(repo)

    features_dir = repo / ".context" / "features"
    index_before = (features_dir / "INDEX.json").read_text(encoding="utf-8")
    meta_before = json.loads(
        (repo / ".context" / "meta.json").read_text(encoding="utf-8")
    )
    capsys.readouterr()  # drain first-install output

    # Re-run install — the curated index must survive.
    install(scope="project", project_dir=repo)

    index_after = (features_dir / "INDEX.json").read_text(encoding="utf-8")
    meta_after = json.loads(
        (repo / ".context" / "meta.json").read_text(encoding="utf-8")
    )
    assert index_after == index_before, "INDEX.json was re-clustered"
    assert (features_dir / new_id).is_dir(), "curated feature dir orphaned"
    # created_at is the index ancestry — a non-destructive refresh must keep it.
    assert meta_after["created_at"] == meta_before["created_at"]
    # Hooks still installed; CLAUDE.md managed block intact.
    settings = (repo / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "DUMMYINDEX_AUTO_REFRESH" in settings
    assert (repo / ".claude" / "CLAUDE.md").exists()
    out = capsys.readouterr().out
    assert "curated index" in out.lower()


@pytest.mark.integration
def test_install_auto_init_advances_version_on_curated_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The non-destructive install path advances meta.dummyindex_version (so a
    healthy curated repo stops showing a stale stamp) without re-clustering."""
    import json

    from dummyindex.installer.common import PACKAGE_VERSION

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)
    _curate_index(repo)

    # Simulate an old stamp left by a prior CLI version.
    meta_path = repo / ".context" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["dummyindex_version"] = "0.15.0"
    meta_path.write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    install(scope="project", project_dir=repo)

    meta_after = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta_after["dummyindex_version"] == PACKAGE_VERSION


@pytest.mark.integration
def test_install_auto_init_full_builds_deterministic_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counter-test: a deterministic-only index (no curation) still full-builds
    on re-install — nothing enriched to preserve."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)
    meta_path = repo / ".context" / "meta.json"
    created_before = json.loads(meta_path.read_text(encoding="utf-8"))["created_at"]

    # No curation. Re-install full-builds → created_at is reset by new_meta.
    install(scope="project", project_dir=repo)
    created_after = json.loads(meta_path.read_text(encoding="utf-8"))["created_at"]
    # Deterministic path went through build_all (created_at re-stamped or equal);
    # the key assertion is that it did NOT take the preserved path, which we
    # prove by the absence of curated dirs — all features stay community-*.
    index = json.loads(
        (repo / ".context" / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    assert all(f["feature_id"].startswith("community-") for f in index["features"])
    assert isinstance(created_after, str) and isinstance(created_before, str)


# ----- reviewed default-plugin orchestration -------------------------------


def _plugin_settings(repo: Path) -> dict:
    settings = repo / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    return json.loads(settings.read_text(encoding="utf-8"))


def _enabled_plugins(repo: Path) -> dict:
    return _plugin_settings(repo).get("enabledPlugins", {})


def _plugin_install_targets(calls: list[tuple[str, ...]]) -> list[str]:
    return [argv[3] for argv in calls if argv[:3] == ("claude", "plugin", "install")]


@pytest.mark.integration
@pytest.mark.parametrize("platform", ["claude", "both"])
def test_install_declares_and_materializes_all_defaults_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    platform: str,
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    runner = _RecordingRunner(lambda: capsys.readouterr().out)
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    install(scope="project", project_dir=repo, platform=platform)

    settings = _plugin_settings(repo)
    assert settings["enabledPlugins"] == dict.fromkeys(_DEFAULT_TARGETS, True)
    marketplaces = settings["extraKnownMarketplaces"]
    for plugin in DEFAULT_PLUGINS:
        if plugin.repo is None:
            continue
        assert marketplaces[plugin.marketplace]["source"] == {
            "source": "github",
            "repo": plugin.repo,
            "ref": plugin.ref,
        }
        source = f"{plugin.repo}@{plugin.ref}"
        add_call = (
            "claude",
            "plugin",
            "marketplace",
            "add",
            source,
            "--scope",
            "project",
        )
        install_call = (
            "claude",
            "plugin",
            "install",
            plugin.target,
            "--scope",
            "project",
        )
        assert runner.calls.index(add_call) < runner.calls.index(install_call)

    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)
    before_runner = runner.output_before_first_call or ""
    expected_trust_disclosures = (
        "default plugin trust -> caveman@caveman from "
        "JuliusBrussee/caveman@0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0; "
        "reviewed surfaces: skills, commands, SessionStart Node command hook, "
        "UserPromptSubmit Node command hook; runs code: yes; opt out this run "
        "with --no-default-plugins",
        "default plugin trust -> i-have-adhd@i-have-adhd from "
        "ayghri/i-have-adhd@0241185d6c7f2d0763a988ce52eceb13ea9f5c1f; "
        "reviewed surfaces: skill; runs code: no; opt out this run with "
        "--no-default-plugins",
    )
    for disclosure in expected_trust_disclosures:
        assert disclosure in before_runner
    if platform == "both":
        assert (repo / "AGENTS.md").exists()


@pytest.mark.integration
def test_install_codex_only_then_both_transitions_defaults_same_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    install(
        scope="project",
        project_dir=repo,
        platform="codex",
        defaults=True,
    )

    assert runner.calls == []
    assert not (repo / ".claude").exists()
    codex_cfg = read_config(repo / ".context")
    assert codex_cfg is not None
    assert codex_cfg.default_plugins_enabled is None
    assert codex_cfg.wired == ()

    install(scope="project", project_dir=repo, platform="both")

    transitioned = read_config(repo / ".context")
    assert transitioned is not None
    assert transitioned.default_plugins_enabled is True
    assert tuple(entry.target for entry in transitioned.wired) == _DEFAULT_TARGETS
    assert _plugin_settings(repo)["enabledPlugins"] == dict.fromkeys(
        _DEFAULT_TARGETS, True
    )
    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)


@pytest.mark.integration
def test_install_backfills_opted_in_config_before_one_materialization_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    context_dir = repo / ".context"
    custom = WiredEntry(WiredKind.PLUGIN, "custom@team")
    write_config(
        context_dir,
        replace(
            default_config(),
            wired=(default_wired()[0], custom),
            default_plugins_enabled=True,
        ),
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(installer_module, "_install_project_hooks", lambda *_: None)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    install(scope="project", project_dir=repo)

    cfg = read_config(context_dir)
    assert cfg is not None
    assert tuple(entry.target for entry in cfg.wired) == (
        _DEFAULT_TARGETS[0],
        custom.target,
        *_DEFAULT_TARGETS[1:],
    )
    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)
    first_calls = tuple(runner.calls)
    first_bytes = (context_dir / "config.json").read_bytes()

    runner.calls.clear()
    install(scope="project", project_dir=repo)

    assert (context_dir / "config.json").read_bytes() == first_bytes
    assert tuple(entry.target for entry in read_config(context_dir).wired) == (
        _DEFAULT_TARGETS[0],
        custom.target,
        *_DEFAULT_TARGETS[1:],
    )
    assert runner.calls.count(("claude", "--version")) == 1
    assert _plugin_install_targets(runner.calls) == list(_DEFAULT_TARGETS)
    assert tuple(runner.calls) == first_calls


@pytest.mark.integration
@pytest.mark.parametrize(
    "opt_out_kw",
    [{"no_default_plugins": True}, {"no_superpowers": True}],
    ids=["canonical", "legacy"],
)
def test_install_one_run_opt_out_is_byte_exact_and_side_effect_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opt_out_kw: dict[str, bool],
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    context_dir = repo / ".context"
    custom = WiredEntry(WiredKind.PLUGIN, "custom@team")
    write_config(
        context_dir,
        replace(default_config(), wired=(default_wired()[0], custom)),
    )
    config_path = context_dir / "config.json"
    config_before = config_path.read_bytes()
    settings_path = repo / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"userSetting": true}\n', encoding="utf-8")
    settings_before = settings_path.read_bytes()
    monkeypatch.setattr(installer_module, "_install_project_hooks", lambda *_: None)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    install(scope="project", project_dir=repo, **opt_out_kw)

    assert config_path.read_bytes() == config_before
    assert settings_path.read_bytes() == settings_before
    assert runner.calls == []
    cfg = read_config(context_dir)
    assert cfg is not None
    assert tuple(entry.target for entry in cfg.wired) == (
        _DEFAULT_TARGETS[0],
        custom.target,
    )


@pytest.mark.integration
def test_install_malformed_config_warns_and_mutates_no_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    config_path = repo / ".context" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{malformed\n", encoding="utf-8")
    config_before = config_path.read_bytes()
    monkeypatch.setattr(installer_module, "_install_project_hooks", lambda *_: None)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    install(scope="project", project_dir=repo)

    assert config_path.read_bytes() == config_before
    assert not (repo / ".claude" / "settings.json").exists()
    assert runner.calls == []
    assert "skipped defaults" in capsys.readouterr().err


@pytest.mark.integration
def test_install_explicit_default_opt_out_remains_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    context_dir = repo / ".context"
    write_config(
        context_dir,
        replace(default_config(), default_plugins_enabled=False),
    )
    config_path = context_dir / "config.json"
    before = config_path.read_bytes()
    monkeypatch.setattr(installer_module, "_install_project_hooks", lambda *_: None)
    runner = _RecordingRunner()
    monkeypatch.setattr(default_plugins_module, "default_runner", runner)
    monkeypatch.delenv(SKIP_INSTALL_ENV)

    install(scope="project", project_dir=repo)

    cfg = read_config(context_dir)
    assert cfg is not None and cfg.default_plugins_enabled is False
    assert config_path.read_bytes() == before
    assert not (repo / ".claude" / "settings.json").exists()
    assert runner.calls == []


# ----- user-scope skill registration: sentinel probe (plan task 11) ---------
# The idempotency probe (install.py:176) must key off the `_SKILL_REGISTRATION`
# SENTINEL substring ("**dummyindex** ("), NOT the bare word "dummyindex". A
# pre-existing ~/.claude/CLAUDE.md may *mention* dummyindex in user prose
# without ever carrying our managed registration block — that file must still
# get the block appended. The unique opening of the registration bullet is the
# sentinel substring asserted below.

# The stable, unique opening of the `_SKILL_REGISTRATION` bullet — the exact
# substring install.py probes for. Asserting on this (not the bare word)
# pins the fix.
_SENTINEL = "**dummyindex** ("


def _user_scope_clean_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME at a fresh tmp home and chdir into a clean non-git dir so the
    user-scope `install()` registers in ~/.claude/CLAUDE.md without firing
    auto-init on the test runner's cwd. Returns the fake HOME path."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    clean_cwd = tmp_path / "cwd"
    clean_cwd.mkdir()
    monkeypatch.chdir(clean_cwd)
    return fake_home


@pytest.mark.integration
def test_install_user_scope_appends_block_when_bare_word_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ~/.claude/CLAUDE.md that names "dummyindex" in prose but carries no
    `_SKILL_REGISTRATION` sentinel must get the registration block appended —
    the bare word must NOT be mistaken for the sentinel (install.py:176)."""
    fake_home = _user_scope_clean_cwd(tmp_path, monkeypatch)
    claude_md = fake_home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    # User prose mentions dummyindex, but the sentinel is absent.
    seeded = "# My notes\nI use dummyindex sometimes for indexing.\n"
    claude_md.write_text(seeded, encoding="utf-8")
    assert _SENTINEL not in claude_md.read_text(encoding="utf-8")  # precondition

    install(scope="user")

    content = claude_md.read_text(encoding="utf-8")
    # The block was appended (sentinel now present)...
    assert _SENTINEL in content
    # ...and the user's original prose is preserved above it.
    assert "I use dummyindex sometimes for indexing." in content


@pytest.mark.integration
def test_install_user_scope_skips_when_sentinel_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the sentinel is already present, install makes no change and does
    not duplicate the registration block (sentinel appears exactly once)."""
    from dummyindex.installer.common import _SKILL_REGISTRATION

    fake_home = _user_scope_clean_cwd(tmp_path, monkeypatch)
    claude_md = fake_home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    seeded = "# My notes\n" + _SKILL_REGISTRATION
    claude_md.write_text(seeded, encoding="utf-8")
    assert seeded.count(_SENTINEL) == 1  # precondition

    install(scope="user")

    content = claude_md.read_text(encoding="utf-8")
    # No duplicate block — sentinel still appears exactly once...
    assert content.count(_SENTINEL) == 1
    # ...and the file is unchanged (no re-append).
    assert content == seeded


@pytest.mark.integration
def test_install_user_scope_idempotent_on_bare_word_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running install twice on a bare-word file appends the block exactly once:
    the first run appends it, the second sees the sentinel and skips."""
    fake_home = _user_scope_clean_cwd(tmp_path, monkeypatch)
    claude_md = fake_home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text(
        "# My notes\nNotes that mention dummyindex.\n", encoding="utf-8"
    )

    install(scope="user")
    after_first = claude_md.read_text(encoding="utf-8")
    assert after_first.count(_SENTINEL) == 1

    install(scope="user")
    after_second = claude_md.read_text(encoding="utf-8")
    # Second run must NOT re-append — sentinel still exactly once...
    assert after_second.count(_SENTINEL) == 1
    # ...and the file is byte-identical to after the first run.
    assert after_second == after_first


@pytest.mark.integration
def test_install_skill_entry_reported_needs_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A ``kind: skill`` wired entry is reported needs-user, never auto-wired.

    The reconcile path classifies a skill entry into ``needs_user`` and the init
    summary surfaces a ``needs you:`` line on stderr — reported, never prompted.
    """
    from dataclasses import replace

    from dummyindex.context.default_plugins import WiredEntry, WiredKind
    from dummyindex.context.domains.config import default_config, write_config

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    ctx = repo / ".context"
    ctx.mkdir(parents=True)
    skill = WiredEntry(kind=WiredKind.SKILL, target="some-skill", version=None)
    write_config(ctx, replace(default_config(), wired=(skill,)))
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)

    captured = capsys.readouterr()
    assert "needs you: some-skill" in captured.err
    # The skill is never wired into settings.json.
    assert "some-skill" not in _enabled_plugins(repo)


# ----- equip-generated tools are refreshed on (re)install --------------------


@pytest.mark.unit
def test_refresh_equipment_step_noop_when_not_equipped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An indexed-but-unequipped repo (no equipment.json) is a silent no-op.

    The generated-tool refresh must not even attempt `equip refresh` when there is
    no manifest — no output, no error, and the underlying refresh is never called.
    """
    from dummyindex.installer.install import _refresh_equipment_step

    (tmp_path / ".context").mkdir()  # indexed, but `equip apply` never ran

    def _must_not_run(*_a: object, **_k: object) -> None:
        raise AssertionError("refresh must not run on an unequipped repo")

    monkeypatch.setattr("dummyindex.context.domains.equip.refresh", _must_not_run)
    _refresh_equipment_step(tmp_path)
    assert "equipment" not in capsys.readouterr().out


@pytest.mark.unit
def test_refresh_equipment_step_refreshes_when_equipped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An equipped repo triggers `equip refresh` against the just-installed templates.

    Proves the install-time wiring: with `equipment.json` present, the step builds
    fresh renders and calls the hash-baselined `refresh`, reporting what re-rendered.
    """
    from dummyindex.context.domains.equip import RefreshReport
    from dummyindex.installer.install import _refresh_equipment_step

    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    (context_dir / "equipment.json").write_text(
        '{"schema_version": 4, "items": []}', encoding="utf-8"
    )

    calls: list[Path] = []

    def _fake_refresh(
        root: Path, *, fresh_renders: object, dry_run: bool
    ) -> RefreshReport:
        calls.append(root)
        assert dry_run is False  # a real (non-dry) refresh
        return RefreshReport(refreshed=("python-implementer",))

    monkeypatch.setattr(
        "dummyindex.cli.equip.common.fresh_renders", lambda root, ctx: {}
    )
    monkeypatch.setattr("dummyindex.context.domains.equip.refresh", _fake_refresh)

    _refresh_equipment_step(tmp_path)

    assert calls == [tmp_path]
    out = capsys.readouterr().out
    assert "equipment" in out and "refreshed 1" in out
