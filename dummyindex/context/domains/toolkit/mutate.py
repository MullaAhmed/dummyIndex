"""Add, remove, enable and disable toolkit items.

Terminal requests change only the terminal bundle under ``--out-dir``. Project
and user requests change host config by merge (one key at a time), after a
timestamped backup of that file in the same run (project backups live under
``.context/toolkit/backups/``, user backups next to the file). A removed skill is
copied into ``<toolkit dir>/backups/skills/`` before it is deleted. Disabled MCP
servers and skills move into a stash under ``.context/toolkit/`` (project) or ``<claude>/toolkit/``
(user) and come back on enable. Each call returns ``changed``, so repeating a
request is a no-op.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..atomic_io import write_text_atomic
from .bundle import (
    bundle_dir,
    find_item,
    launch_args,
    load_manifest,
    mechanism_for,
    save,
)
from .constants import (
    BUNDLE_PLUGINS_DIR,
    MECHANISM_ADD_DIR,
    MECHANISM_PLUGIN_DIR,
    MECHANISM_SETTINGS,
    PROVEN_TERMINAL_MECHANISMS,
)
from .errors import ToolkitError
from .host import (
    Layout,
    WriteSession,
    find_stash,
    preserve_skill,
    read_object,
    read_stash,
    write_object,
    write_stash,
)
from .items import ToolkitItem, fall_back
from .listing import host_items
from .paths import (
    check_out_dir,
    refuse_links,
    safe_target,
    validate_name,
    validate_plugin_key,
)

ACTIONS = ("add", "remove", "enable", "disable")
SCOPE_PROVEN_HINT = (
    "Pass --allow-project-fallback to apply this at project scope anyway; "
    "other sessions in the repo will be affected."
)


@dataclass(frozen=True)
class Request:
    action: str
    kind: str | None
    name: str
    scope: str
    root: Path
    layout_project: Layout
    layout_user: Layout
    out_dir: Path | None
    terminal_id: str | None
    config_file: Path | None
    source_file: Path | None
    source_dir: Path | None
    mechanism: str | None
    allow_project_fallback: bool


def _check_name(kind: str | None, name: str) -> None:
    if kind == "plugin" and "@" in name:
        validate_plugin_key(name)
    else:
        validate_name(name)


def _layout_for(req: Request, scope: str) -> Layout:
    return req.layout_project if scope == "project" else req.layout_user


def _read_text(path: Path | None, flag: str) -> str:
    if path is None:
        raise ToolkitError("invalid_argument", f"{flag} is required for this add")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolkitError(
            "invalid_argument", f"cannot read {flag} {path}: {exc}"
        ) from exc
    if not text.strip():
        raise ToolkitError("invalid_argument", f"{flag} {path} is empty")
    return text


def mcp_definition(config_file: Path | None, name: str) -> dict[str, Any]:
    """A server object from ``--config``: bare, or ``{"mcpServers": {...}}``."""
    text = _read_text(config_file, "--config")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolkitError("invalid_argument", f"--config is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ToolkitError("invalid_argument", "--config must be a JSON object")
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        if name not in servers:
            raise ToolkitError("invalid_argument", f"--config has no server {name!r}")
        data = servers[name]
    if not isinstance(data, dict) or not (
        isinstance(data.get("command"), str) or isinstance(data.get("url"), str)
    ):
        raise ToolkitError(
            "invalid_argument", "an MCP server needs a string 'command' or 'url'"
        )
    return data


def _check_mechanism(kind: str, requested: str | None, allowed: tuple[str, ...]) -> str:
    chosen = requested or allowed[0]
    if chosen not in allowed:
        raise ToolkitError(
            "invalid_argument",
            f"--mechanism {chosen} is not valid for {kind}; use one of {', '.join(allowed)}",
        )
    return chosen


# ----- host scope (project or user) ----------------------------------------


def _host_mcp(req: Request, layout: Layout, session: WriteSession) -> bool:
    """Change one server key. The host file is written first, the stash second.

    Host write first means a crash between the two writes can lose the stash
    entry (the pre-write backup still holds the definition), but never leaves the
    server in neither place after an enable.
    """
    path = layout.mcp_path()
    data = read_object(path)
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ToolkitError("malformed_config", f"{path} mcpServers is not an object")
    stash = read_stash(layout)
    stashed = find_stash(stash, "mcp", req.name)
    new_stash: list[dict[str, Any]] | None = None  # None: stash unchanged

    if req.action == "add":
        definition = mcp_definition(req.config_file, req.name)
        if stashed is not None:
            raise ToolkitError(
                "already_exists", f"mcp {req.name} is disabled in {layout.scope}"
            )
        if req.name in servers:
            if servers[req.name] == definition:
                return False
            raise ToolkitError(
                "already_exists",
                f"mcp {req.name} already exists with another definition",
            )
        servers[req.name] = definition
    elif req.action == "enable":
        if req.name in servers:
            return False
        if stashed is None:
            raise ToolkitError("not_found", f"no mcp {req.name} in {layout.scope}")
        servers[req.name] = stashed["definition"]
        new_stash = [s for s in stash if s is not stashed]
    elif req.action == "disable":
        if req.name not in servers:
            if stashed is None:
                raise ToolkitError("not_found", f"no mcp {req.name} in {layout.scope}")
            return False
        definition = servers.pop(req.name)
        new_stash = [
            *stash,
            {"kind": "mcp", "name": req.name, "definition": definition},
        ]
    else:  # remove
        in_live = req.name in servers
        if not in_live and stashed is None:
            return False
        servers.pop(req.name, None)
        if stashed is not None:
            new_stash = [s for s in stash if s is not stashed]
    data["mcpServers"] = servers
    write_object(path, data, session)
    if new_stash is not None:
        write_stash(layout, new_stash)
    return True


def _host_skill(req: Request, layout: Layout, session: WriteSession) -> bool:
    path = layout.skill_file(req.name)
    folder = path.parent
    stash = read_stash(layout)
    stashed = find_stash(stash, "skill", req.name)
    live = path.is_file()

    if req.action == "add":
        text = _read_text(req.source_file, "--file")
        if stashed is not None:
            raise ToolkitError(
                "already_exists", f"skill {req.name} is disabled in {layout.scope}"
            )
        if live:
            if path.read_text(encoding="utf-8") == text:
                return False
            raise ToolkitError(
                "already_exists", f"skill {req.name} already exists with other content"
            )
        write_text_atomic(path, text)
        return True
    if req.action == "enable":
        if live:
            return False
        if stashed is None:
            raise ToolkitError("not_found", f"no skill {req.name} in {layout.scope}")
        write_text_atomic(path, stashed["definition"])
        write_stash(layout, [s for s in stash if s is not stashed])
        return True
    if req.action == "disable":
        if not live:
            if stashed is None:
                raise ToolkitError(
                    "not_found", f"no skill {req.name} in {layout.scope}"
                )
            return False
        extras = [c.name for c in folder.iterdir() if c.name != "SKILL.md"]
        if extras:
            raise ToolkitError(
                "skill_has_extra_files",
                f"skill {req.name} has files besides SKILL.md ({', '.join(sorted(extras))}); "
                "only single-file skills can be disabled",
            )
        text = path.read_text(encoding="utf-8")
        write_stash(
            layout, [*stash, {"kind": "skill", "name": req.name, "definition": text}]
        )
        path.unlink()
        folder.rmdir()
        return True
    # remove
    if not live and stashed is None:
        return False
    if live:
        extras = [c.name for c in folder.iterdir() if c.name != "SKILL.md"]
        if extras:
            raise ToolkitError(
                "skill_has_extra_files",
                f"skill {req.name} has extra files; remove them by hand first",
            )
        # Copy first: the delete below is not recoverable otherwise.
        preserve_skill(layout, path, req.name)
        path.unlink()
        folder.rmdir()
    if stashed is not None:
        write_stash(layout, [s for s in stash if s is not stashed])
    return True


def _host_plugin(req: Request, layout: Layout, session: WriteSession) -> bool:
    if "@" not in req.name:
        raise ToolkitError(
            "unsupported_scope",
            "plugin folders can only be added at terminal scope (--scope terminal)",
        )
    path = layout.settings_path()
    data = read_object(path)
    toggles = data.get("enabledPlugins", {})
    if not isinstance(toggles, dict):
        raise ToolkitError(
            "malformed_config", f"{path} enabledPlugins is not an object"
        )
    key = req.name
    if req.action == "remove":
        if key not in toggles:
            return False
        toggles.pop(key)
    elif req.action in ("add", "enable"):
        if req.action == "enable" and key not in toggles:
            raise ToolkitError(
                "not_found", f"no plugin {key} in {layout.scope} settings"
            )
        if toggles.get(key) is True:
            return False
        toggles[key] = True
    else:  # disable
        if key not in toggles:
            raise ToolkitError(
                "not_found", f"no plugin {key} in {layout.scope} settings"
            )
        if toggles[key] is False:
            return False
        toggles[key] = False
    data["enabledPlugins"] = toggles
    write_object(path, data, session)
    return True


def _host_change(
    req: Request, kind: str, layout: Layout, session: WriteSession
) -> bool:
    if kind == "mcp":
        return _host_mcp(req, layout, session)
    if kind == "skill":
        return _host_skill(req, layout, session)
    return _host_plugin(req, layout, session)


def _host_item(kind: str, req: Request, scope: str) -> ToolkitItem:
    enabled = req.action in ("add", "enable")
    return ToolkitItem(kind, req.name, scope, enabled)


# ----- terminal bundle -------------------------------------------------------


def _plugin_folder_ok(source: Path) -> None:
    if not (source / ".claude-plugin" / "plugin.json").is_file():
        raise ToolkitError(
            "invalid_argument",
            f"{source} is not a plugin folder (missing .claude-plugin/plugin.json)",
        )
    refuse_links(source)


def _terminal_change(
    req: Request, kind: str, bdir: Path, manifest: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    items = manifest["items"]
    existing = find_item(manifest, kind, req.name)

    if req.action == "add":
        if kind == "mcp":
            definition: Any = mcp_definition(req.config_file, req.name)
            mechanism = _check_mechanism(
                kind, req.mechanism, PROVEN_TERMINAL_MECHANISMS["mcp"]
            )
        elif kind == "skill":
            definition = _read_text(req.source_file, "--file")
            _check_mechanism(kind, req.mechanism, (MECHANISM_ADD_DIR,))
            mechanism = MECHANISM_ADD_DIR
        elif "@" in req.name:
            definition = None
            _check_mechanism(kind, req.mechanism, (MECHANISM_SETTINGS,))
            mechanism = MECHANISM_SETTINGS
        else:
            if req.source_dir is None:
                raise ToolkitError(
                    "invalid_argument", "--dir is required for a plugin folder"
                )
            _check_mechanism(kind, req.mechanism, (MECHANISM_PLUGIN_DIR,))
            _plugin_folder_ok(req.source_dir)
            definition = None
            mechanism = MECHANISM_PLUGIN_DIR
        if existing is not None:
            if existing.get("definition") == definition:
                if existing.get("enabled"):
                    return False, existing
                existing["enabled"] = True
                return True, existing
            raise ToolkitError(
                "already_exists", f"{kind} {req.name} already exists in this terminal"
            )
        if kind == "plugin" and "@" not in req.name:
            folder = safe_target(bdir, BUNDLE_PLUGINS_DIR, req.name)
            if folder.exists():
                refuse_links(folder)
                shutil.rmtree(folder)
            folder.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(req.source_dir, folder)
        entry: dict[str, Any] = {
            "kind": kind,
            "name": req.name,
            "enabled": True,
            "mechanism": mechanism,
        }
        if definition is not None:
            entry["definition"] = definition
        items.append(entry)
        return True, entry

    if existing is None:
        raise ToolkitError("not_found", f"no {kind} {req.name} in this terminal")
    if req.action == "remove":
        items.remove(existing)
        return True, existing
    want = req.action == "enable"
    if bool(existing.get("enabled")) == want:
        return False, existing
    existing["enabled"] = want
    return True, existing


def _terminal_item(entry: dict[str, Any], terminal_id: str) -> ToolkitItem:
    return ToolkitItem(
        kind=entry["kind"],
        name=entry["name"],
        scope="terminal",
        enabled=bool(entry.get("enabled")),
        mechanism=mechanism_for(entry["kind"], entry["name"], entry.get("mechanism")),
        terminal_id=terminal_id,
    )


def _resolve_scope_and_kind(req: Request) -> tuple[str, str]:
    """For non-add actions: the scope the item lives in and its kind.

    Terminal requests resolve inside the bundle first. A host-only match is a
    proven-scope miss: refused unless the caller opted into the project fallback.
    """
    if req.scope == "terminal":
        assert req.out_dir is not None and req.terminal_id is not None
        manifest = load_manifest(bundle_dir(req.out_dir, req.terminal_id))
        matches = [
            i
            for i in manifest["items"]
            if i["name"] == req.name and (req.kind is None or i["kind"] == req.kind)
        ]
        if len(matches) == 1:
            return "terminal", matches[0]["kind"]
        if len(matches) > 1:
            raise ToolkitError(
                "ambiguous_item", f"several kinds named {req.name}; pass --kind"
            )
        host_matches = [
            i
            for i in host_items(req.layout_project) + host_items(req.layout_user)
            if i.name == req.name and (req.kind is None or i.kind == req.kind)
        ]
        if not host_matches:
            raise ToolkitError("not_found", f"no item {req.name} for this terminal")
        if not req.allow_project_fallback:
            raise ToolkitError(
                "scope_not_proven",
                f"{req.name} exists in project or user config; a per-terminal change is "
                f"not proven for it. {SCOPE_PROVEN_HINT}",
            )
        return host_matches[0].scope, host_matches[0].kind
    layout = _layout_for(req, req.scope)
    matches = [
        i
        for i in host_items(layout)
        if i.name == req.name and (req.kind is None or i.kind == req.kind)
    ]
    if not matches:
        raise ToolkitError("not_found", f"no item {req.name} in {req.scope} scope")
    if len(matches) > 1:
        raise ToolkitError(
            "ambiguous_item", f"several kinds named {req.name}; pass --kind"
        )
    return req.scope, matches[0].kind


def mutate(req: Request) -> dict[str, Any]:
    """Run one add/remove/enable/disable. Returns the toolkit-mutate payload."""
    if req.action not in ACTIONS:
        raise ToolkitError("usage", f"unknown action {req.action!r}")
    _check_name(req.kind, req.name)
    if req.action == "add" and req.kind is None:
        raise ToolkitError("invalid_argument", "add requires --kind mcp|skill|plugin")
    if req.scope == "terminal":
        if req.terminal_id is None:
            raise ToolkitError(
                "terminal_required", "--scope terminal needs --terminal ID"
            )
        if req.out_dir is None:
            raise ToolkitError(
                "out_dir_required", "--scope terminal needs --out-dir DIR"
            )
        check_out_dir(req.out_dir, req.root)

    if req.action == "add":
        target_scope = req.scope
        kind = req.kind
    else:
        target_scope, kind = _resolve_scope_and_kind(req)
    if kind is None:
        raise ToolkitError("invalid_argument", "could not determine the item kind")
    fallback = req.scope == "terminal" and target_scope != "terminal"

    if target_scope == "terminal":
        assert req.out_dir is not None and req.terminal_id is not None
        bdir = bundle_dir(req.out_dir, req.terminal_id)
        manifest = load_manifest(bdir)
        changed, entry = _terminal_change(req, kind, bdir, manifest)
        if changed:
            save(bdir, manifest)
        item = _terminal_item(entry, req.terminal_id)
        if req.action == "remove":
            item = ToolkitItem(
                kind, req.name, "terminal", False, item.mechanism, req.terminal_id
            )
        return {
            "action": req.action,
            "changed": changed,
            "item": item.to_dict(),
            "launch_args": launch_args(bdir, manifest),
            "restart_required": changed,
            "backup_path": None,
        }

    layout = _layout_for(req, target_scope)
    session = WriteSession(backup_dir=layout.host_backup_dir())
    changed = _host_change(req, kind, layout, session)
    item = _host_item(kind, req, target_scope)
    if fallback:
        item = fall_back(item, "terminal")
    return {
        "action": req.action,
        "changed": changed,
        "item": item.to_dict(),
        "launch_args": [],
        "restart_required": changed,
        "backup_path": session.backup_path,
    }
