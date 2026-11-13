"""Enumerate toolkit items from host config and terminal bundles. Read-only.

Host items come from three places per scope: MCP servers (``.mcp.json`` or
``~/.claude.json``), skills (``<scope>/.claude/skills/<name>/SKILL.md``), and plugin
toggles (``enabledPlugins``). Disabled MCP servers and skills are read back from
the stash, so they still show up with ``enabled: false``.
"""

from __future__ import annotations

from pathlib import Path

from .bundle import bundle_dir, load_manifest, mechanism_for
from .host import Layout, read_object, read_stash
from .items import ToolkitItem, fall_back


def _host_mcp(layout: Layout, scope: str) -> list[ToolkitItem]:
    servers = read_object(layout.mcp_read_path()).get("mcpServers", {})
    live = servers if isinstance(servers, dict) else {}
    out = [ToolkitItem("mcp", name, scope, True) for name in sorted(live)]
    for entry in read_stash(layout):
        name = entry.get("name")
        if entry.get("kind") == "mcp" and isinstance(name, str) and name not in live:
            out.append(ToolkitItem("mcp", name, scope, False))
    return out


def _host_skills(layout: Layout, scope: str) -> list[ToolkitItem]:
    out: list[ToolkitItem] = []
    live: set[str] = set()
    skills_dir = layout.skills_read_dir()
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                live.add(child.name)
                out.append(ToolkitItem("skill", child.name, scope, True))
    for entry in read_stash(layout):
        name = entry.get("name")
        if entry.get("kind") == "skill" and isinstance(name, str) and name not in live:
            out.append(ToolkitItem("skill", name, scope, False))
    return out


def _host_plugins(layout: Layout, scope: str) -> list[ToolkitItem]:
    toggles = read_object(layout.settings_read_path()).get("enabledPlugins", {})
    if not isinstance(toggles, dict):
        return []
    return [
        ToolkitItem("plugin", key, scope, value is True)
        for key, value in sorted(toggles.items())
        if isinstance(key, str) and "@" in key
    ]


def host_items(layout: Layout) -> list[ToolkitItem]:
    scope = layout.scope
    return (
        _host_mcp(layout, scope)
        + _host_skills(layout, scope)
        + _host_plugins(layout, scope)
    )


def bundle_items(out_dir: Path, terminal_id: str) -> list[ToolkitItem]:
    bdir = bundle_dir(out_dir, terminal_id)
    manifest = load_manifest(bdir)
    return [
        ToolkitItem(
            kind=item["kind"],
            name=item["name"],
            scope="terminal",
            enabled=bool(item.get("enabled")),
            mechanism=mechanism_for(item["kind"], item["name"], item.get("mechanism")),
            terminal_id=terminal_id,
        )
        for item in manifest["items"]
    ]


def list_items(
    *,
    project: Layout,
    user: Layout,
    kind: str | None,
    scope: str | None,
    terminal_id: str | None,
    out_dir: Path | None,
) -> list[ToolkitItem]:
    """Items filtered by requested kind and scope.

    No scope: project, user and (when ``terminal_id`` and ``out_dir`` are given)
    the terminal bundle. ``project`` or ``user``: that host scope only.
    ``terminal``: the bundle plus host items, with fallback fields on the host
    items, so the caller can see what a terminal request would really change.
    """
    items: list[ToolkitItem] = []
    if scope in (None, "project", "terminal"):
        items += host_items(project)
    if scope in (None, "user", "terminal"):
        items += host_items(user)
    if terminal_id is not None and out_dir is not None and scope in (None, "terminal"):
        items += bundle_items(out_dir, terminal_id)
    if kind is not None:
        items = [i for i in items if i.kind == kind]
    return [fall_back(item, scope) for item in items]
