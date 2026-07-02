"""``equip install`` — wire a discovered plugin (native) or vendor a collection
skill (copy onto disk).

Wire-only: parse flags, resolve the exact ``<plugin>@<marketplace>`` target over
the discovery universe (:mod:`.discover`), gate on trust + a usage playbook, then
either NATIVE-enable the plugin in ``.claude/settings.json`` or VENDOR its
``SKILL.md`` under ``.claude/skills/`` — recording the result in the equipment
manifest. The runner and the discovery helpers live in :mod:`.discover`; this
module reaches them via the ``discover`` module object so the test seam
(``monkeypatch …discover._RUNNER``) stays a single source of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dummyindex.context.claude_plugins import add_marketplace, enable_plugin
from dummyindex.context.claude_settings import MalformedSettingsError, load_settings
from dummyindex.context.default_plugins import WiredEntry, WiredKind
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.config import ConfigError, read_config, write_config
from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    VENDORED_SENTINEL,
    Candidate,
    Capability,
    EquipError,
    EquipmentItem,
    EquipmentKind,
    EquipmentManifest,
    EquipmentSource,
    InstallMechanism,
    SourceError,
    build_install_plan,
    capabilities_for,
    classify_item,
    fetch_file,
    is_safe_to_write,
    is_user_owned,
    list_skills,
    read_manifest,
    resolve_ref,
    stamp_vendored,
    vendored_item,
    write_manifest,
)

from ..common import usage_error
from . import discover
from .common import pull_bool_flag, pull_flag_value


def _settings_path_for_scope(project_root: Path, scope: str | None) -> Path:
    if scope == "local":
        return project_root / ".claude" / "settings.local.json"
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    return project_root / ".claude" / "settings.json"  # project (default)


def run_install(rest: list[str]) -> int:
    yes, rest = pull_bool_flag(rest, "yes")
    scope, rest = pull_flag_value(rest, "scope")
    if scope is not None and scope not in discover._VALID_SCOPES:
        print(
            f"error: --scope must be project|local|user, got {scope!r}", file=sys.stderr
        )
        return 2
    repo, rest = pull_flag_value(rest, "repo")
    extra_repos = discover._parse_repo_flag(repo)
    if extra_repos is None:
        print(f"error: --repo must be <owner>/<name>, got {repo!r}", file=sys.stderr)
        return 2
    usage_doc, rest = pull_flag_value(rest, "usage-doc")
    skip_usage_doc, rest = pull_bool_flag(rest, "skip-usage-doc")
    caps_flag, rest = pull_flag_value(rest, "capabilities")
    caps_override = _parse_capabilities_flag(caps_flag)
    if caps_override is None:
        return 2
    project_root, rest = discover._parse_root(rest)
    target = next((a for a in rest if "@" in a), None)
    if target is None:
        return usage_error("equip", "`equip install` requires <plugin>@<marketplace>")
    plugin_name, _, marketplace = target.partition("@")
    if not plugin_name or not marketplace:
        return usage_error("equip", "target must be <plugin>@<marketplace>")

    catalogs, warn = discover._collect_catalogs(
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
            else " — if it lives in a low-profile repo, name it: --repo <owner>/<name>"
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

    # VENDOR mechanism: a loose-collection skill is copied onto disk under
    # .claude/skills/ (no native settings wiring). The approval + usage gates
    # above already fired, so this only runs once the install is approved.
    if pi.mechanism is InstallMechanism.VENDOR:
        return _run_vendor_install(
            project_root, chosen, usage_doc_rel=usage_rel, caps_override=caps_override
        )

    # Transport preflight: Claude Code's native fetcher must be able to reach
    # the marketplace repo. Warn (never block) so an HTTPS/SSH-key mismatch
    # surfaces now instead of as a silent load failure later.
    probe = discover._RUNNER(
        ["git", "ls-remote", f"https://github.com/{chosen.repo}", "HEAD"]
    )
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
            print(
                f"warning: {target} wired, but manifest not updated: {exc}",
                file=sys.stderr,
            )
        # Declared-intent write-back: upsert the matching `wired` entry into the
        # committed config.json keyed on <plugin>@<marketplace>, so config.wired
        # (intent) and equipment.json (render manifest) stay reconcilable on that
        # shared key. Skipped-with-warning when no committed config exists (e.g.
        # `--scope user`, or a repo indexed before config existed) — never
        # materialise a seeded config as a side effect of one install. Never
        # raises: a write-back failure leaves the install rc + manifest intact.
        _write_back_wired(project_root, target, chosen.plugin.version)
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
    write_manifest(
        context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=items)
    )


def _vendor_write_ok(target: Path) -> bool:
    """True when writing a vendored skill to ``target`` cannot clobber a foreign
    file: absent / carries our generated sentinel (:func:`is_safe_to_write`), or
    an existing file already carrying our :data:`VENDORED_SENTINEL` (ours to
    re-vendor). Any other existing file is a user file and is left untouched."""
    if is_safe_to_write(target):
        return True
    try:
        return VENDORED_SENTINEL in target.read_text(encoding="utf-8")
    except OSError:
        return False


def _record_vendored(
    project_root: Path,
    chosen: Candidate,
    *,
    rel_path: str,
    ref: str,
    content: str,
    capabilities: tuple[str, ...],
    usage_doc_rel: str | None = None,
) -> None:
    from dataclasses import replace

    context_dir = project_root / ".context"
    prior = read_manifest(context_dir)
    item = vendored_item(
        name=f"{chosen.plugin.name}@{chosen.marketplace}",
        rel_path=rel_path,
        kind_skill=True,
        capabilities=capabilities,
        repo=chosen.repo,
        ref=ref,
        content=content,
        marketplace=chosen.marketplace,
    )
    if usage_doc_rel:
        item = replace(item, grounded_in=(usage_doc_rel,))
    items = tuple(i for i in prior.items if i.name != item.name) + (item,)
    write_manifest(
        context_dir, EquipmentManifest(schema_version=SCHEMA_VERSION, items=items)
    )


def _run_vendor_install(
    project_root: Path,
    chosen: Candidate,
    *,
    usage_doc_rel: str | None,
    caps_override: tuple[str, ...],
) -> int:
    """Vendor one collection skill onto disk (the VENDOR mechanism).

    Resolves the repo HEAD to a pinned sha, fetches the skill's ``SKILL.md`` at
    that sha, stamps it, writes it under ``.claude/skills/<name>/`` behind the
    never-clobber guard, and records a VENDORED manifest item carrying the pinned
    ref. Pinning is what makes the vendored bytes reproducible and immune to a
    moving-HEAD swap after approval (concerns.md:13).
    """
    repo, name = chosen.repo, chosen.plugin.name
    # Path-safety: `name` becomes a path segment under .claude/skills/. Reject any
    # separator / traversal so a crafted collection entry can never escape the
    # skills dir (defense-in-depth — list_skills already yields single-component,
    # non-hidden names).
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        print(
            f"error: refusing to vendor skill with unsafe name {name!r}",
            file=sys.stderr,
        )
        return 1
    try:
        ref = resolve_ref(repo, runner=discover._RUNNER)
        if ref is None:
            print(f"error: could not resolve a commit sha for {repo}", file=sys.stderr)
            return 1
        skill = next(
            (
                s
                for s in list_skills(repo, ref=ref, runner=discover._RUNNER)
                if s.name == name
            ),
            None,
        )
    except SourceError as exc:
        print(f"error: could not enumerate skills in {repo}: {exc}", file=sys.stderr)
        return 1
    if skill is None:
        print(f"error: no SKILL.md for {name!r} in {repo}@{ref[:12]}", file=sys.stderr)
        return 1
    try:
        content = fetch_file(repo, skill.path, ref=ref, runner=discover._RUNNER)
    except SourceError as exc:
        print(
            f"error: could not fetch {skill.path} from {repo}: {exc}", file=sys.stderr
        )
        return 1
    if content is None:
        print(f"error: {skill.path} not found in {repo}@{ref[:12]}", file=sys.stderr)
        return 1

    rel_path = f".claude/skills/{name}/SKILL.md"
    target = project_root / rel_path
    item_name = f"{name}@{chosen.marketplace}"
    try:
        prior_items = read_manifest(project_root / ".context").items
    except EquipError as exc:
        # The manifest is the never-clobber oracle for an already-vendored skill;
        # if we cannot read it we cannot tell a pristine copy from a hand-edited
        # one, so fail closed rather than risk overwriting an edit (and the record
        # step below would choke on the same corrupt ledger regardless).
        print(
            f"error: cannot read equipment manifest: {exc}; "
            "fix or remove .context/equipment.json before installing",
            file=sys.stderr,
        )
        return 1
    prior_item = next((i for i in prior_items if i.name == item_name), None)
    if prior_item is not None:
        # A skill we already vendored is governed by the hash baseline — the same
        # oracle refresh/uninstall use. A local edit (USER_MODIFIED / CUSTOMIZED /
        # INVARIANT_BROKEN) freezes it: re-install must not silently discard that
        # edit. Uninstall first to take a fresh pin.
        if is_user_owned(classify_item(project_root, prior_item)):
            print(
                f"error: vendored skill {item_name!r} has local edits at {rel_path}; "
                "refusing to overwrite (run `equip uninstall` first to re-vendor)",
                file=sys.stderr,
            )
            return 1
    elif not _vendor_write_ok(target):
        print(
            f"error: refusing to overwrite a user file at {rel_path} "
            "(not a dummyindex-vendored skill)",
            file=sys.stderr,
        )
        return 1
    try:
        write_text_atomic(target, stamp_vendored(content))
    except OSError as exc:
        print(f"error: could not write {rel_path}: {exc}", file=sys.stderr)
        return 1

    _record_vendored(
        project_root,
        chosen,
        rel_path=rel_path,
        ref=ref,
        content=content,
        capabilities=caps_override or chosen.capabilities,
        usage_doc_rel=usage_doc_rel,
    )
    print(
        f"equip install: vendored {name}@{chosen.marketplace} -> {rel_path} "
        f"(pinned {ref[:12]})"
    )
    return 0


def _write_back_wired(project_root: Path, target: str, version: str | None) -> None:
    """Upsert ``target`` into the committed ``config.wired``, keyed on ``target``.

    Reads ``config.json`` via :func:`read_config`; **only if a committed config
    exists** does it upsert a matching :class:`WiredEntry` (``kind=plugin``,
    ``target=<plugin>@<marketplace>``, descriptive ``version``) — replacing an
    existing entry with the same ``target`` else appending — and persist via
    :func:`write_config` (atomic). Absent config → skip with a warning (never
    materialise a seeded config as an install side effect). Single-writer per
    repo (no locking). Never raises: a read/write failure is warned-and-continued
    so the install's rc and ``equipment.json`` record are unaffected.
    """
    from dataclasses import replace

    context_dir = project_root / ".context"
    try:
        config = read_config(context_dir)
    except ConfigError as exc:
        print(
            f"warning: {target} wired, but config.json not updated (unreadable): {exc}",
            file=sys.stderr,
        )
        return
    if config is None:
        print(
            f"note: {target} not recorded in config.wired — no committed "
            "config.json (run dummyindex init to create one).",
            file=sys.stderr,
        )
        return

    entry = WiredEntry(kind=WiredKind.PLUGIN, target=target, version=version)
    kept = tuple(e for e in config.wired if e.target != target)
    updated = replace(config, wired=kept + (entry,))
    try:
        write_config(context_dir, updated)
    except OSError as exc:
        print(
            f"warning: {target} wired, but config.json not updated: {exc}",
            file=sys.stderr,
        )


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
