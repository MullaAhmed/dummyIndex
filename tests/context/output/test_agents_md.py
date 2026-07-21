"""Codex ``AGENTS.md`` managed-block behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dummyindex.codex_guidance as codex_guidance
from dummyindex.context.output.agents_md import (
    AGENTS_BEGIN_MARKER,
    AGENTS_END_MARKER,
    PROJECT_OWNER_EXPLICIT,
    PROJECT_OWNER_USER_AUTO_INIT,
    bootstrap_global_agents_md,
    bootstrap_project_agents_md,
    remove_global_agents_md,
    remove_project_agents_md,
)


@pytest.fixture(autouse=True)
def codex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    configured = tmp_path / ".test-codex-home"
    configured.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(configured))
    return configured


def _write_fallback_config(codex_home: Path, names: list[str]) -> None:
    (codex_home / "config.toml").write_text(
        "project_doc_fallback_filenames = " + json.dumps(names) + "\n",
        encoding="utf-8",
    )


def _trust_project(codex_home: Path, project_root: Path) -> None:
    config = codex_home / "config.toml"
    existing = config.read_text(encoding="utf-8") if config.exists() else ""
    config.write_text(
        existing
        + f"\n[projects.{json.dumps(str(project_root.resolve()))}]\n"
        + 'trust_level = "trusted"\n',
        encoding="utf-8",
    )


def _use_system_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
) -> Path:
    path = tmp_path / "system-codex" / "config.toml"
    path.parent.mkdir()
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(codex_guidance, "_system_config_path", lambda: path)
    return path


@pytest.mark.unit
def test_project_agents_md_preserves_user_content_and_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# Team rules\n\nKeep this.\n", encoding="utf-8")

    first = bootstrap_project_agents_md(tmp_path).read_text(encoding="utf-8")
    second = bootstrap_project_agents_md(tmp_path).read_text(encoding="utf-8")

    assert first == second
    assert first.startswith(AGENTS_BEGIN_MARKER)
    assert first.endswith("# Team rules\n\nKeep this.\n")
    assert first.count("dummyindex:begin") == 1
    assert "$dummyindex-build" in first
    assert "Codex `/status`" in first


@pytest.mark.unit
@pytest.mark.parametrize("prefix", [b"", b"\xef\xbb\xbf"])
def test_project_guidance_round_trip_preserves_bom_and_crlf_user_bytes(
    tmp_path: Path,
    prefix: bytes,
) -> None:
    path = tmp_path / "AGENTS.md"
    original = prefix + b"# Team rules\r\n\r\nKeep this.\r\n"
    path.write_bytes(original)

    bootstrap_project_agents_md(tmp_path)
    installed = path.read_bytes()
    assert installed.startswith(prefix + AGENTS_BEGIN_MARKER.encode("utf-8"))

    result = remove_project_agents_md(tmp_path)
    assert result.removed == (path,)
    assert path.read_bytes() == original


@pytest.mark.unit
def test_global_agents_md_uses_default_codex_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    path = bootstrap_global_agents_md(tmp_path)

    assert path == tmp_path / ".codex" / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    assert ".agents/skills/dummyindex" in text
    assert "`/usage`" in text


@pytest.mark.unit
def test_project_agents_md_prefers_existing_override(tmp_path: Path) -> None:
    standard = tmp_path / "AGENTS.md"
    override = tmp_path / "AGENTS.override.md"
    standard.write_text("# Standard rules\n", encoding="utf-8")
    override.write_text("# Active override\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == override
    assert AGENTS_BEGIN_MARKER in override.read_text(encoding="utf-8")
    assert standard.read_text(encoding="utf-8") == "# Standard rules\n"


@pytest.mark.unit
def test_project_agents_md_uses_existing_empty_override_before_standard(
    tmp_path: Path,
) -> None:
    standard = tmp_path / "AGENTS.md"
    override = tmp_path / "AGENTS.override.md"
    standard.write_text("# Active standard rules\n", encoding="utf-8")
    override.write_text(" \n\t\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == override
    assert AGENTS_BEGIN_MARKER in override.read_text(encoding="utf-8")
    assert standard.read_text(encoding="utf-8") == "# Active standard rules\n"


@pytest.mark.unit
def test_project_agents_md_uses_existing_empty_override_when_standard_missing(
    tmp_path: Path,
) -> None:
    override = tmp_path / "AGENTS.override.md"
    override.write_text("\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == override
    assert AGENTS_BEGIN_MARKER in override.read_text(encoding="utf-8")
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_project_agents_md_uses_first_existing_configured_fallback(
    tmp_path: Path, codex_home: Path
) -> None:
    _write_fallback_config(
        codex_home,
        ["EMPTY_GUIDE.md", "TEAM_GUIDE.md", "SECOND_GUIDE.md"],
    )
    empty = tmp_path / "EMPTY_GUIDE.md"
    active = tmp_path / "TEAM_GUIDE.md"
    second = tmp_path / "SECOND_GUIDE.md"
    empty.write_text(" \n", encoding="utf-8")
    active.write_text("# Team guide\n", encoding="utf-8")
    second.write_text("# Second guide\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == empty
    assert AGENTS_BEGIN_MARKER in empty.read_text(encoding="utf-8")
    assert active.read_text(encoding="utf-8") == "# Team guide\n"
    assert second.read_text(encoding="utf-8") == "# Second guide\n"
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_project_agents_md_uses_safe_nested_configured_fallback(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    _write_fallback_config(codex_home, ["docs/TEAM_GUIDE.md"])
    nested = tmp_path / "docs" / "TEAM_GUIDE.md"
    nested.parent.mkdir()
    nested.write_text("# Nested team guide\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == nested
    assert AGENTS_BEGIN_MARKER in nested.read_text(encoding="utf-8")
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_nested_fallback_refuses_out_of_scope_parent_symlink(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "TEAM_GUIDE.md"
    target.write_text("# Outside guide\n", encoding="utf-8")
    (project / "docs").symlink_to(outside, target_is_directory=True)
    _write_fallback_config(codex_home, ["docs/TEAM_GUIDE.md"])

    with pytest.raises(ValueError, match="out-of-scope"):
        bootstrap_project_agents_md(project)

    assert target.read_text(encoding="utf-8") == "# Outside guide\n"


@pytest.mark.unit
def test_trusted_project_config_fallback_overrides_user_config(
    tmp_path: Path, codex_home: Path
) -> None:
    _write_fallback_config(codex_home, ["USER_GUIDE.md"])
    project_config = tmp_path / ".codex" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        'project_doc_fallback_filenames = ["PROJECT_GUIDE.md"]\n',
        encoding="utf-8",
    )
    _trust_project(codex_home, tmp_path)
    (tmp_path / "USER_GUIDE.md").write_text("# User fallback\n", encoding="utf-8")
    project_fallback = tmp_path / "PROJECT_GUIDE.md"
    project_fallback.write_text("# Project fallback\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == project_fallback
    assert AGENTS_BEGIN_MARKER in project_fallback.read_text(encoding="utf-8")
    assert (tmp_path / "USER_GUIDE.md").read_text(encoding="utf-8") == (
        "# User fallback\n"
    )


@pytest.mark.unit
def test_system_config_fallback_is_used_below_user_config(
    tmp_path: Path,
    codex_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_system_config(
        monkeypatch,
        tmp_path,
        'project_doc_fallback_filenames = ["SYSTEM_GUIDE.md"]\n',
    )
    system_guide = tmp_path / "SYSTEM_GUIDE.md"
    system_guide.write_text("# System guide\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == system_guide
    assert AGENTS_BEGIN_MARKER in system_guide.read_text(encoding="utf-8")
    assert not (codex_home / "config.toml").exists()


@pytest.mark.unit
def test_user_fallback_overrides_system_config(
    tmp_path: Path,
    codex_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_system_config(
        monkeypatch,
        tmp_path,
        'project_doc_fallback_filenames = ["SYSTEM_GUIDE.md"]\n',
    )
    _write_fallback_config(codex_home, ["USER_GUIDE.md"])
    system_guide = tmp_path / "SYSTEM_GUIDE.md"
    user_guide = tmp_path / "USER_GUIDE.md"
    system_guide.write_text("# System guide\n", encoding="utf-8")
    user_guide.write_text("# User guide\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == user_guide
    assert AGENTS_BEGIN_MARKER in user_guide.read_text(encoding="utf-8")
    assert system_guide.read_text(encoding="utf-8") == "# System guide\n"


@pytest.mark.unit
def test_empty_project_fallback_list_clears_user_config(
    tmp_path: Path, codex_home: Path
) -> None:
    _write_fallback_config(codex_home, ["USER_GUIDE.md"])
    project_config = tmp_path / ".codex" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        "project_doc_fallback_filenames = []\n",
        encoding="utf-8",
    )
    _trust_project(codex_home, tmp_path)
    user_fallback = tmp_path / "USER_GUIDE.md"
    user_fallback.write_text("# User fallback\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == tmp_path / "AGENTS.md"
    assert user_fallback.read_text(encoding="utf-8") == "# User fallback\n"


@pytest.mark.unit
def test_remove_project_agents_md_cleans_configured_fallback(
    tmp_path: Path, codex_home: Path
) -> None:
    _write_fallback_config(codex_home, ["TEAM_GUIDE.md"])
    fallback = tmp_path / "TEAM_GUIDE.md"
    fallback.write_text("# Team-owned guidance\n", encoding="utf-8")
    assert bootstrap_project_agents_md(tmp_path) == fallback

    result = remove_project_agents_md(tmp_path)

    assert result.removed == (fallback,)
    assert result.errors == ()
    assert fallback.read_text(encoding="utf-8").startswith("# Team-owned guidance")
    assert AGENTS_BEGIN_MARKER not in fallback.read_text(encoding="utf-8")


@pytest.mark.unit
def test_remove_project_agents_md_finds_fallback_after_config_changes(
    tmp_path: Path, codex_home: Path
) -> None:
    _write_fallback_config(codex_home, ["TEAM_GUIDE.md"])
    fallback = tmp_path / "TEAM_GUIDE.md"
    fallback.write_text("# Team-owned guidance\n", encoding="utf-8")
    assert bootstrap_project_agents_md(tmp_path) == fallback

    # Uninstall may run after the user renamed or removed the fallback setting.
    _write_fallback_config(codex_home, ["NEW_GUIDE.md"])
    result = remove_project_agents_md(tmp_path)

    assert result.removed == (fallback,)
    assert result.errors == ()
    text = fallback.read_text(encoding="utf-8")
    assert text == "# Team-owned guidance\n"


@pytest.mark.unit
def test_remove_finds_nested_managed_fallback_after_config_changes(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    _write_fallback_config(codex_home, ["docs/TEAM_GUIDE.md"])
    nested = tmp_path / "docs" / "TEAM_GUIDE.md"
    nested.parent.mkdir()
    nested.write_text("# Nested team-owned guidance\n", encoding="utf-8")
    assert bootstrap_project_agents_md(tmp_path) == nested

    _write_fallback_config(codex_home, ["NEW_GUIDE.md"])
    result = remove_project_agents_md(tmp_path)

    assert result.removed == (nested,)
    assert result.errors == ()
    assert nested.read_text(encoding="utf-8") == "# Nested team-owned guidance\n"


@pytest.mark.unit
def test_empty_configured_fallback_is_selected_before_new_agents_md(
    tmp_path: Path, codex_home: Path
) -> None:
    _write_fallback_config(codex_home, ["TEAM_GUIDE.md"])
    fallback = tmp_path / "TEAM_GUIDE.md"
    fallback.write_text(" \n\t", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == fallback
    assert AGENTS_BEGIN_MARKER in fallback.read_text(encoding="utf-8")
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_malformed_codex_config_falls_back_safely_to_agents_md(
    tmp_path: Path, codex_home: Path
) -> None:
    (codex_home / "config.toml").write_text(
        'project_doc_fallback_filenames = ["TEAM_GUIDE.md"\n',
        encoding="utf-8",
    )
    fallback = tmp_path / "TEAM_GUIDE.md"
    fallback.write_text("# Existing fallback\n", encoding="utf-8")

    path = bootstrap_project_agents_md(tmp_path)

    assert path == tmp_path / "AGENTS.md"
    assert path.exists()
    assert fallback.read_text(encoding="utf-8") == "# Existing fallback\n"


@pytest.mark.unit
def test_unsafe_configured_fallback_paths_are_rejected(
    tmp_path: Path, codex_home: Path
) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    _write_fallback_config(
        codex_home,
        [
            "../outside.md",
            str(outside.resolve()),
            "nested/../../outside.md",
        ],
    )

    path = bootstrap_project_agents_md(project)

    assert path == project / "AGENTS.md"
    assert path.exists()
    assert outside.read_text(encoding="utf-8") == "# Outside\n"


@pytest.mark.unit
def test_global_agents_md_ignores_project_fallback_configuration(
    codex_home: Path,
) -> None:
    _write_fallback_config(codex_home, ["TEAM_GUIDE.md"])
    fallback = codex_home / "TEAM_GUIDE.md"
    fallback.write_text("# Project-style fallback\n", encoding="utf-8")

    path = bootstrap_global_agents_md()

    assert path == codex_home / "AGENTS.md"
    assert path.exists()
    assert fallback.read_text(encoding="utf-8") == "# Project-style fallback\n"


@pytest.mark.unit
def test_global_agents_md_honors_codex_home_and_existing_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "custom-codex"
    configured.mkdir()
    override = configured / "AGENTS.override.md"
    override.write_text("# Global override\n", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(configured))

    path = bootstrap_global_agents_md(tmp_path / "ignored-home")

    assert path == override
    assert AGENTS_BEGIN_MARKER in override.read_text(encoding="utf-8")
    assert not (tmp_path / "ignored-home" / ".codex").exists()


@pytest.mark.unit
def test_remove_project_blocks_cleans_active_and_stale_files_only(
    tmp_path: Path,
) -> None:
    standard = tmp_path / "AGENTS.md"
    standard.write_text("# Standard rules\n", encoding="utf-8")
    bootstrap_project_agents_md(tmp_path)

    override = tmp_path / "AGENTS.override.md"
    override.write_text("# Override rules\n", encoding="utf-8")
    bootstrap_project_agents_md(tmp_path)

    result = remove_project_agents_md(tmp_path)

    assert result.removed == (override, standard)
    assert result.errors == ()
    assert "# Standard rules" in standard.read_text(encoding="utf-8")
    assert "# Override rules" in override.read_text(encoding="utf-8")
    assert AGENTS_BEGIN_MARKER not in standard.read_text(encoding="utf-8")
    assert AGENTS_BEGIN_MARKER not in override.read_text(encoding="utf-8")


@pytest.mark.unit
def test_remove_global_block_deletes_otherwise_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(configured))
    path = bootstrap_global_agents_md(tmp_path / "ignored")
    assert path.exists()

    result = remove_global_agents_md(tmp_path / "ignored")
    assert result.removed == (path,)
    assert result.errors == ()
    assert not path.exists()


@pytest.mark.unit
def test_remove_only_block_preserves_symlink_and_clears_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "shared-agents.md"
    target.write_text("", encoding="utf-8")
    agents_md = tmp_path / "AGENTS.md"
    agents_md.symlink_to(target.name)
    bootstrap_project_agents_md(tmp_path)

    result = remove_project_agents_md(tmp_path)
    assert result.removed == (agents_md,)
    assert result.errors == ()
    assert agents_md.is_symlink()
    assert target.read_text(encoding="utf-8") == ""


@pytest.mark.unit
def test_project_guidance_refuses_out_of_scope_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    target = tmp_path / "outside.md"
    target.write_text("# Outside\n", encoding="utf-8")
    guidance = project / "AGENTS.md"
    guidance.symlink_to(target)

    with pytest.raises(ValueError, match="out-of-scope"):
        bootstrap_project_agents_md(project)

    assert guidance.is_symlink()
    assert target.read_text(encoding="utf-8") == "# Outside\n"

    result = remove_project_agents_md(project)
    assert result.removed == ()
    assert len(result.errors) == 1
    assert "out-of-scope" in result.errors[0].message
    assert guidance.is_symlink()
    assert target.read_text(encoding="utf-8") == "# Outside\n"


@pytest.mark.unit
def test_remove_reversed_markers_fails_without_modifying_user_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "AGENTS.md"
    original = f"{AGENTS_END_MARKER}\nKeep me.\n{AGENTS_BEGIN_MARKER}\n"
    path.write_text(original, encoding="utf-8")

    result = remove_project_agents_md(tmp_path)

    assert result.removed == ()
    assert len(result.errors) == 1
    assert result.errors[0].path == path
    assert "end marker before" in result.errors[0].message
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.unit
def test_remove_agents_files_continues_after_malformed_override(
    tmp_path: Path,
) -> None:
    standard = bootstrap_project_agents_md(tmp_path)
    override = tmp_path / "AGENTS.override.md"
    malformed = f"{AGENTS_END_MARKER}\nKeep me.\n{AGENTS_BEGIN_MARKER}\n"
    override.write_text(malformed, encoding="utf-8")

    result = remove_project_agents_md(tmp_path)

    assert result.removed == (standard,)
    assert not standard.exists()
    assert len(result.errors) == 1
    assert result.errors[0].path == override
    assert "end marker before" in result.errors[0].message
    assert override.read_text(encoding="utf-8") == malformed


@pytest.mark.unit
def test_project_guidance_relocates_existing_managed_block_to_front(
    tmp_path: Path,
) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# Team rules\n\n" + "x" * 40_000 + "\n", encoding="utf-8")

    first = bootstrap_project_agents_md(tmp_path).read_text(encoding="utf-8")
    second = bootstrap_project_agents_md(tmp_path).read_text(encoding="utf-8")

    assert first == second
    assert first.startswith(AGENTS_BEGIN_MARKER)
    assert first.endswith("# Team rules\n\n" + "x" * 40_000 + "\n")


@pytest.mark.unit
def test_project_guidance_refuses_too_small_codex_byte_budget(
    tmp_path: Path, codex_home: Path
) -> None:
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text("project_doc_max_bytes = 64\n", encoding="utf-8")
    _trust_project(codex_home, tmp_path)

    with pytest.raises(ValueError, match="project_doc_max_bytes"):
        bootstrap_project_agents_md(tmp_path)

    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_system_config_byte_budget_is_used_below_user_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_system_config(
        monkeypatch,
        tmp_path,
        "project_doc_max_bytes = 64\n",
    )

    with pytest.raises(ValueError, match="project_doc_max_bytes"):
        bootstrap_project_agents_md(tmp_path)

    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_zero_project_doc_budget_disables_managed_guidance(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    (codex_home / "config.toml").write_text(
        "project_doc_max_bytes = 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="project_doc_max_bytes is 0"):
        bootstrap_project_agents_md(tmp_path)

    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.unit
def test_user_byte_budget_overrides_smaller_system_budget(
    tmp_path: Path,
    codex_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_system_config(
        monkeypatch,
        tmp_path,
        "project_doc_max_bytes = 64\n",
    )
    (codex_home / "config.toml").write_text(
        "project_doc_max_bytes = 32768\n",
        encoding="utf-8",
    )

    path = bootstrap_project_agents_md(tmp_path)

    assert path.exists()
    assert AGENTS_END_MARKER in path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_project_byte_budget_overrides_smaller_user_budget(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    (codex_home / "config.toml").write_text(
        "project_doc_max_bytes = 64\n",
        encoding="utf-8",
    )
    project_config = tmp_path / ".codex" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        "project_doc_max_bytes = 32768\n",
        encoding="utf-8",
    )
    _trust_project(codex_home, tmp_path)

    path = bootstrap_project_agents_md(tmp_path)

    assert path.exists()
    assert AGENTS_END_MARKER in path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_untrusted_project_config_cannot_redirect_guidance(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    project = tmp_path / "untrusted-repo"
    project.mkdir()
    readme = project / "README.md"
    readme.write_text("# User documentation\n", encoding="utf-8")
    project_config = project / ".codex" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        'project_doc_fallback_filenames = ["README.md"]\nproject_doc_max_bytes = 1\n',
        encoding="utf-8",
    )
    (codex_home / "config.toml").write_text(
        f'[projects.{json.dumps(str(project.resolve()))}]\ntrust_level = "untrusted"\n',
        encoding="utf-8",
    )

    path = bootstrap_project_agents_md(project)

    assert path == project / "AGENTS.md"
    assert path.exists()
    assert readme.read_text(encoding="utf-8") == "# User documentation\n"


@pytest.mark.unit
def test_symlinked_trust_alias_does_not_transfer_trust_to_resolved_project(
    tmp_path: Path,
    codex_home: Path,
) -> None:
    project = tmp_path / "trusted-repo"
    project.mkdir()
    alias = tmp_path / "trusted-repo-alias"
    alias.symlink_to(project, target_is_directory=True)
    project_config = project / ".codex" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        'project_doc_fallback_filenames = ["TEAM_GUIDE.md"]\n',
        encoding="utf-8",
    )
    team_guide = project / "TEAM_GUIDE.md"
    team_guide.write_text("# Trusted team guidance\n", encoding="utf-8")
    (codex_home / "config.toml").write_text(
        f'[projects.{json.dumps(str(alias.absolute()))}]\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )

    path = bootstrap_project_agents_md(project)

    assert path == project / "AGENTS.md"
    assert AGENTS_BEGIN_MARKER in path.read_text(encoding="utf-8")
    assert team_guide.read_text(encoding="utf-8") == "# Trusted team guidance\n"


@pytest.mark.unit
def test_user_auto_init_owner_can_be_removed_selectively(tmp_path: Path) -> None:
    path = bootstrap_project_agents_md(
        tmp_path,
        owner=PROJECT_OWNER_USER_AUTO_INIT,
    )
    assert "dummyindex:owner:user-auto-init" in path.read_text(encoding="utf-8")

    result = remove_project_agents_md(
        tmp_path,
        owner=PROJECT_OWNER_USER_AUTO_INIT,
    )

    assert result.removed == (path,)
    assert not path.exists()


@pytest.mark.unit
def test_user_auto_init_does_not_take_or_remove_explicit_project_owner(
    tmp_path: Path,
) -> None:
    path = bootstrap_project_agents_md(tmp_path, owner=PROJECT_OWNER_EXPLICIT)
    bootstrap_project_agents_md(tmp_path, owner=PROJECT_OWNER_USER_AUTO_INIT)

    text = path.read_text(encoding="utf-8")
    assert "dummyindex:owner:project" in text
    assert "dummyindex:owner:user-auto-init" not in text

    result = remove_project_agents_md(
        tmp_path,
        owner=PROJECT_OWNER_USER_AUTO_INIT,
    )
    assert result.removed == ()
    assert path.exists()


@pytest.mark.unit
def test_user_uninstall_keeps_legacy_unowned_project_block(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(
        f"{AGENTS_BEGIN_MARKER}\nlegacy body\n{AGENTS_END_MARKER}\n",
        encoding="utf-8",
    )

    result = remove_project_agents_md(
        tmp_path,
        owner=PROJECT_OWNER_USER_AUTO_INIT,
    )

    assert result.removed == ()
    assert path.exists()
