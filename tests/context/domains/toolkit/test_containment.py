"""Escape refusal: traversal names, bad terminal ids, symlinked config, source schemes."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.domains.toolkit import (
    ToolkitError,
    toolkit_install,
    toolkit_mutate,
)
from dummyindex.context.domains.toolkit.bundle import load_manifest
from dummyindex.context.domains.toolkit.host import project_layout
from dummyindex.context.domains.toolkit.listing import host_items
from dummyindex.context.domains.toolkit.source import parse_source
from tests.context.domains.toolkit.helpers import SKILL_TEXT

pytestmark = pytest.mark.unit


def _link_outside(link: Path, target: Path) -> None:
    """A symlink, or on Windows a directory junction (needs no admin rights)."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    if os.name == "nt":
        done = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        if done.returncode == 0:
            return
    pytest.skip("this environment cannot create symlinks or junctions")


def _link_settings_outside(root: Path, outside_dir: Path) -> Path:
    """``<root>/.claude/settings.json`` resolving outside ``root``.

    Prefers a file symlink; without that privilege (Windows) it links the
    ``.claude`` folder as a junction, which the containment check also sees.
    """
    claude = root / ".claude"
    outside_dir.mkdir(parents=True, exist_ok=True)
    try:
        claude.mkdir()
        (claude / "settings.json").symlink_to(outside_dir / "settings.json")
        return claude / "settings.json"
    except OSError:
        pass
    if claude.exists():
        claude.rmdir()
    if os.name == "nt":
        done = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(claude), str(outside_dir)],
            capture_output=True,
            check=False,
        )
        if done.returncode == 0:
            return claude / "settings.json"
    pytest.skip("this environment cannot create symlinks or junctions")


def _server(tmp_path: Path) -> Path:
    path = tmp_path / "s.json"
    path.write_text('{"command": "node"}', encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "name",
    ["../escape", "..", "a/b", "a\\b", ".hidden", "", "C:evil"],
)
def test_traversal_names_are_refused(
    root: Path, home: Path, tmp_path: Path, name: str
) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            name,
            root=root,
            home=home,
            kind="mcp",
            scope="project",
            config_file=_server(tmp_path),
        )
    assert exc.value.code == "invalid_name"
    assert not (root / ".mcp.json").exists()


def test_plugin_key_with_traversal_half_is_refused(root: Path, home: Path) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate("enable", "codex@../evil", root=root, home=home, kind="plugin")
    assert exc.value.code == "invalid_name"


@pytest.mark.parametrize("terminal", ["../x", "a/b", "", "has space"])
def test_bad_terminal_ids_are_refused(
    root: Path, home: Path, out_dir: Path, tmp_path: Path, terminal: str
) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="terminal",
            terminal_id=terminal,
            out_dir=out_dir,
            config_file=_server(tmp_path),
        )
    assert exc.value.code == "invalid_terminal_id"


def test_out_dir_inside_context_is_refused(
    root: Path, home: Path, tmp_path: Path
) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-1",
            out_dir=root / ".context" / "bundles",
            config_file=_server(tmp_path),
        )
    assert exc.value.code == "invalid_argument"
    assert not (root / ".context" / "bundles").exists()


def test_relative_out_dir_is_refused(root: Path, home: Path, tmp_path: Path) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-1",
            out_dir=Path("relative/dir"),
            config_file=_server(tmp_path),
        )
    assert exc.value.code == "invalid_argument"


def test_symlinked_claude_dir_escaping_root_is_refused(
    root: Path, home: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    _link_outside(root / ".claude", outside)
    src = tmp_path / "in.md"
    src.write_text(SKILL_TEXT, encoding="utf-8")

    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "demo",
            root=root,
            home=home,
            kind="skill",
            scope="project",
            source_file=src,
        )
    assert exc.value.code == "path_escape"
    assert list(outside.iterdir()) == []


def test_symlinked_mcp_file_escaping_root_is_refused(
    root: Path, home: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        (root / ".mcp.json").symlink_to(outside)
    except OSError:
        pytest.skip("this environment cannot create file symlinks")
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="project",
            config_file=_server(tmp_path),
        )
    assert exc.value.code == "path_escape"
    assert outside.read_text(encoding="utf-8") == "{}"


