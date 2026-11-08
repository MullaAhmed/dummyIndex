"""Two-step install: preview (nothing written) and apply (only if the hash matches).

Preview resolves the source to a commit SHA, fetches the content at that SHA,
builds the exact commands, the blast radius and trust, and hashes the canonical
preview with SHA-256. Apply rebuilds the same preview and refuses with
``stale_plan_hash`` unless the hash matches, so the user confirms exactly what
runs. Installs never enable anything. Skills and MCP servers are stored as
disabled entries in the stash; plugins are installed and then disabled.

Delegates to ``context/domains/equip/plugins``: ``sources`` for the GitHub reads
(pinned by SHA), ``marketplace`` and ``discover`` for the plugin catalog,
``install_plan`` and ``blast_radius`` for the plugin blast radius.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..equip.enums import PluginSurface
from ..equip.errors import EquipError
from ..equip.plugins.blast_radius import analyze_blast_radius
from ..equip.plugins.discover import Candidate, capabilities_for
from ..equip.plugins.install_plan import build_install_plan
from ..equip.plugins.marketplace import PluginEntry, parse_catalog
from ..equip.plugins.sources import (
    CATALOG_PATH,
    Runner,
    RunResult,
    default_runner,
    fetch_file,
)
from .constants import INSTALL_SCOPES, TRUSTED_REPOS
from .errors import ToolkitError
from .host import (
    Layout,
    project_layout,
    read_object,
    read_stash,
    user_layout,
    write_stash,
)
from .paths import validate_name
from .source import ParsedSource, parse_source

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Plan:
    preview: dict[str, Any]
    kind: str
    name: str
    sha: str
    scope: str
    layout: Layout
    content: Any = field(default=None)
    commands: tuple[tuple[str, ...], ...] = ()


def _digest(obj: dict[str, Any]) -> str:
    canonical = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_sha(parsed: ParsedSource, runner: Runner) -> str:
    target = quote(parsed.git_ref or "HEAD", safe="/")
    res = runner(["gh", "api", f"repos/{parsed.repo}/commits/{target}"])
    if res.returncode != 0:
        raise ToolkitError(
            "source_unreachable",
            f"could not resolve {parsed.repo}@{parsed.git_ref or 'HEAD'}: "
            f"{(res.stderr or '').strip() or 'gh api failed'}",
        )
    try:
        obj = json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        raise ToolkitError(
            "source_unreachable", f"unexpected commit response: {exc}"
        ) from exc
    sha = obj.get("sha") if isinstance(obj, dict) else None
    if not isinstance(sha, str) or not _SHA_RE.match(sha):
        raise ToolkitError(
            "source_unreachable", f"{parsed.repo} did not return a commit SHA"
        )
    return sha


def _fetch(parsed: ParsedSource, path: str, sha: str, runner: Runner) -> str:
    try:
        text = fetch_file(parsed.repo, path, ref=sha, runner=runner)
    except EquipError as exc:
        raise ToolkitError("source_unreachable", str(exc)) from exc
    if text is None:
        raise ToolkitError(
            "source_not_found", f"{path} was not found in {parsed.repo} at {sha[:12]}"
        )
    return text


def _contents_argv(repo: str, path: str, sha: str) -> tuple[str, ...]:
    return ("gh", "api", f"repos/{repo}/contents/{path}?ref={sha}")


def _skill_plan(
    parsed: ParsedSource, sha: str, runner: Runner
) -> tuple[str, str, Any, tuple[str, ...]]:
    if not parsed.subpath:
        raise ToolkitError(
            "invalid_source", "a skill source needs a folder path after the repo"
        )
    last = parsed.subpath.split("/")[-1]
    if last == "SKILL.md":
        path = parsed.subpath
        name = (
            parsed.subpath.split("/")[-2]
            if "/" in parsed.subpath
            else parsed.repo.split("/")[1]
        )
    else:
        path = f"{parsed.subpath}/SKILL.md"
        name = last
    validate_name(name)
    text = _fetch(parsed, path, sha, runner)
    if not text.strip():
        raise ToolkitError("source_not_found", f"{path} is empty")
    return name, "skill", text, (_contents_argv(parsed.repo, path, sha),)


def _mcp_definition(name: str, data: Any) -> dict[str, Any]:
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if isinstance(servers, dict):
        if name not in servers and len(servers) != 1:
            raise ToolkitError("invalid_source", f"mcp file has no server {name!r}")
        data = servers.get(name, next(iter(servers.values())))
    if not isinstance(data, dict) or not (
        isinstance(data.get("command"), str) or isinstance(data.get("url"), str)
    ):
        raise ToolkitError(
            "invalid_source", "an MCP server needs a string 'command' or 'url'"
        )
    return data


def _mcp_plan(
    parsed: ParsedSource, sha: str, runner: Runner
) -> tuple[str, str, Any, tuple[str, ...]]:
    if not parsed.subpath.endswith(".json"):
        raise ToolkitError("invalid_source", "an mcp source must point at a .json file")
    stem = parsed.subpath.split("/")[-1][: -len(".json")]
    name = validate_name(stem)
    text = _fetch(parsed, parsed.subpath, sha, runner)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolkitError(
            "invalid_source", f"{parsed.subpath} is not JSON: {exc}"
        ) from exc
    definition = _mcp_definition(name, data)
    return name, "mcp", definition, (_contents_argv(parsed.repo, parsed.subpath, sha),)


def _plugin_plan(
    parsed: ParsedSource, sha: str, runner: Runner
) -> tuple[str, str, Any, tuple[str, ...], PluginEntry, str, bool]:
    plugin = parsed.subpath
    if not plugin or "/" in plugin:
        raise ToolkitError(
            "invalid_source", "a plugin source names one plugin after the repo"
        )
    validate_name(plugin)
    text = _fetch(parsed, CATALOG_PATH, sha, runner)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolkitError("source_unreachable", f"catalog is not JSON: {exc}") from exc
    trusted = parsed.repo in TRUSTED_REPOS
    try:
        catalog = parse_catalog(data, repo=parsed.repo, trusted=trusted)
    except EquipError as exc:
        raise ToolkitError("source_unreachable", f"catalog invalid: {exc}") from exc
    entry = next((p for p in catalog.plugins if p.name == plugin), None)
    if entry is None:
        raise ToolkitError(
            "source_not_found", f"plugin {plugin!r} is not in the catalog"
        )
    key = f"{plugin}@{catalog.name}"
    argv_install = (
        "claude",
        "plugin",
        "install",
        key,
        "--marketplace",
        parsed.repo,
        "--scope",
        "user",
        "--json",
    )
    argv_disable = ("claude", "plugin", "disable", key, "--scope", "user", "--json")
    return (
        key,
        "plugin",
        None,
        (argv_install, argv_disable),
        entry,
        catalog.name,
        trusted,
    )


def _stash_display(layout: Layout) -> str:
    path = layout.stash_path()
    if layout.scope == "project":
        return ".context/toolkit/disabled.json"
    return str(path)


def build_plan(
    kind: str,
    source: str,
    scope: str,
    *,
    root: Path,
    home: Path,
    runner: Runner = default_runner,
) -> Plan:
    if kind not in ("mcp", "skill", "plugin"):
        raise ToolkitError("invalid_argument", "--kind must be mcp, skill or plugin")
    if scope not in INSTALL_SCOPES:
        raise ToolkitError(
            "unsupported_scope",
            "install --scope must be project or user (terminal is not an install scope)",
        )
    if scope == "project" and kind == "plugin":
        raise ToolkitError(
            "unsupported_scope",
            "plugin install is user-scope only (claude plugin install --scope user)",
        )
    parsed = parse_source(source)
    layout = project_layout(root) if scope == "project" else user_layout(home)
    sha = _resolve_sha(parsed, runner)
    warnings: list[str] = []
    trusted = parsed.repo in TRUSTED_REPOS

    if kind == "plugin":
        name, _, content, commands, entry, _market, trusted = _plugin_plan(
            parsed, sha, runner
        )
        blast = analyze_blast_radius(entry, trusted=trusted)
        planned = build_install_plan(
            (
                Candidate(
                    plugin=entry,
                    marketplace=_market,
                    repo=parsed.repo,
                    trusted=trusted,
                    is_collection=False,
                    capabilities=capabilities_for(entry),
                    score=0,
                ),
            )
        ).installs[0]
        writes = ["~/.claude/plugins", "~/.claude/settings.json"]
        blast_scope = "user"
        summary = (
            f"Installs plugin {name} for every project on this machine. "
            "Not enabled by this step."
        )
        requires_approval = planned.requires_approval
        warnings.append(
            "claude plugin install takes the marketplace repo, not the commit SHA; "
            "the resolved SHA is recorded but the CLI does not pin to it (unverified)."
        )
    else:
        if kind == "skill":
            name, _, content, commands = _skill_plan(parsed, sha, runner)
            surfaces: tuple[str, ...] = ()
        else:
            name, _, content, commands = _mcp_plan(parsed, sha, runner)
            surfaces = (PluginSurface.MCP.value,) if "command" in content else ()
        entry = PluginEntry(name=name, declared_surfaces=surfaces)
        blast = analyze_blast_radius(entry, trusted=trusted)
        requires_approval = not trusted
        writes = [_stash_display(layout)]
        blast_scope = scope
        summary = (
            f"Stores {kind} {name} as disabled in {scope} scope. "
            "Nothing is enabled until `toolkit enable`."
        )

    preview: dict[str, Any] = {
        "kind": kind,
        "name": name,
        "source": {"ref": source, "scheme": parsed.scheme},
        "resolved": {"sha": sha},
        "commands": [list(c) for c in commands],
        "blast_radius": {
            "scope": blast_scope,
            "writes": writes,
            "summary": summary,
            "runs_code": blast.runs_code,
            "surfaces": list(blast.surfaces),
        },
        "trust": {
            "requires_confirmation": True,
            "scheme_allowed": True,
            "trusted_repo": trusted,
            "requires_approval": requires_approval,
        },
        "warnings": warnings,
    }
    preview["plan_hash"] = _digest(preview)
    return Plan(
        preview=preview,
        kind=kind,
        name=name,
        sha=sha,
        scope=scope,
        layout=layout,
        content=content,
        commands=commands,
    )


def preview(
    kind: str,
    source: str,
    scope: str,
    *,
    root: Path,
    home: Path,
    runner: Runner = default_runner,
) -> dict[str, Any]:
    return build_plan(kind, source, scope, root=root, home=home, runner=runner).preview


def _store_disabled(plan: Plan) -> None:
    layout = plan.layout
    stash = read_stash(layout)
    if any(s.get("kind") == plan.kind and s.get("name") == plan.name for s in stash):
        raise ToolkitError(
            "already_exists", f"{plan.kind} {plan.name} is already stashed"
        )
    if plan.kind == "skill":
        if layout.skill_file(plan.name).is_file():
            raise ToolkitError("already_exists", f"skill {plan.name} already exists")
    else:
        servers = read_object(layout.mcp_path()).get("mcpServers", {})
        if isinstance(servers, dict) and plan.name in servers:
            raise ToolkitError("already_exists", f"mcp {plan.name} already exists")
    write_stash(
        layout,
        [*stash, {"kind": plan.kind, "name": plan.name, "definition": plan.content}],
    )


def _run_plugin_commands(plan: Plan, runner: Runner) -> None:
    for argv in plan.commands:
        res: RunResult = runner(list(argv))
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "").strip()
            raise ToolkitError(
                "install_failed",
                f"{' '.join(argv[:3])} failed (exit {res.returncode}): {detail[:500]}",
            )


def apply(
    kind: str,
    source: str,
    scope: str,
    plan_hash: str,
    *,
    root: Path,
    home: Path,
    runner: Runner = default_runner,
) -> dict[str, Any]:
    """Install only if the freshly built preview hashes to ``plan_hash``."""
    plan = build_plan(kind, source, scope, root=root, home=home, runner=runner)
    if not isinstance(plan_hash, str) or plan_hash.lower() != plan.preview["plan_hash"]:
        raise ToolkitError(
            "stale_plan_hash",
            "plan_hash does not match the current preview (the source moved or the "
            "request changed); preview again and confirm the new plan",
        )
    if plan.kind == "plugin":
        _run_plugin_commands(plan, runner)
    else:
        _store_disabled(plan)
    return {
        "installed": True,
        "kind": plan.kind,
        "name": plan.name,
        "enabled": False,
        "restart_required": False,
        "plan_hash": plan.preview["plan_hash"],
        "resolved_sha": plan.sha,
    }
