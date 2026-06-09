"""``equip discover`` / ``equip install`` — the plugin-manager verbs.

Wire-only: parse flags, drive discovery I/O (:mod:`equip.sources`), call the
pure domain (match → plan), print the dry-run plan, and on ``install`` wire via
:mod:`context.claude_plugins` (native) — recording the result in the equipment
manifest. ``_RUNNER`` is module-level so tests monkeypatch a fake (no live
network). The VENDOR install path is added in a later slice.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.claude_plugins import add_marketplace, enable_plugin
from dummyindex.context.claude_settings import MalformedSettingsError
from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    SEED_MARKETPLACES,
    Candidate,
    EquipError,
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    InstallMechanism,
    InstallPlan,
    MarketplaceCatalog,
    available_tools,
    build_install_plan,
    detect_stack,
    fetch_catalog,
    match_candidates,
    parse_catalog,
    read_manifest,
    search_github,
    write_manifest,
)
from dummyindex.context.domains.equip.sources import default_runner

from ._common import _resolve_context_root
from ._equip_common import _pull_bool_flag, _pull_flag_value, _pull_root

_RUNNER = default_runner
_SETTINGS_REL = ".claude/settings.json"
_VALID_SCOPES = frozenset({"project", "local", "user"})


# ----- discovery (I/O via the module-level _RUNNER) -------------------------


def _fetch_one(repo: str, *, trusted: bool) -> MarketplaceCatalog | None:
    """Fetch + parse one repo's marketplace.json, or None if absent/undecodable."""
    try:
        data = fetch_catalog(repo, runner=_RUNNER)
    except EquipError:
        return None
    if data is None:
        return None
    try:
        return parse_catalog(data, repo=repo, trusted=trusted, is_collection=False)
    except EquipError:
        return None


def _collect_catalogs(query: str | None = None) -> tuple[list[MarketplaceCatalog], str | None]:
    """Fetch + parse the non-collection seed marketplaces, plus — when a
    ``query`` is given — any GitHub-discovered marketplaces (untrusted). Each
    catalog carries its trust flag. Returns ``(catalogs, warning_or_None)``; a
    missing ``gh`` yields an empty list + an actionable warning."""
    catalogs: list[MarketplaceCatalog] = []
    if not available_tools(runner=_RUNNER).gh:
        return catalogs, "gh CLI not found — install it and run `gh auth login` to discover plugins"
    seen_repos: set[str] = set()
    for seed in SEED_MARKETPLACES:
        if seed.is_collection:
            continue  # collections have no marketplace.json; handled by the vendor path
        cat = _fetch_one(seed.repo, trusted=seed.trusted)
        seen_repos.add(seed.repo)
        if cat is not None:
            catalogs.append(cat)
    if query:
        # GitHub-discovered marketplaces beyond the seeds are always UNTRUSTED.
        for repo in search_github(query, runner=_RUNNER):
            if repo in seen_repos:
                continue
            seen_repos.add(repo)
            cat = _fetch_one(repo, trusted=False)
            if cat is not None:
                catalogs.append(cat)
    return catalogs, None


def _needed_caps(project_root: Path) -> tuple[str, ...]:
    """Auto-match signal from the detected stack (kept deliberately simple — a
    richer gap analysis against the existing manifest is a fast-follow)."""
    profile = detect_stack(project_root / ".context")
    caps: list[str] = []
    if profile.test_runner:
        caps.append("test")
    if profile.label and profile.label != "generic":
        caps.append("implement")
    return tuple(caps)


def _parse_root(rest: list[str]) -> tuple[Path, list[str]]:
    explicit_root, rest = _pull_root(rest)
    return _resolve_context_root(Path("."), explicit_root=explicit_root), rest


# ----- verb: discover -------------------------------------------------------


def _verb_discover(rest: list[str]) -> int:
    as_json, rest = _pull_bool_flag(rest, "json")
    project_root, rest = _parse_root(rest)
    bad = [a for a in rest if a.startswith("--")]
    if bad:
        print(f"error: unknown argument(s) for `equip discover`: {bad}", file=sys.stderr)
        return 2
    query = " ".join(rest).strip() or None
    catalogs, warn = _collect_catalogs(query)
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    needed = () if query else _needed_caps(project_root)
    candidates = match_candidates(tuple(catalogs), needed_caps=needed, query=query)
    return _print_plan(build_install_plan(candidates), as_json=as_json)


