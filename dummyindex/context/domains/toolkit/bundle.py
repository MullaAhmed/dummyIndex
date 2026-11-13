"""Per-terminal bundle under ``--out-dir``: the state and the launch argv.

Layout: ``<out_dir>/<terminal_id>/`` holds ``toolkit.json`` (the item manifest,
the only source of truth), plus files generated from it on every save:

- ``mcp.json``       MCP servers for enabled terminal MCP items
- ``settings.json``  ``enabledPlugins`` toggles (one file, so hooks can merge in)
- ``skills-dir/``    ``.claude/skills/<name>/SKILL.md`` for enabled skills
- ``plugins/<name>/`` copied plugin folders (launched only when enabled)

``launch_args`` is the argv array the GUI appends to the agent launch. Each entry
is one argv element, so the GUI passes it with ``Command::args`` and no quoting.
Callers never edit these files by hand.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..atomic_io import write_text_atomic
from .constants import (
    BUNDLE_MANIFEST,
    BUNDLE_MCP_FILE,
    BUNDLE_PLUGINS_DIR,
    BUNDLE_SETTINGS_FILE,
    BUNDLE_SKILLS_DIR,
    MECHANISM_ADD_DIR,
    MECHANISM_MCP_ADDITIVE,
    MECHANISM_MCP_EXCLUSIVE,
    MECHANISM_PLUGIN_DIR,
    MECHANISM_SETTINGS,
    SCHEMA_VERSION,
)
from .errors import ToolkitError
from .paths import refuse_links, safe_target, validate_terminal_id


def bundle_dir(out_dir: Path, terminal_id: str) -> Path:
    """``<out_dir>/<terminal_id>``; the id is validated before it becomes a path."""
    validate_terminal_id(terminal_id)
    return safe_target(out_dir, terminal_id)


def empty_manifest() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "items": []}


def load_manifest(bdir: Path) -> dict[str, Any]:
    path = safe_target(bdir, BUNDLE_MANIFEST)
    if not path.exists():
        return empty_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolkitError(
            "malformed_config", f"{path} is not valid JSON ({exc}); fix or remove it"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ToolkitError("malformed_config", f"{path} has no item list")
    for item in data["items"]:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("kind"), str)
            and isinstance(item.get("name"), str)
        ):
            raise ToolkitError(
                "malformed_config",
                f"{path} has an item without string 'kind' and 'name'",
            )
    return data


def find_item(manifest: dict[str, Any], kind: str, name: str) -> dict[str, Any] | None:
    for item in manifest["items"]:
        if item.get("kind") == kind and item.get("name") == name:
            return item
    return None


def _write_json(path: Path, data: Any) -> None:
    write_text_atomic(path, json.dumps(data, indent=2) + "\n")


def materialize(bdir: Path, manifest: dict[str, Any]) -> None:
    """Regenerate every generated file in the bundle from the manifest."""
    items = manifest["items"]
    mcp_servers = {
        i["name"]: i["definition"]
        for i in items
        if i["kind"] == "mcp" and i.get("enabled")
    }
    _write_json(safe_target(bdir, BUNDLE_MCP_FILE), {"mcpServers": mcp_servers})

    plugin_toggles = {
        i["name"]: bool(i.get("enabled"))
        for i in items
        if i["kind"] == "plugin" and "@" in i["name"]
    }
    _write_json(
        safe_target(bdir, BUNDLE_SETTINGS_FILE), {"enabledPlugins": plugin_toggles}
    )

    skills_root = safe_target(bdir, BUNDLE_SKILLS_DIR)
    if skills_root.exists():
        refuse_links(skills_root)
        shutil.rmtree(skills_root)
    for item in items:
        if item["kind"] == "skill" and item.get("enabled"):
            skill = safe_target(
                skills_root, ".claude", "skills", item["name"], "SKILL.md"
            )
            write_text_atomic(skill, item["definition"])

    keep = {i["name"] for i in items if i["kind"] == "plugin" and "@" not in i["name"]}
    plugins_root = safe_target(bdir, BUNDLE_PLUGINS_DIR)
    if plugins_root.exists():
        for child in plugins_root.iterdir():
            if child.is_dir() and child.name not in keep:
                refuse_links(child)
                shutil.rmtree(child)


def save(bdir: Path, manifest: dict[str, Any]) -> None:
    bdir.mkdir(parents=True, exist_ok=True)
    _write_json(safe_target(bdir, BUNDLE_MANIFEST), manifest)
    materialize(bdir, manifest)


def launch_args(bdir: Path, manifest: dict[str, Any]) -> list[str]:
    """argv for the bundle's enabled items, in a fixed order.

    MCP first (exclusive adds ``--strict-mcp-config``), then plugin folders, then
    the skills folder, then the single settings file. A plugin toggle file is
    emitted when any toggle exists, even a disabled one, because ``false`` is how
    a terminal disables an installed plugin for one session.
    """
    items = manifest["items"]
    args: list[str] = []
    mcp = [i for i in items if i["kind"] == "mcp" and i.get("enabled")]
    if mcp:
        if any(i.get("mechanism") == MECHANISM_MCP_EXCLUSIVE for i in mcp):
            args.append("--strict-mcp-config")
        args += ["--mcp-config", str(safe_target(bdir, BUNDLE_MCP_FILE))]
    for item in items:
        if item["kind"] == "plugin" and "@" not in item["name"] and item.get("enabled"):
            folder = safe_target(bdir, BUNDLE_PLUGINS_DIR, item["name"])
            args += ["--plugin-dir", str(folder)]
    if any(i["kind"] == "skill" and i.get("enabled") for i in items):
        args += ["--add-dir", str(safe_target(bdir, BUNDLE_SKILLS_DIR))]
    if any(i["kind"] == "plugin" and "@" in i["name"] for i in items):
        args += ["--settings", str(safe_target(bdir, BUNDLE_SETTINGS_FILE))]
    return args


def mechanism_for(kind: str, name: str, stored: str | None) -> str:
    """The launch mechanism an item uses inside its terminal bundle."""
    if kind == "mcp":
        return stored or MECHANISM_MCP_ADDITIVE
    if kind == "skill":
        return MECHANISM_ADD_DIR
    if "@" in name:
        return MECHANISM_SETTINGS
    return MECHANISM_PLUGIN_DIR
