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

from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    SEED_MARKETPLACES,
    EquipError,
    EquipmentManifest,
    InstallPlan,
    MarketplaceCatalog,
    PluginEntry,
    SourceError,
    available_tools,
    build_install_plan,
    capability_gaps,
    detect_stack,
    fetch_catalog,
    list_skills,
    match_candidates,
    parse_catalog,
    read_manifest,
    search_github,
)
from dummyindex.context.domains.equip.plugins.sources import (
    CATALOG_PATH,
    default_runner,
)

from ..common import resolve_context_root
from .common import pull_bool_flag, pull_flag_value, pull_root
from .plugin_state import catalog_from_local_clone, declared_marketplaces

_RUNNER = default_runner
_SETTINGS_REL = ".claude/settings.json"
_VALID_SCOPES = frozenset({"project", "local", "user"})

# A trusted seed's marketplace name belongs to its specific repo. Any catalog
# (seed or GitHub-discovered) that claims one of these names from a *different*
# repo is an impersonation attempt and is dropped — so an attacker cannot
# publish a marketplace.json named "claude-plugins-official" and ride the
# official identity. Trust itself never comes from the JSON; it comes from the
# seed list / discovery path, so the trust flag is independently unspoofable.
_RESERVED_NAME_REPOS: dict[str, str] = {
    seed.name: seed.repo for seed in SEED_MARKETPLACES if seed.trusted
}


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


def _collection_catalog(
    repo: str, name: str, *, trusted: bool
) -> MarketplaceCatalog | None:
    """Synthesise a catalog for a loose collection repo (no marketplace.json).

    Enumerates the repo's skill dirs (:func:`list_skills`) and turns each
    ``SKILL.md`` into a vendorable :class:`PluginEntry`. Returns ``None`` when the
    repo ships no skills (or ``gh`` is unreachable). An undecodable listing
    (:class:`SourceError`) degrades to ``None`` too — a collection we cannot
    enumerate simply contributes no candidates rather than crashing the whole
    discover/install run. ``is_collection=True`` is what routes a later ``install``
    of one of these into the VENDOR mechanism.
    """
    try:
        refs = list_skills(repo, runner=_RUNNER)
    except SourceError as exc:
        print(f"warning: could not enumerate skills in {repo}: {exc}", file=sys.stderr)
        return None
    if not refs:
        return None
    plugins = tuple(
        PluginEntry(name=ref.name, description=f"skill from {repo}") for ref in refs
    )
    return MarketplaceCatalog(
        name=name, repo=repo, plugins=plugins, trusted=trusted, is_collection=True
    )


