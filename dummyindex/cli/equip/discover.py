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
from dummyindex.context.claude_settings import MalformedSettingsError, load_settings
from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    SEED_MARKETPLACES,
    Candidate,
    Capability,
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
    capabilities_for,
    detect_stack,
    fetch_catalog,
    match_candidates,
    parse_catalog,
    read_manifest,
    search_github,
    write_manifest,
)
from dummyindex.context.domains.equip.plugins.sources import CATALOG_PATH, default_runner

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
        return catalogs, "gh CLI not found — install it and run `gh auth login` to discover plugins"

    # Seeds first (so a seed always wins its name over a discovered collision).
    for seed in SEED_MARKETPLACES:
        if seed.is_collection:
            continue  # collections have no marketplace.json; handled by the vendor path
        seen_repos.add(seed.repo)
        cat = _fetch_one(seed.repo, trusted=seed.trusted)
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
            candidate = candidate[len(prefix):]
            break
    candidate = candidate.rstrip("/")
    candidate = candidate.removesuffix(".git")
    owner, _, name = candidate.partition("/")
    if not owner or not name or "/" in name:
        return None
    return f"{owner}/{name}"


def _validate_usage_doc(
    project_root: Path, usage_doc: str | None, skip: bool
) -> tuple[str | None, int | None]:
    """Resolve the mandatory usage-playbook flags for a plugin install.

    Returns ``(recorded_path_or_None, error_rc_or_None)``: a repo-relative POSIX
    path to record in ``grounded_in`` (or ``None`` when skipped), and an exit
    code to return immediately on error (or ``None`` to proceed). An absolute
    path outside the repo is recorded as-is with a warning — it won't travel
    with the committed manifest.
    """
    if usage_doc is not None and skip:
        print(
            "error: pass either --usage-doc <path> or --skip-usage-doc, not both",
            file=sys.stderr,
        )
        return None, 2
    if usage_doc is None and not skip:
        print(
            "error: a plugin install needs a usage playbook — the /dummyindex-equip "
            "council writes one, or pass --usage-doc <path> (or --skip-usage-doc to "
            "opt out).",
            file=sys.stderr,
        )
        return None, 2
    if skip:
        return None, None
    doc = Path(usage_doc)  # usage_doc is not None here
    if not doc.is_absolute():
        doc = project_root / doc
    if not doc.is_file():
        print(f"error: --usage-doc {usage_doc}: file not found", file=sys.stderr)
        return None, 1
    resolved = doc.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix(), None
    except ValueError:
        print(
            f"warning: --usage-doc {resolved} is outside the repo; recording an "
            "absolute path",
            file=sys.stderr,
        )
        return str(resolved), None


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
        print(f"error: unknown argument(s) for `equip discover`: {bad}", file=sys.stderr)
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
                print(f"note: --repo {named}: no plugins surfaced (catalog missing or unreadable)")
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
            print("Tip: if the plugin lives in a low-profile repo, add --repo <owner>/<name>.")
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
        print(f"         blast radius: {surfaces} ({runs}; {pi.blast.tier.value}){flag}")
    print("\nInstall one with: equip install <plugin>@<marketplace> [--yes]")
    if not force_repos:
        print("A low-profile repo `gh search` misses: add --repo <owner>/<name>.")
    return 0


# ----- verb: install --------------------------------------------------------


def _settings_path_for_scope(project_root: Path, scope: str | None) -> Path:
    if scope == "local":
        return project_root / ".claude" / "settings.local.json"
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    return project_root / ".claude" / "settings.json"  # project (default)