def _print_plan(plan: InstallPlan, *, as_json: bool) -> int:
    if as_json:
        print(
            json.dumps(
                {
                    "installs": [
                        {
                            "plugin": pi.candidate.plugin.name,
                            "marketplace": pi.candidate.marketplace,
                            "mechanism": pi.mechanism.value,
                            "runs_code": pi.blast.runs_code,
                            "surfaces": list(pi.blast.surfaces),
                            "tier": pi.blast.tier.value,
                            "requires_approval": pi.requires_approval,
                            "capabilities": list(pi.candidate.capabilities),
                        }
                        for pi in plan.installs
                    ]
                },
                indent=2,
            )
        )
        return 0
    if not plan.installs:
        print("equip discover: no matching plugins found.")
        return 0
    print("equip discover (dry-run — nothing written):")
    for pi in plan.installs:
        c = pi.candidate
        flag = "  ⚠ requires --yes" if pi.requires_approval else ""
        surfaces = ", ".join(pi.blast.surfaces) if pi.blast.surfaces else "none"
        runs = "runs code" if pi.blast.runs_code else "inert"
        print(
            f"  {pi.mechanism.value:6} {c.plugin.name}@{c.marketplace}  "
            f"covers: {', '.join(c.capabilities) or '-'}"
        )
        print(f"         blast radius: {surfaces} ({runs}; {pi.blast.tier.value}){flag}")
    print("\nInstall one with: equip install <plugin>@<marketplace> [--yes]")
    return 0


# ----- verb: install --------------------------------------------------------


def _settings_path_for_scope(project_root: Path, scope: str | None) -> Path:
    if scope == "local":
        return project_root / ".claude" / "settings.local.json"
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    return project_root / ".claude" / "settings.json"  # project (default)


def _verb_install(rest: list[str]) -> int:
    yes, rest = _pull_bool_flag(rest, "yes")
    scope, rest = _pull_flag_value(rest, "scope")
    if scope is not None and scope not in _VALID_SCOPES:
        print(f"error: --scope must be project|local|user, got {scope!r}", file=sys.stderr)
        return 2
    project_root, rest = _parse_root(rest)
    target = next((a for a in rest if "@" in a), None)
    if target is None:
        print("error: `equip install` requires <plugin>@<marketplace>", file=sys.stderr)
        return 2
    plugin_name, _, marketplace = target.partition("@")
    if not plugin_name or not marketplace:
        print("error: target must be <plugin>@<marketplace>", file=sys.stderr)
        return 2

    catalogs, warn = _collect_catalogs(plugin_name)
    if warn:
        print(f"error: {warn}", file=sys.stderr)
        return 1
    candidates = match_candidates(tuple(catalogs), query=plugin_name)
    chosen = next(
        (c for c in candidates if c.plugin.name == plugin_name and c.marketplace == marketplace),
        None,
    )
    if chosen is None:
        print(f"error: {target} not found in known marketplaces", file=sys.stderr)
        return 1

    pi = build_install_plan((chosen,)).installs[0]
    if pi.requires_approval and not yes:
        print(
            f"error: {target} runs code from an untrusted source "
            f"(surfaces: {', '.join(pi.blast.surfaces)}). Re-run with --yes to approve.",
            file=sys.stderr,
        )
        return 1

    settings = _settings_path_for_scope(project_root, scope)
    try:
        add_marketplace(settings, name=chosen.marketplace, repo=chosen.repo, ref=chosen.plugin.version)
        enable_plugin(settings, plugin=plugin_name, marketplace=marketplace)
    except (MalformedSettingsError, OSError) as exc:
        print(f"error: could not wire {target}: {exc}", file=sys.stderr)
        return 1

    # Record only in-repo scopes in the (committed) project manifest. A
    # user-scope install lives in ~/.claude and is personal — tracking it here
    # would leak an absolute home path into a shared ledger and report a false
    # MISSING from any other checkout, so it is left to native `claude plugin`.
    if scope in (None, "project", "local"):
        settings_rel = settings.relative_to(project_root).as_posix()
        try:
            _record_native(project_root, chosen, settings_rel=settings_rel)
        except EquipError as exc:
            print(f"warning: {target} wired, but manifest not updated: {exc}", file=sys.stderr)
    print(f"equip install: enabled {target} (native) -> {settings}")
    return 0


def _record_native(project_root: Path, chosen: Candidate, *, settings_rel: str) -> None:
    context_dir = project_root / ".context"
    prior = read_manifest(context_dir)
    name = f"{chosen.plugin.name}@{chosen.marketplace}"
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=settings_rel,
        source=EquipmentSource.MARKETPLACE,
        capabilities=chosen.capabilities,
        marketplace=chosen.marketplace,
        origin_repo=chosen.repo,
        origin_ref=chosen.plugin.version,
        mechanism=InstallMechanism.NATIVE.value,
    )
    items = tuple(i for i in prior.items if i.name != name) + (item,)
    write_manifest(context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=items))
