"""Installed skill upgrades preserve file ownership and one shared workflow."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from dummyindex.cli import check
from dummyindex.installer import install, uninstall
from dummyindex.installer.common import LinkMode
from dummyindex.installer.link.models import LinkInstallResult
from dummyindex.installer.ownership import (
    MANIFEST_NAME,
    content_hash,
    family_is_pristine,
    read_manifest,
    remove_family,
    sync_family,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def no_links(monkeypatch: pytest.MonkeyPatch) -> None:
    package = importlib.import_module("dummyindex.installer.install")
    monkeypatch.setattr(
        package,
        "run_link_install",
        lambda *args, **kwargs: LinkInstallResult(LinkMode.COPY, None, True, ()),
    )


def test_auto_without_symlinks_has_one_body_and_thin_references(
    tmp_path: Path, no_links
) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True)
    canonical = tmp_path / ".agents/skills/dummyindex"
    native = tmp_path / ".claude/skills/dummyindex"
    assert "dummyindex:skill-reference" not in (canonical / "SKILL.md").read_text(
        encoding="utf-8"
    )
    pointer = (native / "SKILL.md").read_text(encoding="utf-8")
    assert "dummyindex:skill-reference" in pointer
    assert "../../../.agents/skills/dummyindex/SKILL.md" in pointer
    assert not (native / "council").exists()
    assert (canonical / "council").is_dir()
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    before_stats = {
        p: p.stat().st_mtime_ns
        for p in (
            native,
            native / MANIFEST_NAME,
            native / ".dummyindex_version",
            canonical,
        )
    }
    install(scope="project", project_dir=tmp_path, skill_only=True)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert {p: p.stat().st_mtime_ns for p in before_stats} == before_stats


def test_claude_only_auto_prepares_shared_dependency(tmp_path: Path, no_links) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True, platform="claude")
    assert (tmp_path / ".agents/skills/dummyindex/SKILL.md").is_file()
    assert "dummyindex:skill-reference" in (
        tmp_path / ".claude/skills/dummyindex/SKILL.md"
    ).read_text(encoding="utf-8")


def test_same_version_update_uses_hashes_and_preserves_edits(tmp_path: Path) -> None:
    directory = tmp_path / "dummyindex"
    sync_family(
        directory,
        {"SKILL.md": "stock v1", "guide.md": "guide"},
        family="dummyindex",
        version="1.0.0",
    )
    (directory / "guide.md").write_text("user guide", encoding="utf-8")
    (directory / "unknown.md").write_text("user notes", encoding="utf-8")
    result = sync_family(
        directory,
        {"SKILL.md": "stock v2", "guide.md": "new guide"},
        family="dummyindex",
        version="1.0.0",
    )
    assert (directory / "SKILL.md").read_text(encoding="utf-8") == "stock v2"
    assert (directory / "guide.md").read_text(encoding="utf-8") == "user guide"
    assert (directory / "unknown.md").read_text(encoding="utf-8") == "user notes"
    assert result.preserved == ("guide.md",)
    manifest = read_manifest(directory)
    assert manifest["complete"] is False
    assert manifest["files"]["guide.md"] == content_hash(b"guide")
    assert not family_is_pristine(directory)


def test_stamp_does_not_authorize_ambiguous_legacy_overwrite(tmp_path: Path) -> None:
    directory = tmp_path / ".agents/skills/dummyindex"
    directory.mkdir(parents=True)
    (directory / ".dummyindex_version").write_text("0.36.0", encoding="utf-8")
    (directory / "SKILL.md").write_text("my custom workflow", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        install(
            scope="project", project_dir=tmp_path, skill_only=True, platform="codex"
        )
    assert exc.value.code == 1
    assert (directory / "SKILL.md").read_text(encoding="utf-8") == "my custom workflow"
    assert read_manifest(directory)["complete"] is False


def test_official_legacy_file_can_be_upgraded_without_claiming_unknowns(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "dummyindex-remember"
    directory.mkdir()
    stock = (
        Path(__file__).parent / "fixtures/legacy_skill_md/remember_0_36.md"
    ).read_text(encoding="utf-8")
    (directory / "SKILL.md").write_text(stock, encoding="utf-8")
    (directory / ".dummyindex_version").write_text("0.36.0", encoding="utf-8")
    assert family_is_pristine(directory)
    (directory / "notes.md").write_text("mine", encoding="utf-8")
    assert not family_is_pristine(directory)
    result = sync_family(
        directory,
        {"SKILL.md": "new stock"},
        family="dummyindex-remember",
        version="1.0.0",
    )
    assert result.complete
    assert (directory / "SKILL.md").read_text(encoding="utf-8") == "new stock"
    assert (directory / "notes.md").read_text(encoding="utf-8") == "mine"


def test_uninstall_then_reinstall_preserves_edited_survivor(
    tmp_path: Path, no_links
) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True)
    directory = tmp_path / ".agents/skills/dummyindex-plan"
    skill = directory / "SKILL.md"
    edited = skill.read_text(encoding="utf-8") + "\nmy policy\n"
    skill.write_text(edited, encoding="utf-8")
    uninstall(scope="project", project_dir=tmp_path)
    assert skill.read_text(encoding="utf-8") == edited
    assert (directory / MANIFEST_NAME).is_file()
    with pytest.raises(SystemExit) as exc:
        install(scope="project", project_dir=tmp_path, skill_only=True)
    assert exc.value.code == 1
    assert skill.read_text(encoding="utf-8") == edited


def test_retirement_removes_only_proven_files(tmp_path: Path) -> None:
    sync_family(
        tmp_path,
        {"SKILL.md": "stock", "retired.md": "old"},
        family="dummyindex",
        version="1.0.0",
    )
    (tmp_path / "personal.md").write_text("mine", encoding="utf-8")
    result = sync_family(
        tmp_path, {"SKILL.md": "stock"}, family="dummyindex", version="1.1.0"
    )
    assert result.removed == ("retired.md",)
    remove_family(tmp_path)
    assert (tmp_path / "personal.md").read_text(encoding="utf-8") == "mine"


def test_copy_is_explicit_and_still_ownership_safe(tmp_path: Path) -> None:
    install(
        scope="project", project_dir=tmp_path, skill_only=True, link_mode=LinkMode.COPY
    )
    directory = tmp_path / ".claude/skills/dummyindex"
    assert (directory / "council").is_dir()
    skill = directory / "SKILL.md"
    skill.write_text("custom", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        install(
            scope="project",
            project_dir=tmp_path,
            skill_only=True,
            link_mode=LinkMode.COPY,
        )
    assert exc.value.code == 1
    assert skill.read_text(encoding="utf-8") == "custom"


def test_corrupt_ownership_manifest_never_authorizes_writes(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text("{bad", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("mine", encoding="utf-8")
    with pytest.raises(OSError, match="ownership manifest"):
        sync_family(
            tmp_path, {"SKILL.md": "stock"}, family="dummyindex", version="1.1.0"
        )
    assert remove_family(tmp_path) == ()
    assert (tmp_path / "SKILL.md").read_text(encoding="utf-8") == "mine"
    assert (tmp_path / MANIFEST_NAME).read_text(encoding="utf-8") == "{bad"


def test_version_check_detects_same_version_source_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from dummyindex.installer import ownership

    install(scope="project", project_dir=tmp_path, skill_only=True, platform="codex")
    assert check._skill_source_warnings(tmp_path) == ()
    monkeypatch.setattr(ownership, "package_source_hash", lambda: "f" * 64)
    capsys.readouterr()
    assert check.run(["--versions", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "versions coherent" in output
    assert "CLI source differs" in output


def test_version_check_reports_edits_without_rebasing_them(
    tmp_path: Path, capsys
) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True, platform="codex")
    directory = tmp_path / ".agents/skills/dummyindex"
    before = read_manifest(directory)["files"]["SKILL.md"]
    skill = directory / "SKILL.md"
    edited = skill.read_text(encoding="utf-8") + "\nmy customization\n"
    skill.write_text(edited, encoding="utf-8")
    assert "content changed" in "; ".join(check._skill_source_warnings(tmp_path))
    with pytest.raises(SystemExit) as exc:
        install(
            scope="project", project_dir=tmp_path, skill_only=True, platform="codex"
        )
    assert exc.value.code == 1
    assert skill.read_text(encoding="utf-8") == edited
    assert read_manifest(directory)["files"]["SKILL.md"] == before
    assert "customized or incomplete" in "; ".join(
        check._skill_source_warnings(tmp_path)
    )


def test_install_preserves_custom_commands_and_project_config(
    tmp_path: Path, no_links
) -> None:
    commands = tmp_path / ".claude/commands"
    commands.mkdir(parents=True)
    token_command = commands / "tokens.md"
    token_command.write_text("my token command", encoding="utf-8")
    config = tmp_path / ".context/config.json"
    config.parent.mkdir()
    original = b'{"custom":true}\n'
    config.write_bytes(original)
    install(scope="project", project_dir=tmp_path, skill_only=True)
    assert token_command.read_text(encoding="utf-8") == "my token command"
    assert config.read_bytes() == original


def test_agents_uninstall_removes_only_unchanged_dependent_claude_references(
    tmp_path, no_links
):
    from dummyindex.installer import uninstall

    install(scope="project", project_dir=tmp_path, skill_only=True)
    edited = tmp_path / ".claude/skills/dummyindex-plan/SKILL.md"
    edited.write_bytes(edited.read_bytes() + b"\nmy changes\n")
    unknown = tmp_path / ".claude/skills/dummyindex/personal.md"
    unknown.write_text("mine", encoding="utf-8")
    uninstall(scope="project", project_dir=tmp_path, platform="agents")
    assert not (tmp_path / ".agents/skills/dummyindex/SKILL.md").exists()
    assert not (tmp_path / ".claude/skills/dummyindex/SKILL.md").exists()
    assert unknown.read_text(encoding="utf-8") == "mine"
    assert edited.read_bytes().endswith(b"my changes\n")


def test_native_link_targets_use_host_separators(tmp_path):
    import errno

    from dummyindex.installer.link import create_family_links
    from dummyindex.installer.link.classify import relative_link_value
    from dummyindex.installer.link.orchestrate import _probe_symlink_capability

    canonical = tmp_path / ".agents/skills/dummyindex"
    sync_family(canonical, {"SKILL.md": "stock"}, family="dummyindex", version="1.0.0")
    targets = []

    def unavailable(source, destination, **kwargs):
        targets.append(source)
        raise OSError(errno.EPERM, "no links in this deterministic test")

    _probe_symlink_capability(tmp_path, symlink_fn=unavailable)
    create_family_links(tmp_path, symlink_fn=unavailable)
    assert targets
    assert all(
        target == str(Path(relative_link_value("dummyindex"))) for target in targets[:2]
    )
    if __import__("os").name == "nt":
        assert all("/" not in target for target in targets)