def test_context_dir_redirected_outside_root_blocks_the_stash(
    root: Path, home: Path, tmp_path: Path
) -> None:
    """The stash lives under .context/; a redirected .context must refuse the write."""
    outside = tmp_path / "elsewhere-context"
    outside.mkdir()
    (root / ".context").rmdir()
    _link_outside(root / ".context", outside)
    src = tmp_path / "in.md"
    src.write_text(SKILL_TEXT, encoding="utf-8")
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "demo",
            root=root,
            home=home,
            kind="skill",
            scope="project",
            source_file=src,
        )
    assert exc.value.code == "path_escape"
    assert not (root / ".claude").exists()
    assert list(outside.iterdir()) == []


def test_symlinked_out_dir_terminal_tree_is_refused(
    root: Path, home: Path, tmp_path: Path
) -> None:
    """A junction inside the bundle folder must not redirect bundle writes."""
    out = tmp_path / "app-data"
    out.mkdir()
    outside = tmp_path / "outside-bundle"
    outside.mkdir()
    _link_outside(out / "t-link", outside)
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-link",
            out_dir=out,
            config_file=_server(tmp_path),
        )
    assert exc.value.code == "path_escape"
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "source",
    [
        "https://github.com/o/r",
        "file:///etc/passwd",
        "C:/evil/path",
        "git+ssh://host/o/r",
        "GITHUB:o/r",
        "npm:left-pad",
        "",
    ],
)
def test_disallowed_source_schemes_are_refused(
    root: Path, home: Path, source: str
) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_install("skill", source, root=root, home=home, preview=True)
    assert exc.value.code in ("unsupported_source", "invalid_source")


@pytest.mark.parametrize(
    "source",
    [
        "github:o",
        "github:o/r/../x",
        "github:o/r/a\\b",
        "github:o/r@../x",
        "github:bad repo/x",
    ],
)
def test_malformed_github_sources_are_refused(source: str) -> None:
    with pytest.raises(ToolkitError) as exc:
        parse_source(source)
    assert exc.value.code == "invalid_source"


def test_github_source_parses_ref_and_subpath() -> None:
    parsed = parse_source("github:owner/repo/skills/demo@feature/x")
    assert parsed.repo == "owner/repo"
    assert parsed.subpath == "skills/demo"
    assert parsed.git_ref == "feature/x"
    assert parsed.scheme == "github"


def test_plugin_folder_containing_a_link_is_refused(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    plugin = tmp_path / "plug"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside-content"
    outside.mkdir()
    _link_outside(plugin / "linked", outside)
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "add",
            "lint",
            root=root,
            home=home,
            kind="plugin",
            scope="terminal",
            terminal_id="t-8",
            out_dir=out_dir,
            source_dir=plugin,
        )
    assert exc.value.code == "path_escape"
    assert not (out_dir / "t-8" / "plugins" / "lint").exists()


def test_install_cannot_target_terminal_scope(root: Path, home: Path) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "skill",
            "github:o/r/demo",
            root=root,
            home=home,
            scope="terminal",
            preview=True,
        )
    assert exc.value.code == "unsupported_scope"


def test_read_of_symlinked_settings_outside_scope_is_allowed(
    root: Path, home: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    _link_settings_outside(root, outside)
    (outside / "settings.json").write_text(
        '{"enabledPlugins": {"codex@m": true}}', encoding="utf-8"
    )
    items = host_items(project_layout(root))
    assert any(i.name == "codex@m" and i.enabled for i in items)


def test_write_through_escaping_symlink_is_still_refused(
    root: Path, home: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    _link_settings_outside(root, outside)
    original = '{"enabledPlugins": {"codex@m": false}}'
    (outside / "settings.json").write_text(original, encoding="utf-8")
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate("enable", "codex@m", root=root, home=home, kind="plugin")
    assert exc.value.code == "path_escape"
    assert (outside / "settings.json").read_text(encoding="utf-8") == original


def test_bundle_item_with_bad_shape_is_malformed_config(tmp_path: Path) -> None:
    bdir = tmp_path / "term"
    bdir.mkdir()
    (bdir / "toolkit.json").write_text(
        json.dumps({"schema_version": 1, "items": ["not-an-object"]}),
        encoding="utf-8",
    )
    with pytest.raises(ToolkitError) as exc:
        load_manifest(bdir)
    assert exc.value.code == "malformed_config"