def _collect_catalogs(
    query: str | None = None,
    *,
    extra_repos: tuple[str, ...] = (),
    project_root: Path | None = None,
) -> tuple[list[MarketplaceCatalog], str | None]:
    """Assemble the candidate marketplace universe, in priority order.

    1. The non-collection seed marketplaces.
    2. Repos named explicitly via ``extra_repos`` (``--repo``) — the user's
       explicit intent wins name collisions against everything below.
    3. Marketplaces this machine already declares (project/user settings
       ``extraKnownMarketplaces`` + ``known_marketplaces.json``) — resolved
       from their on-disk clone when present, else fetched. This is what lets
       ``install`` find a marketplace Claude Code already knows.
    4. When a ``query`` is given, GitHub-discovered marketplaces.

    Discovered, explicit, and declared repos are always UNTRUSTED. Each catalog
    carries its trust flag. Returns ``(catalogs, warning_or_None)``; a missing
    ``gh`` yields only the locally-readable declared catalogs + a warning.
    """
    catalogs: list[MarketplaceCatalog] = []
    seen_repos: set[str] = set()
    seen_names: set[str] = set()

    def _admit(cat: MarketplaceCatalog) -> None:
        """Add ``cat`` unless its name impersonates a reserved identity or
        duplicates an already-registered (higher-priority) name."""
        reserved_repo = _RESERVED_NAME_REPOS.get(cat.name)
        if reserved_repo is not None and cat.repo != reserved_repo:
            print(
                f"warning: skipping {cat.repo}: claims reserved marketplace name "
                f"{cat.name!r} (belongs to {reserved_repo})",
                file=sys.stderr,
            )
            return
        if cat.name in seen_names:
            print(
                f"warning: skipping {cat.repo}: marketplace name {cat.name!r} "
                "already registered by a higher-priority source",
                file=sys.stderr,
            )
            return
        seen_names.add(cat.name)
        catalogs.append(cat)

    declared = declared_marketplaces(project_root) if project_root is not None else ()

    if not available_tools(runner=_RUNNER).gh:
        # No network path — local marketplace clones are still readable.
        for dm in declared:
            cat = catalog_from_local_clone(dm)
            if cat is not None:
                _admit(cat)
        return (
            catalogs,
            "gh CLI not found — install it and run `gh auth login` to discover plugins",
        )

    # Seeds first (so a seed always wins its name over a discovered collision).
    # A collection seed (no marketplace.json) is enumerated into a synthetic
    # catalog whose plugins are its vendorable skills; every other seed fetches
    # its marketplace.json.
    for seed in SEED_MARKETPLACES:
        seen_repos.add(seed.repo)
        cat = (
            _collection_catalog(seed.repo, seed.name, trusted=seed.trusted)
            if seed.is_collection
            else _fetch_one(seed.repo, trusted=seed.trusted)
        )
        if cat is not None:
            _admit(cat)
    # Explicitly named marketplaces (--repo) bypass discovery for low-profile
    # repos `gh search` won't surface, and are admitted BEFORE search results so
    # the user's explicit repo wins name collisions. Still UNTRUSTED — a
    # hand-typed repo is not a vetted seed, so its declared surfaces stay
    # attacker-controlled (approval gates) and reserved-name impersonation is
    # still rejected via `_admit`.
    for repo in extra_repos:
        if repo in seen_repos:
            continue
        seen_repos.add(repo)
        cat = _fetch_one(repo, trusted=False)
        if cat is not None:
            _admit(cat)
        else:
            # The user named this repo explicitly — a fetch miss is worth saying
            # out loud (vs. silently skipping a speculative search result), so a
            # transient gh API error / private repo isn't mistaken for "not found".
            print(
                f"warning: --repo {repo}: no readable "
                f"{CATALOG_PATH} (absent, private, or gh API error)",
                file=sys.stderr,
            )
    # Locally-declared marketplaces: prefer the on-disk clone (no network),
    # fall back to fetching the declared repo.
    for dm in declared:
        if dm.repo in seen_repos:
            continue
        seen_repos.add(dm.repo)
        cat = catalog_from_local_clone(dm) or _fetch_one(dm.repo, trusted=False)
        if cat is not None:
            _admit(cat)
    if query:
        # GitHub-discovered marketplaces beyond the seeds are always UNTRUSTED.
        search = search_github(query, runner=_RUNNER)
        if search.degraded:
            print(
                "warning: GitHub code search unavailable "
                f"({search.reason or 'unknown'}) — results from repo search, "
                "may differ between runs",
                file=sys.stderr,
            )
        for repo in search.repos:
            if repo in seen_repos:
                continue
            seen_repos.add(repo)
            cat = _fetch_one(repo, trusted=False)
            if cat is not None:
                _admit(cat)
    return catalogs, None


def _parse_repo_flag(repo: str | None) -> tuple[str, ...] | None:
    """Validate a ``--repo`` value. Returns the ``extra_repos`` tuple (empty when
    absent), or ``None`` when the value is malformed (caller errors with rc 2).
    Accepts both ``owner/name`` and full GitHub URLs."""
    if repo is None:
        return ()
    normalized = _normalize_repo(repo)
    if normalized is None:
        return None
    return (normalized,)


def _normalize_repo(repo: str) -> str | None:
    """Normalize ``https://github.com/owner/name(.git)`` → ``owner/name``."""
    candidate = repo.strip()
    lowered = candidate.lower()
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if lowered.startswith(prefix):
            candidate = candidate[len(prefix) :]
            break
    candidate = candidate.rstrip("/")
    candidate = candidate.removesuffix(".git")
    owner, _, name = candidate.partition("/")
    if not owner or not name or "/" in name:
        return None
    return f"{owner}/{name}"