def run_install(rest: list[str]) -> int:
    yes, rest = pull_bool_flag(rest, "yes")
    scope, rest = pull_flag_value(rest, "scope")
    if scope is not None and scope not in _VALID_SCOPES:
        print(f"error: --scope must be project|local|user, got {scope!r}", file=sys.stderr)
        return 2
    repo, rest = pull_flag_value(rest, "repo")
    extra_repos = _parse_repo_flag(repo)
    if extra_repos is None:
        print(f"error: --repo must be <owner>/<name>, got {repo!r}", file=sys.stderr)
        return 2
    usage_doc, rest = pull_flag_value(rest, "usage-doc")
    skip_usage_doc, rest = pull_bool_flag(rest, "skip-usage-doc")
    caps_flag, rest = pull_flag_value(rest, "capabilities")
    caps_override = _parse_capabilities_flag(caps_flag)
    if caps_override is None:
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

    catalogs, warn = _collect_catalogs(
        plugin_name, extra_repos=extra_repos, project_root=project_root
    )
    if warn:
        print(f"error: {warn}", file=sys.stderr)
        return 1
    # Resolve <plugin>@<marketplace> by EXACT name over the whole universe —
    # never through the query-scoring path, which can drop a perfectly valid
    # target that happens to score 0 against its own name.
    matches = [
        Candidate(
            plugin=entry,
            marketplace=cat.name,
            repo=cat.repo,
            trusted=cat.trusted,
            is_collection=cat.is_collection,
            capabilities=capabilities_for(entry),
            score=0,
        )
        for cat in catalogs
        if cat.name == marketplace
        for entry in cat.plugins
        if entry.name == plugin_name
    ]
    repos = {c.repo for c in matches}
    if len(repos) > 1:
        print(
            f"error: {target} is ambiguous across repos {sorted(repos)}; "
            "refusing — disambiguate the marketplace.",
            file=sys.stderr,
        )
        return 1
    chosen = matches[0] if matches else None
    if chosen is None:
        hint = (
            ""
            if extra_repos
            else " — if it lives in a low-profile repo, name it: "
            "--repo <owner>/<name>"
        )
        print(f"error: {target} not found in known marketplaces{hint}", file=sys.stderr)
        return 1

    pi = build_install_plan((chosen,)).installs[0]
    pre_approved = _already_enabled_in(project_root, target)
    if pi.requires_approval and not yes:
        if pre_approved is None:
            print(
                f"error: {target} requires approval (untrusted source"
                f"{'; surfaces: ' + ', '.join(pi.blast.surfaces) if pi.blast.surfaces else ''}). "
                "Re-run with --yes to approve.",
                file=sys.stderr,
            )
            return 1
        # The exact target is already enabled in this repo's settings — the
        # team/user accepted its blast radius; re-registering needs no re-gate.
        print(f"note: {target} already enabled in {pre_approved} — re-registering.")

    usage_rel, usage_rc = _validate_usage_doc(project_root, usage_doc, skip_usage_doc)
    if usage_rc is not None:
        return usage_rc

    # Transport preflight: Claude Code's native fetcher must be able to reach
    # the marketplace repo. Warn (never block) so an HTTPS/SSH-key mismatch
    # surfaces now instead of as a silent load failure later.
    probe = _RUNNER(["git", "ls-remote", f"https://github.com/{chosen.repo}", "HEAD"])
    if probe.returncode != 0:
        print(
            f"warning: could not reach https://github.com/{chosen.repo} "
            "(git ls-remote failed) — Claude Code's native marketplace fetch may fail.",
            file=sys.stderr,
        )

    settings = _settings_path_for_scope(project_root, scope)
    try:
        # NEVER pass the plugin's listing semver as the marketplace git ref:
        # the marketplace repo has no such tag, and a bad ref breaks the native
        # fetch for EVERY plugin of that marketplace. Re-wiring an entry also
        # repairs a stale semver ref written by older versions.
        add_marketplace(settings, name=chosen.marketplace, repo=chosen.repo)
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
            _record_native(
                project_root,
                chosen,
                settings_rel=settings_rel,
                usage_doc_rel=usage_rel,
                capabilities_override=caps_override or None,
            )
        except EquipError as exc:
            print(f"warning: {target} wired, but manifest not updated: {exc}", file=sys.stderr)
    print(f"equip install: enabled {target} (native) -> {settings}")
    print(
        "note: Claude Code loads plugins at session start — restart, or open "
        f"/plugin and refresh the marketplace, then run `equip verify {target}`."
    )
    return 0


def _parse_capabilities_flag(raw: str | None) -> tuple[str, ...] | None:
    """Parse ``--capabilities a,b,c`` against the Capability vocabulary.

    Returns the parsed tuple (empty when the flag is absent), or ``None`` after
    printing the rc-2 usage error for an unknown capability.
    """
    if raw is None:
        return ()
    vocabulary = {c.value for c in Capability}
    caps = tuple(c.strip() for c in raw.split(",") if c.strip())
    unknown = [c for c in caps if c not in vocabulary]
    if unknown:
        print(
            f"error: unknown capability(ies) {unknown}; "
            f"valid: {', '.join(sorted(vocabulary))}",
            file=sys.stderr,
        )
        return None
    return caps


def _already_enabled_in(project_root: Path, target: str) -> str | None:
    """The settings file that already enables ``target``, or ``None``.

    Checks the project's committed settings.json and the machine-local
    settings.local.json — both count as prior approval for an identical
    re-registration (the blast radius was already accepted here). Malformed
    settings never grant approval.
    """
    for rel in (".claude/settings.json", ".claude/settings.local.json"):
        path = project_root / rel
        try:
            enabled = load_settings(path).get("enabledPlugins")
        except (MalformedSettingsError, OSError):
            continue
        if isinstance(enabled, dict) and enabled.get(target) is True:
            return rel
    return None


def _record_native(
    project_root: Path,
    chosen: Candidate,
    *,
    settings_rel: str,
    usage_doc_rel: str | None = None,
    capabilities_override: tuple[str, ...] | None = None,
) -> None:
    context_dir = project_root / ".context"
    prior = read_manifest(context_dir)
    name = f"{chosen.plugin.name}@{chosen.marketplace}"
    item = EquipmentItem(
        kind=EquipmentKind.PLUGIN,
        name=name,
        path=settings_rel,
        source=EquipmentSource.MARKETPLACE,
        capabilities=capabilities_override or chosen.capabilities,
        grounded_in=(usage_doc_rel,) if usage_doc_rel else (),
        version=chosen.plugin.version,
        marketplace=chosen.marketplace,
        origin_repo=chosen.repo,
        # origin_ref stays None: it is documented as a pinned commit sha — the
        # plugin's listing semver was never that (the wrong-ref defect).
        origin_ref=None,
        mechanism=InstallMechanism.NATIVE.value,
    )
    items = tuple(i for i in prior.items if i.name != name) + (item,)
    write_manifest(context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=items))
