"""Add / enable / disable / remove across host config and terminal bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dummyindex.context.domains.toolkit.mutate as mutate_mod
from dummyindex.context.domains.toolkit import (
    ToolkitError,
    toolkit_list,
    toolkit_mutate,
    toolkit_show,
)
from dummyindex.context.domains.toolkit.constants import BUNDLE_MANIFEST
from dummyindex.context.domains.toolkit.host import user_layout
from tests.context.domains.toolkit.helpers import MCP_TEXT, SKILL_TEXT

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _server_file(tmp_path: Path, text: str = MCP_TEXT) -> Path:
    return _write(tmp_path / "server.json", text)


def _skill_file(tmp_path: Path, text: str = SKILL_TEXT) -> Path:
    return _write(tmp_path / "in" / "SKILL.md", text)


def _stash_entries(root: Path, name: str) -> list[dict]:
    path = root / ".context" / "toolkit" / "disabled.json"
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    return [i for i in items if i.get("name") == name]


def _mutate(action: str, name: str, root: Path, home: Path, **kw):
    return toolkit_mutate(action, name, root=root, home=home, **kw)


def test_project_mcp_disable_then_enable_round_trips_and_is_idempotent(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _server_file(tmp_path)
    added = _mutate(
        "add", "srv", root, home, kind="mcp", scope="project", config_file=cfg
    )
    assert added["changed"] is True
    assert added["item"]["enabled"] is True
    assert added["item"]["scope_warning"] is True
    assert added["restart_required"] is True
    assert added["launch_args"] == []

    disabled = _mutate("disable", "srv", root, home, kind="mcp", scope="project")
    assert disabled["changed"] is True
    assert disabled["backup_path"] is not None
    servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "srv" not in servers
    assert (root / ".context" / "toolkit" / "disabled.json").is_file()

    again = _mutate("disable", "srv", root, home, kind="mcp", scope="project")
    assert again["changed"] is False

    enabled = _mutate("enable", "srv", root, home, kind="mcp", scope="project")
    assert enabled["changed"] is True
    servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["srv"]["url"] == "https://example.test/mcp"


def test_add_merges_by_key_and_preserves_other_keys(
    root: Path, home: Path, tmp_path: Path
) -> None:
    original = {
        "mcpServers": {"other": {"command": "node", "args": ["x.js"]}},
        "unknownTopLevel": {"keep": True},
    }
    target = root / ".mcp.json"
    target.write_text(json.dumps(original), encoding="utf-8")
    cfg = _server_file(tmp_path)

    result = _mutate(
        "add", "new", root, home, kind="mcp", scope="project", config_file=cfg
    )

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert "new" in data["mcpServers"]
    assert data["unknownTopLevel"] == {"keep": True}
    backup = Path(result["backup_path"])
    assert backup.name.startswith(".mcp.json.bak-")
    assert json.loads(backup.read_text(encoding="utf-8")) == original


def test_add_never_overwrites_a_different_definition(
    root: Path, home: Path, tmp_path: Path
) -> None:
    target = root / ".mcp.json"
    target.write_text(
        json.dumps({"mcpServers": {"srv": {"command": "node"}}}), encoding="utf-8"
    )
    before = target.read_bytes()
    cfg = _server_file(tmp_path)

    with pytest.raises(ToolkitError) as exc:
        _mutate("add", "srv", root, home, kind="mcp", scope="project", config_file=cfg)

    assert exc.value.code == "already_exists"
    assert target.read_bytes() == before


def test_same_definition_add_is_a_no_op(root: Path, home: Path, tmp_path: Path) -> None:
    cfg = _server_file(tmp_path)
    _mutate("add", "srv", root, home, kind="mcp", scope="project", config_file=cfg)
    again = _mutate(
        "add", "srv", root, home, kind="mcp", scope="project", config_file=cfg
    )
    assert again["changed"] is False
    assert again["backup_path"] is None


def test_malformed_host_config_is_refused_and_left_alone(
    root: Path, home: Path
) -> None:
    settings = root / ".claude" / "settings.json"
    _write(settings, "{ not json")
    before = settings.read_bytes()

    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "enable", "codex@openai-codex", root, home, kind="plugin", scope="project"
        )

    assert exc.value.code == "malformed_config"
    assert settings.read_bytes() == before


def test_project_skill_round_trip_through_stash(
    root: Path, home: Path, tmp_path: Path
) -> None:
    src = _skill_file(tmp_path)
    _mutate("add", "demo", root, home, kind="skill", scope="project", source_file=src)
    skill = root / ".claude" / "skills" / "demo" / "SKILL.md"
    assert skill.read_text(encoding="utf-8") == SKILL_TEXT

    _mutate("disable", "demo", root, home, kind="skill", scope="project")
    assert not skill.exists()

    _mutate("enable", "demo", root, home, kind="skill", scope="project")
    assert skill.read_text(encoding="utf-8") == SKILL_TEXT


def test_skill_with_extra_files_cannot_be_disabled(
    root: Path, home: Path, tmp_path: Path
) -> None:
    src = _skill_file(tmp_path)
    _mutate("add", "demo", root, home, kind="skill", scope="project", source_file=src)
    _write(root / ".claude" / "skills" / "demo" / "helper.py", "print(1)\n")

    with pytest.raises(ToolkitError) as exc:
        _mutate("disable", "demo", root, home, kind="skill", scope="project")
    assert exc.value.code == "skill_has_extra_files"


def test_plugin_toggle_sets_explicit_true_false_and_remove_drops_key(
    root: Path, home: Path
) -> None:
    settings = root / ".claude" / "settings.json"
    _write(
        settings, json.dumps({"enabledPlugins": {"codex@openai-codex": True}, "x": 1})
    )

    off = _mutate(
        "disable", "codex@openai-codex", root, home, kind="plugin", scope="project"
    )
    assert off["changed"] is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["enabledPlugins"]["codex@openai-codex"] is False
    assert data["x"] == 1

    gone = _mutate(
        "remove", "codex@openai-codex", root, home, kind="plugin", scope="project"
    )
    assert gone["changed"] is True
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "codex@openai-codex" not in data["enabledPlugins"]


def test_enable_unknown_plugin_is_not_found(root: Path, home: Path) -> None:
    with pytest.raises(ToolkitError) as exc:
        _mutate("enable", "ghost@nowhere", root, home, kind="plugin", scope="project")
    assert exc.value.code == "not_found"


def test_user_scope_writes_only_under_home(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _server_file(tmp_path)
    result = _mutate(
        "add", "srv", root, home, kind="mcp", scope="user", config_file=cfg
    )
    assert result["item"]["scope"] == "user"
    assert json.loads((home / ".claude.json").read_text(encoding="utf-8"))[
        "mcpServers"
    ]["srv"]
    assert not (root / ".mcp.json").exists()


def test_terminal_items_live_in_bundle_and_report_mechanism(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    cfg = _server_file(tmp_path)
    result = _mutate(
        "add",
        "ex",
        root,
        home,
        kind="mcp",
        scope="terminal",
        terminal_id="t-1",
        out_dir=out_dir,
        config_file=cfg,
        mechanism="mcp_exclusive",
    )
    assert result["item"]["scope"] == "terminal"
    assert result["item"]["terminal_id"] == "t-1"
    assert result["item"]["mechanism"] == "mcp_exclusive"
    assert result["item"]["scope_warning"] is False
    assert result["backup_path"] is None
    assert result["launch_args"][0] == "--strict-mcp-config"
    assert result["launch_args"][1] == "--mcp-config"
    assert not (root / ".mcp.json").exists()


def test_terminal_launch_args_are_ordered_argv_with_hostile_paths(
    root: Path, home: Path, tmp_path: Path
) -> None:
    out = tmp_path / "a b" / "x&'y"
    out.mkdir(parents=True)
    plugin_src = tmp_path / "plug"
    _write(plugin_src / ".claude-plugin" / "plugin.json", "{}")
    _write(plugin_src / "skills" / "p" / "SKILL.md", SKILL_TEXT)
    cfg = _server_file(tmp_path)
    kw = {"scope": "terminal", "terminal_id": "t-9", "out_dir": out}

    _mutate("add", "srv", root, home, kind="mcp", config_file=cfg, **kw)
    _mutate("add", "lint", root, home, kind="plugin", source_dir=plugin_src, **kw)
    _mutate(
        "add", "demo", root, home, kind="skill", source_file=_skill_file(tmp_path), **kw
    )
    last = _mutate("add", "codex@openai-codex", root, home, kind="plugin", **kw)

    args = last["launch_args"]
    assert all(isinstance(a, str) for a in args)
    bundle = out / "t-9"
    assert args == [
        "--mcp-config",
        str(bundle / "mcp.json"),
        "--plugin-dir",
        str(bundle / "plugins" / "lint"),
        "--add-dir",
        str(bundle / "skills-dir"),
        "--settings",
        str(bundle / "settings.json"),
    ]
    settings = json.loads((bundle / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"enabledPlugins": {"codex@openai-codex": True}}


def test_terminal_disable_emits_settings_false_and_drops_mcp_args(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    kw = {"scope": "terminal", "terminal_id": "t-2", "out_dir": out_dir}
    _mutate("add", "codex@openai-codex", root, home, kind="plugin", **kw)
    off = _mutate("disable", "codex@openai-codex", root, home, kind="plugin", **kw)
    assert off["changed"] is True
    assert off["launch_args"] == [
        "--settings",
        str(out_dir / "t-2" / "settings.json"),
    ]
    again = _mutate("disable", "codex@openai-codex", root, home, kind="plugin", **kw)
    assert again["changed"] is False


def test_terminal_add_is_idempotent_for_identical_definitions(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    cfg = _server_file(tmp_path)
    kw = {
        "scope": "terminal",
        "terminal_id": "t-3",
        "out_dir": out_dir,
        "config_file": cfg,
    }
    first = _mutate("add", "srv", root, home, kind="mcp", **kw)
    second = _mutate("add", "srv", root, home, kind="mcp", **kw)
    assert first["changed"] is True
    assert second["changed"] is False


def test_terminal_request_for_host_item_refuses_without_opt_in(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="project",
        config_file=_server_file(tmp_path),
    )
    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "disable",
            "srv",
            root,
            home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-4",
            out_dir=out_dir,
        )
    assert exc.value.code == "scope_not_proven"
    assert "srv" in (root / ".mcp.json").read_text(encoding="utf-8")


def test_terminal_request_with_opt_in_applies_at_project_and_says_so(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="project",
        config_file=_server_file(tmp_path),
    )
    result = _mutate(
        "disable",
        "srv",
        root,
        home,
        kind="mcp",
        scope="terminal",
        terminal_id="t-4",
        out_dir=out_dir,
        allow_project_fallback=True,
    )
    item = result["item"]
    assert item["scope"] == "project"
    assert item["requested_scope"] == "terminal"
    assert item["scope_warning"] is True
    assert item["mechanism"] is None
    assert (
        "srv"
        not in json.loads((root / ".mcp.json").read_text(encoding="utf-8"))[
            "mcpServers"
        ]
    )


def test_list_with_terminal_scope_shows_host_items_as_fallback(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="project",
        config_file=_server_file(tmp_path),
    )
    listing = toolkit_list(
        root=root, home=home, scope="terminal", terminal_id="t-5", out_dir=out_dir
    )
    fallback = [i for i in listing["items"] if i["name"] == "srv"]
    assert fallback and fallback[0]["scope"] == "project"
    assert fallback[0]["requested_scope"] == "terminal"
    assert fallback[0]["scope_warning"] is True


def test_show_returns_bundle_args_only_for_terminal_items(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "codex@openai-codex",
        root,
        home,
        kind="plugin",
        scope="terminal",
        terminal_id="t-6",
        out_dir=out_dir,
    )
    shown = toolkit_show(
        "codex@openai-codex",
        root=root,
        home=home,
        scope="terminal",
        terminal_id="t-6",
        out_dir=out_dir,
    )
    assert shown["launch_args"] == [
        "--settings",
        str(out_dir / "t-6" / "settings.json"),
    ]
    assert shown["bundle_dir"] == str(out_dir / "t-6")

    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="project",
        config_file=_server_file(tmp_path),
    )
    host = toolkit_show("srv", root=root, home=home, scope="project")
    assert host["launch_args"] == []
    assert host["bundle_dir"] is None


def test_ambiguous_name_across_scopes_is_an_error(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _server_file(tmp_path)
    _mutate("add", "srv", root, home, kind="mcp", scope="project", config_file=cfg)
    _mutate("add", "srv", root, home, kind="mcp", scope="user", config_file=cfg)
    with pytest.raises(ToolkitError) as exc:
        toolkit_show("srv", root=root, home=home)
    assert exc.value.code == "ambiguous_item"


def test_plugin_folder_is_refused_at_host_scope(
    root: Path, home: Path, tmp_path: Path
) -> None:
    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "add",
            "lint",
            root,
            home,
            kind="plugin",
            scope="project",
            source_dir=tmp_path,
        )
    assert exc.value.code == "unsupported_scope"


def test_plugin_folder_needs_a_manifest(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "not-a-plugin"
    empty.mkdir()
    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "add",
            "lint",
            root,
            home,
            kind="plugin",
            scope="terminal",
            terminal_id="t-7",
            out_dir=out_dir,
            source_dir=empty,
        )
    assert exc.value.code == "invalid_argument"


def test_project_host_backup_goes_under_toolkit_backups(
    root: Path, home: Path, tmp_path: Path
) -> None:
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "node"}}}), encoding="utf-8"
    )
    result = _mutate(
        "add",
        "new",
        root,
        home,
        kind="mcp",
        scope="project",
        config_file=_server_file(tmp_path),
    )
    backup = Path(result["backup_path"])
    assert backup.parent == root / ".context" / "toolkit" / "backups"
    assert backup.name.startswith(".mcp.json.bak-")
    assert not list(root.glob(".mcp.json.bak-*"))


def test_user_host_backup_sits_next_to_the_file(
    root: Path, home: Path, tmp_path: Path
) -> None:
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    result = _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="user",
        config_file=_server_file(tmp_path),
    )
    backup = Path(result["backup_path"])
    assert backup.parent == home
    assert backup.name.startswith(".claude.json.bak-")


def test_removing_a_live_skill_copies_skill_md_before_delete(
    root: Path, home: Path, tmp_path: Path
) -> None:
    src = _skill_file(tmp_path)
    _mutate("add", "demo", root, home, kind="skill", scope="project", source_file=src)
    _mutate("remove", "demo", root, home, kind="skill", scope="project")

    assert not (root / ".claude" / "skills" / "demo").exists()
    copies = list(
        (root / ".context" / "toolkit" / "backups" / "skills" / "demo").glob(
            "SKILL.md.bak-*"
        )
    )
    assert len(copies) == 1
    assert copies[0].read_text(encoding="utf-8") == SKILL_TEXT


def test_enable_writes_host_before_stash_so_a_stash_crash_loses_nothing(
    root: Path, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _server_file(tmp_path)
    _mutate("add", "srv", root, home, kind="mcp", scope="project", config_file=cfg)
    _mutate("disable", "srv", root, home, kind="mcp", scope="project")

    def stash_crash(layout, items):
        raise OSError("disk full")

    monkeypatch.setattr(mutate_mod, "write_stash", stash_crash)
    with pytest.raises(OSError):
        _mutate("enable", "srv", root, home, kind="mcp", scope="project")

    servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["srv"]["url"] == "https://example.test/mcp"


def test_terminal_fallback_ignores_user_scope_match(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="user",
        config_file=_server_file(tmp_path),
    )
    user_file = user_layout(home).mcp_path()
    before = user_file.read_bytes()

    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "disable",
            "srv",
            root,
            home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-5",
            out_dir=out_dir,
            allow_project_fallback=True,
        )

    assert exc.value.code in ("not_found", "scope_not_proven")
    assert user_file.read_bytes() == before


def test_live_and_stashed_same_name_lists_once_and_resolves_with_kind(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _server_file(tmp_path)
    _mutate("add", "srv", root, home, kind="mcp", scope="project", config_file=cfg)
    _mutate("disable", "srv", root, home, kind="mcp", scope="project")
    _write(
        root / ".mcp.json",
        json.dumps({"mcpServers": {"srv": {"url": "https://live.test/mcp"}}}),
    )

    listed = toolkit_list(root=root, home=home, kind="mcp", scope="project")
    srv = [i for i in listed["items"] if i["name"] == "srv"]
    assert len(srv) == 1
    assert srv[0]["enabled"] is True

    result = _mutate("disable", "srv", root, home, kind="mcp", scope="project")
    assert result["changed"] is True
    servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert "srv" not in servers
    stashed = _stash_entries(root, "srv")
    assert [s["definition"] for s in stashed] == [{"url": "https://live.test/mcp"}]

    _mutate("enable", "srv", root, home, kind="mcp", scope="project")
    servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert servers["srv"] == {"url": "https://live.test/mcp"}


def test_live_and_stashed_skill_disable_leaves_one_stash_entry(
    root: Path, home: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "demo",
        root,
        home,
        kind="skill",
        scope="project",
        source_file=_skill_file(tmp_path),
    )
    _mutate("disable", "demo", root, home, kind="skill", scope="project")
    live_text = SKILL_TEXT + "\nlive\n"
    _write(root / ".claude" / "skills" / "demo" / "SKILL.md", live_text)

    result = _mutate("disable", "demo", root, home, kind="skill", scope="project")
    assert result["changed"] is True
    assert [s["definition"] for s in _stash_entries(root, "demo")] == [live_text]

    _mutate("enable", "demo", root, home, kind="skill", scope="project")
    skill = root / ".claude" / "skills" / "demo" / "SKILL.md"
    assert skill.read_text(encoding="utf-8") == live_text


def test_terminal_fallback_with_two_project_kinds_is_ambiguous_and_changes_nothing(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="mcp",
        scope="project",
        config_file=_server_file(tmp_path),
    )
    _mutate(
        "add",
        "srv",
        root,
        home,
        kind="skill",
        scope="project",
        source_file=_skill_file(tmp_path),
    )
    mcp_file = root / ".mcp.json"
    skill_file = root / ".claude" / "skills" / "srv" / "SKILL.md"
    before = (mcp_file.read_bytes(), skill_file.read_bytes())

    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "disable",
            "srv",
            root,
            home,
            scope="terminal",
            terminal_id="t-8",
            out_dir=out_dir,
            allow_project_fallback=True,
        )

    assert exc.value.code == "ambiguous_item"
    assert (mcp_file.read_bytes(), skill_file.read_bytes()) == before


def test_non_utf8_config_is_malformed_config(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = tmp_path / "server.json"
    cfg.write_bytes('{"command": "ñ"}'.encode("latin-1"))

    with pytest.raises(ToolkitError) as exc:
        _mutate("add", "srv", root, home, kind="mcp", scope="project", config_file=cfg)

    assert exc.value.code == "malformed_config"


def test_stash_entry_without_definition_is_malformed_config(
    root: Path, home: Path
) -> None:
    _write(
        root / ".context" / "toolkit" / "disabled.json",
        json.dumps({"schema_version": 1, "items": [{"kind": "mcp", "name": "srv"}]}),
    )

    with pytest.raises(ToolkitError) as exc:
        _mutate("enable", "srv", root, home, kind="mcp", scope="project")

    assert exc.value.code == "malformed_config"


def test_bundle_item_without_name_is_malformed_config(
    root: Path, home: Path, out_dir: Path
) -> None:
    _write(
        out_dir / "t-6" / BUNDLE_MANIFEST,
        json.dumps({"items": [{"kind": "mcp"}]}),
    )

    with pytest.raises(ToolkitError) as exc:
        _mutate(
            "disable",
            "srv",
            root,
            home,
            scope="terminal",
            terminal_id="t-6",
            out_dir=out_dir,
        )

    assert exc.value.code == "malformed_config"