def _needed_caps(project_root: Path) -> tuple[str, ...]:
    """Auto-match signal: the real capability gap — what the detected stack
    requires minus what ``equipment.json`` already covers (``capability_gaps``).

    Manifest read failures (a corrupt/too-new manifest) degrade to an empty
    manifest so a bare ``discover`` still surfaces the full stack gap rather than
    crashing — discovery is read-only and must never hard-fail here.
    """
    context_dir = project_root / ".context"
    profile = detect_stack(context_dir)
    try:
        manifest = read_manifest(context_dir)
    except EquipError as exc:
        # Degrade but say so (mirrors `_record_native`'s EquipError handling):
        # a corrupt/too-new manifest leaves discover blind to already-covered
        # capabilities, so the gap is computed from the stack alone — never a
        # silent swallow.
        print(
            f"warning: equipment.json unreadable ({exc}); capability gap "
            "computed from the stack only",
            file=sys.stderr,
        )
        manifest = EquipmentManifest(schema_version=SCHEMA_VERSION, items=())
    return capability_gaps(profile=profile, manifest=manifest)


def _parse_root(rest: list[str]) -> tuple[Path, list[str]]:
    explicit_root, rest = pull_root(rest)
    return resolve_context_root(Path("."), explicit_root=explicit_root), rest


# ----- verb: discover -------------------------------------------------------


def run_discover(rest: list[str]) -> int:
    as_json, rest = pull_bool_flag(rest, "json")
    repo, rest = pull_flag_value(rest, "repo")
    extra_repos = _parse_repo_flag(repo)
    if extra_repos is None:
        print(f"error: --repo must be <owner>/<name>, got {repo!r}", file=sys.stderr)
        return 2
    project_root, rest = _parse_root(rest)
    bad = [a for a in rest if a.startswith("--")]
    if bad:
        print(
            f"error: unknown argument(s) for `equip discover`: {bad}", file=sys.stderr
        )
        return 2
    query = " ".join(rest).strip() or None
    catalogs, warn = _collect_catalogs(
        query, extra_repos=extra_repos, project_root=project_root
    )
    if warn:
        print(f"warning: {warn}", file=sys.stderr)
    if extra_repos and not as_json:
        # An explicit --repo whose catalog never made it in deserves a STDOUT
        # answer, not just the stderr warning (the canvas-to-code dead end).
        admitted = {c.repo for c in catalogs}
        for named in extra_repos:
            if named not in admitted:
                print(
                    f"note: --repo {named}: no plugins surfaced (catalog missing or unreadable)"
                )
    needed = () if query else _needed_caps(project_root)
    candidates = match_candidates(
        tuple(catalogs),
        needed_caps=needed,
        query=query,
        force_repos=frozenset(extra_repos),
    )
    return _print_plan(
        build_install_plan(candidates),
        as_json=as_json,
        force_repos=frozenset(extra_repos),
    )


def _print_plan(
    plan: InstallPlan, *, as_json: bool, force_repos: frozenset[str] = frozenset()
) -> int:
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
        if not force_repos:
            print(
                "Tip: if the plugin lives in a low-profile repo, add --repo <owner>/<name>."
            )
        return 0
    print("equip discover (dry-run — nothing written):")
    for pi in plan.installs:
        c = pi.candidate
        flag = "  ⚠ requires --yes" if pi.requires_approval else ""
        from_repo = f"  (from --repo {c.repo})" if c.repo in force_repos else ""
        surfaces = ", ".join(pi.blast.surfaces) if pi.blast.surfaces else "none"
        runs = "runs code" if pi.blast.runs_code else "inert"
        print(
            f"  {pi.mechanism.value:6} {c.plugin.name}@{c.marketplace}  "
            f"covers: {', '.join(c.capabilities) or '-'}{from_repo}"
        )
        print(
            f"         blast radius: {surfaces} ({runs}; {pi.blast.tier.value}){flag}"
        )
    print("\nInstall one with: equip install <plugin>@<marketplace> [--yes]")
    if not force_repos:
        print("A low-profile repo `gh search` misses: add --repo <owner>/<name>.")
    return 0
