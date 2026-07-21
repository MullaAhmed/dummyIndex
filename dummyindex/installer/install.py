"""`dummyindex install` — copy the skill tree + auto-init the project."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from dummyindex.context.domains.config import ConfigError

from .common import (
    _SIBLING_SKILLS,
    _SKILL_REGISTRATION,
    _SKILLS_DIR,
    PACKAGE_VERSION,
    _first_symlink_component,
    _install_commands,
    _skill_src,
    platforms_for,
    render_skill,
    skill_rel,
    skills_root_rel,
)


def install(
    *,
    scope: str = "user",
    project_dir: Path | None = None,
    skill_only: bool = False,
    no_onboarding: bool = False,
    defaults: bool = False,
    no_superpowers: bool = False,
    platform: str = "claude",
) -> None:
    """Install the skill family for Claude Code, Codex, or both hosts.

    Claude uses ``.claude/skills`` and slash-command aliases. Codex uses the
    open Agent Skills location ``.agents/skills`` and ``$skill-name`` mentions.
    The default remains Claude-only for backward compatibility; pass
    ``platform="codex"`` or ``platform="both"`` explicitly.

    Auto-init: after the skill copy, if the resolved project candidate
    (``project_dir`` when given, else CWD) is a git repo — a ``.git/``
    directory *or* a submodule/worktree ``.git`` pointer file — this also
    runs the host-aware ``init`` flow on it: builds ``.context/`` and writes
    managed Claude guidance and/or the active Codex project instruction file.
    Claude installs its managed hooks and default plugins; Codex relies on
    durable project guidance and the installed skills.
    Pass ``skill_only=True`` (``--skill-only`` on the CLI) to suppress
    this and just install the skill — useful when running ``install``
    from a directory that happens to be a git repo but isn't the project
    you want indexed.
    """
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be 'user' or 'project', got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        concrete_platforms = platforms_for(platform)
    except ValueError as exc:
        print(f"error: --{exc}", file=sys.stderr)
        sys.exit(1)

    src = _skill_src("skill.md")
    if not src.exists():
        print(
            f"error: {src} not found - reinstall dummyindex from source",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    for host in concrete_platforms:
        # A user may deliberately manage ~/.claude or ~/.agents as a dotfiles
        # symlink. That host root is user-owned configuration, so follow it at
        # user scope while continuing to reject any deeper managed-directory
        # link (and every project-scope link).
        host_root = base / skills_root_rel(host).parts[0]
        allowed_symlinks = frozenset({host_root}) if scope == "user" else frozenset()
        if scope == "user" and host_root.is_symlink():
            try:
                resolved_host_root = host_root.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                print(
                    f"error: refusing to install through user host root symlink "
                    f"{host_root}: target is unavailable ({exc})",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not resolved_host_root.is_dir():
                print(
                    f"error: refusing to install through user host root symlink "
                    f"{host_root}: target is not a directory "
                    f"({resolved_host_root})",
                    file=sys.stderr,
                )
                sys.exit(1)
        unsafe_link = _symlinked_skill_install_directory(
            base, host, allowed_symlinks=allowed_symlinks
        )
        if unsafe_link is not None:
            print(
                f"error: refusing to install through managed directory symlink "
                f"{unsafe_link}",
                file=sys.stderr,
            )
            sys.exit(1)
    for host in concrete_platforms:
        _install_skill_family(base, host, src)

    if "claude" in concrete_platforms:
        allowed_symlinks = (
            frozenset({base / ".claude"}) if scope == "user" else frozenset()
        )
        copied = _install_commands(base, allowed_symlinks=allowed_symlinks)
        if copied:
            commands = ", ".join("/" + Path(c).stem for c in copied)
            print(f"  claude commands  ->  {commands}")

    if scope == "user" and "claude" in concrete_platforms:
        _register_claude_user_skill()
    if scope == "user" and "codex" in concrete_platforms:
        _register_codex_user_skill()

    # Auto-init the resolved project candidate if it's a git repo. Skip
    # silently for non-repo dirs (user just wanted the skill) and when
    # the caller explicitly opted out via --skill-only. `is_git_repo`
    # accepts submodule/worktree `.git` files, not just `.git/` dirs.
    from dummyindex.context import is_git_repo

    auto_init_target = (project_dir or Path(".")).resolve()
    target_is_repo = is_git_repo(auto_init_target)
    init_ran = False
    if not skill_only and target_is_repo:
        init_ran = _auto_init_project(
            auto_init_target,
            no_superpowers=no_superpowers,
            platform=platform,
            codex_guidance_owner=("user-auto-init" if scope == "user" else "project"),
        )
        if init_ran and (defaults or no_onboarding):
            _write_default_config(auto_init_target, platform=platform)
        # Heal an existing repo's stale config (pre-v2 schema / renamed value) so
        # `$dummyindex-update` and `/dummyindex-update` upgrade it in place.
        _migrate_existing_config(auto_init_target)
        # Claude's equip plugin state is meaningful only when Claude is one of
        # the selected hosts. Codex falls back to its built-in/custom agents.
        if "claude" in concrete_platforms:
            _reconcile_wired_step(auto_init_target)

    selected = " + ".join(
        "Claude Code" if p == "claude" else "Codex" for p in concrete_platforms
    )
    if platform == "claude":
        invocations = ("/dummyindex .",)
    elif platform == "codex":
        invocations = ("$dummyindex .",)
    else:
        invocations = ("Claude Code: /dummyindex .", "Codex:      $dummyindex .")
    print()
    if init_ran:
        print(f"Done. Open {selected} in {auto_init_target} and run:")
    elif scope == "project":
        target = (project_dir or Path(".")).resolve()
        print(f"Done. Open {selected} in {target} and run:")
    else:
        print(f"Done. Open {selected} and run:")
    print()
    for invocation in invocations:
        print(f"  {invocation}")
    print()
    if not skill_only and not init_ran and not target_is_repo:
        platform_flag = "" if platform == "claude" else f" --platform {platform}"
        print(
            f"  (no git repo at {auto_init_target} — skipped project init.\n"
            f"   run `dummyindex ingest <path>{platform_flag}` from a project directory\n"
            f"   to build .context/ and write the host guidance.)"
        )
        print()


def _install_skill_family(base: Path, platform: str, src: Path) -> None:
    """Copy the main skill, companions, and sibling skills for one host."""
    dst = base / skill_rel(platform)
    skill_dir = dst.parent
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Copy the SKILL.md (entry point) plus every companion markdown under
    # skills/agents/, skills/council/, skills/retrieval/. The orchestrator
    # references them as relative paths so the whole tree must ship.
    # The SKILL.md gets a `__VERSION__` placeholder substituted with the
    # installed package version so the user can verify what's running.
    if dst.is_symlink():
        dst.unlink()
    dst.write_text(
        render_skill(src.read_text(encoding="utf-8"), platform=platform),
        encoding="utf-8",
    )
    skills_pkg_dir = _SKILLS_DIR
    for subdir in ("agents", "council", "retrieval"):
        src_sub = skills_pkg_dir / subdir
        if not src_sub.is_dir():
            continue
        dst_sub = skill_dir / subdir
        dst_sub.mkdir(parents=True, exist_ok=True)
        # Drop any stale markdowns from a prior version first, so an upgrade
        # leaves exactly the current source set. v0.14 removed the chairman /
        # senior-developer / stage1-3 files; without this wipe they'd linger
        # beside the new pipeline docs and the orchestrator would see
        # contradictory personas.
        for stale in dst_sub.glob("*.md"):
            stale.unlink()
        for md in sorted(src_sub.glob("*.md")):
            shutil.copy(md, dst_sub / md.name)

    skills_root = base / skills_root_rel(platform)
    for sub_name, skill_label in _SIBLING_SKILLS:
        bl_src = _SKILLS_DIR / sub_name / "SKILL.md"
        if not bl_src.is_file():
            continue
        bl_dst = skills_root / skill_label / "SKILL.md"
        bl_dst.parent.mkdir(parents=True, exist_ok=True)
        if bl_dst.is_symlink():
            bl_dst.unlink()
        bl_dst.write_text(
            render_skill(bl_src.read_text(encoding="utf-8"), platform=platform),
            encoding="utf-8",
        )
        # Ship each skill's companion subtree alongside its SKILL.md (e.g.
        # audit's persona `agents/`, read from the installed dir). Copied
        # verbatim (no __VERSION__ substitution), like the main skill's
        # companions. `*.tmpl` render templates are SKIPPED: equip's renderer
        # resolves them package-relative (`equip/generate/render.py`), never
        # from the installed skill dir, so copying them ships inert files
        # that mislead agents and pollute reconcile/lint surfaces. Installs
        # <= 0.25.0 did copy them — purge those stale twins on upgrade.
        for companion in ("templates", "agents"):
            comp_src = _SKILLS_DIR / sub_name / companion
            comp_dst = bl_dst.parent / companion
            if comp_dst.is_dir():
                for stale in comp_dst.glob("*.tmpl"):
                    stale.unlink()
                if not any(comp_dst.iterdir()):
                    comp_dst.rmdir()
            if not comp_src.is_dir():
                continue
            items = [
                item
                for item in sorted(comp_src.glob("*"))
                if item.is_file() and item.suffix != ".tmpl"
            ]
            if not items:
                continue
            comp_dst.mkdir(parents=True, exist_ok=True)
            for item in items:
                item_dst = comp_dst / item.name
                if item_dst.is_symlink():
                    item_dst.unlink()
                shutil.copy(item, item_dst)
        print(f"  {platform} skill installed  ->  {bl_dst}")

    version_file = skill_dir / ".dummyindex_version"
    if version_file.is_symlink():
        version_file.unlink()
    version_file.write_text(PACKAGE_VERSION, encoding="utf-8")
    print(f"  {platform} skill installed  ->  {dst}")
    print(
        f"  companions       ->  {sum(1 for _ in skill_dir.rglob('*.md')) - 1} markdown(s)"
    )


def _symlinked_skill_install_directory(
    base: Path,
    platform: str,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> Path | None:
    """Return a managed destination directory reached through a symlink."""
    main_dir = (base / skill_rel(platform)).parent
    directories = [
        main_dir,
        *(main_dir / name for name in ("agents", "council", "retrieval")),
    ]
    skills_root = base / skills_root_rel(platform)
    for _sub_name, skill_label in _SIBLING_SKILLS:
        sibling = skills_root / skill_label
        directories.extend((sibling, sibling / "templates", sibling / "agents"))
    for directory in directories:
        linked = _first_symlink_component(
            base, directory, allowed_symlinks=allowed_symlinks
        )
        if linked is not None:
            return linked
    return None


def _register_claude_user_skill() -> None:
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        if "**dummyindex** (" in content:
            print("  CLAUDE.md        ->  already registered (no change)")
            return
        claude_md.write_text(content.rstrip() + _SKILL_REGISTRATION, encoding="utf-8")
        print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
        return
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text(_SKILL_REGISTRATION.lstrip(), encoding="utf-8")
    print(f"  CLAUDE.md        ->  created at {claude_md}")


def _register_codex_user_skill() -> None:
    """Add a managed pointer to Codex's active user-global instruction file."""
    try:
        from dummyindex.context.output.agents_md import bootstrap_global_agents_md

        path = bootstrap_global_agents_md(Path.home())
    except (OSError, ValueError) as exc:
        print(f"  Codex guidance   ->  skipped ({exc})", file=sys.stderr)
        return
    print(f"  Codex guidance   ->  registered in {path}")


def _auto_init_project(
    project_root: Path,
    *,
    no_superpowers: bool = False,
    platform: str = "claude",
    codex_guidance_owner: str = "project",
) -> bool:
    """Run the same flow as `dummyindex context init <project_root>`:
    build the deterministic backbone into ``.context/``, write the
    selected host guidance, and Claude integrations when requested.

    Returns True on success, False on any failure (printed to stderr but
    not raised — the skill install itself already succeeded, and we
    don't want to make the whole command exit non-zero just because a
    secondary project-init step hit a snag).
    """
    try:
        from dummyindex.context.build import (
            enriched_index_status,
            refresh_deterministic_artifacts,
        )
        from dummyindex.context.build.runner import build_all
        from dummyindex.context.hooks import install as install_hooks_fn
        from dummyindex.context.output.agents_md import bootstrap_project_agents_md
        from dummyindex.context.output.claude_md import reconcile_claude_md
    except Exception as exc:
        print(f"  auto-init skipped: import failed ({exc})", file=sys.stderr)
        return False

    concrete_platforms = platforms_for(platform)
    use_claude = "claude" in concrete_platforms
    use_codex = "codex" in concrete_platforms

    # NON-DESTRUCTIVE on a curated index. A bare `install` (e.g. the
    # /dummyindex-update or $dummyindex-update flow) must never re-cluster a
    # council-enriched
    # taxonomy into community-N stubs. When `.context/` already exists and is
    # enriched, take the deterministic refresh path: refresh the enrichment-
    # free artefacts, advance the version stamp, and still bootstrap CLAUDE.md
    # + install hooks. A re-cluster requires an explicit `rebuild --full` or a
    # fresh `ingest`. A deterministic-only or absent index full-builds as before.
    context_dir = project_root / ".context"
    status = enriched_index_status(context_dir) if context_dir.is_dir() else None
    if status is not None and status.enriched:
        try:
            refresh = refresh_deterministic_artifacts(
                project_root,
                extra_doc_roots=(),
                dummyindex_version=PACKAGE_VERSION,
            )
        except Exception as exc:
            print(f"  auto-init skipped: refresh failed ({exc})", file=sys.stderr)
            return False
        print(
            f"  .context/        ->  curated index preserved — refreshed "
            f"{len(refresh.written)} deterministic artefact(s) (no re-cluster)"
        )
        if status.desync:
            print(
                "  .context/        ->  warning: features/INDEX.json does not "
                "list the curated feature dirs on disk — index desync; run "
                "`dummyindex context refresh-indexes` or restore INDEX.json"
            )
        if use_claude:
            try:
                claude_result = reconcile_claude_md(project_root)
                print(f"  CLAUDE.md (proj) ->  {claude_result.message}")
            except Exception as exc:  # pragma: no cover - defensive
                print(f"  CLAUDE.md (proj) ->  skipped ({exc})", file=sys.stderr)
        if use_codex:
            try:
                agents_path = bootstrap_project_agents_md(
                    project_root,
                    owner=codex_guidance_owner,
                )
                print(f"  Codex guidance   ->  managed block written: {agents_path}")
            except Exception as exc:  # pragma: no cover - defensive
                print(f"  Codex guidance   ->  skipped ({exc})", file=sys.stderr)
        if use_claude:
            _install_project_hooks(project_root, install_hooks_fn)
            _wire_default_plugins_step(project_root, no_superpowers=no_superpowers)
            _refresh_equipment_step(project_root)
        return True

    try:
        result = build_all(
            project_root,
            out_root=project_root,
            bootstrap=use_claude,
            dummyindex_version=PACKAGE_VERSION,
            extra_doc_roots=(),
        )
    except Exception as exc:
        print(f"  auto-init skipped: build failed ({exc})", file=sys.stderr)
        return False

    print(
        f"  .context/        ->  built ({len(result.written)} files, "
        f"{result.file_count} indexed, {result.symbol_count} symbols)"
    )
    if result.bootstrapped:
        print("  CLAUDE.md (proj) ->  managed block written")
    if use_codex:
        try:
            agents_path = bootstrap_project_agents_md(
                project_root,
                owner=codex_guidance_owner,
            )
            print(f"  Codex guidance   ->  managed block written: {agents_path}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  Codex guidance   ->  skipped ({exc})", file=sys.stderr)

    if use_claude:
        _install_project_hooks(project_root, install_hooks_fn)
        _wire_default_plugins_step(project_root, no_superpowers=no_superpowers)
        _refresh_equipment_step(project_root)
    return True


def _refresh_equipment_step(project_root: Path) -> None:
    """Refresh equip-generated tools to the just-installed templates.

    When the repo is equipped (``.context/equipment.json`` present), re-render the
    PRISTINE generated agents / skills / specialists whose fresh render differs
    under the current dummyindex version and re-baseline them — so a reinstall (the
    ``/dummyindex-update`` flow) carries the generated toolkit forward, not just the
    plugin skill family + the deterministic backbone. Hash-baselined and
    never-clobber: a USER_MODIFIED tool is skipped forever. Best-effort — a failure
    never fails the install (the primary skill/wiring refresh already succeeded),
    and a repo with no ``equipment.json`` is a silent no-op.
    """
    try:
        from dummyindex.cli.equip.common import fresh_renders
        from dummyindex.context.domains.equip import EQUIPMENT_REL, refresh
    except Exception as exc:  # pragma: no cover - defensive import guard
        print(f"  equipment        ->  refresh skipped ({exc})", file=sys.stderr)
        return
    context_dir = project_root / ".context"
    if not (context_dir / EQUIPMENT_REL).is_file():
        return  # not equipped — nothing to refresh
    try:
        report = refresh(
            project_root,
            fresh_renders=fresh_renders(project_root, context_dir),
            dry_run=False,
        )
    except Exception as exc:
        print(f"  equipment        ->  refresh skipped ({exc})", file=sys.stderr)
        return
    if report.refreshed:
        print(
            f"  equipment        ->  refreshed {len(report.refreshed)} generated "
            f"tool(s) to the new templates "
            f"({len(report.skipped_user_modified)} user-modified kept)"
        )
    else:
        print(
            f"  equipment        ->  {len(report.unchanged)} generated tool(s) "
            f"already current "
            f"({len(report.skipped_user_modified)} user-modified kept)"
        )


def _install_project_hooks(project_root: Path, install_hooks_fn) -> bool:
    """Install the SessionStart/Stop/PreCompact/PreToolUse hooks; print outcome.

    Shared by both auto-init paths (full build and the non-destructive
    enriched refresh). Always returns ``True`` — the ``.context/`` work
    already succeeded; a hook snag is a partial success, not a failure.
    """
    try:
        hook_result = install_hooks_fn(project_root)
    except Exception as exc:
        print(f"  hooks            ->  install failed ({exc})", file=sys.stderr)
        return True  # context still built — partial success
    if hook_result.installed:
        print(f"  hooks            ->  installed: {', '.join(hook_result.installed)}")
    elif hook_result.skipped:
        print(f"  hooks            ->  already current ({len(hook_result.skipped)})")
    if hook_result.errors:
        for name, err in hook_result.errors:
            print(f"  hooks warning ({name}): {err}", file=sys.stderr)

    return True


def _write_default_config(project_root: Path, *, platform: str = "claude") -> None:
    """Write the recommended defaults to ``<project>/.context/config.json``.

    Used by ``install --defaults`` / ``--no-onboarding`` (the non-interactive
    CI path) right after a successful auto-init. Best-effort: a failure here
    doesn't fail the install, since the index itself already built. Never
    clobbers an existing config — onboarding (or a prior run) owns it.
    """
    try:
        from dummyindex.context.domains.config import (
            CONFIG_REL,
            default_config,
            write_config,
        )

        config_path = project_root / ".context" / CONFIG_REL
        if config_path.exists():
            print("  config.json      ->  kept existing (already configured)")
            return
        config = default_config(platform=platform)
        write_config(project_root / ".context", config)
    except (OSError, ConfigError) as exc:  # pragma: no cover - defensive
        print(f"  config.json      ->  skipped ({exc})", file=sys.stderr)
        return
    print("  config.json      ->  wrote defaults")


def _migrate_existing_config(project_root: Path) -> None:
    """Upgrade a loadable-but-stale ``.context/config.json`` in place.

    Run on every repo install so ``/dummyindex-update`` heals configs written
    before a schema bump or a renamed value, instead of leaving them stale (or,
    pre-fix, unreadable). Best-effort and value-preserving: the delegate only
    rewrites a stale config (never a current one), so this is silent on an
    up-to-date repo and never clobbers user choices.
    """
    try:
        from dummyindex.context.domains.config import migrate_config_in_place

        if migrate_config_in_place(project_root / ".context"):
            print("  config.json      ->  migrated to current schema")
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        print(f"  config.json      ->  migration skipped ({exc})", file=sys.stderr)


def _reconcile_wired_step(project_root: Path) -> None:
    """Fold equip-installed plugins into ``config.wired`` (heal declared intent).

    Run on every repo install so ``/dummyindex-update`` never drops a plugin the
    user equipped: a v1→v2 migration reseeds ``wired`` from defaults only, and an
    older CLI equipped plugins without the ``config.wired`` write-back. The
    delegate reconciles ``config.wired`` against ``equipment.json`` on the shared
    ``<plugin>@<marketplace>`` key. Best-effort and idempotent — silent on a repo
    with nothing to fold, and never fails the install.
    """
    try:
        from dummyindex.context.domains.config import reconcile_wired_with_equipment

        if reconcile_wired_with_equipment(project_root / ".context"):
            print("  config.json      ->  folded equipped plugins into wired")
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        print(
            f"  config.json      ->  wired reconcile skipped ({exc})", file=sys.stderr
        )


def _wire_default_plugins_step(project_root: Path, *, no_superpowers: bool) -> None:
    """Enable dummyindex's default plugins in the project settings.json.

    Best-effort, like the hook install: a settings snag is reported but never
    fails the init. Reads ``.context/config.json`` (if present) for a persisted
    opt-out; the ``--no-superpowers`` flag overrides it.
    """
    from dummyindex.context.default_plugins import (
        default_wired,
        describe_install_result,
        describe_wire_result,
        install_default_plugins,
        resolve_enabled,
        wire_default_plugins,
    )

    # `wired` is the declared desired set: the loaded config's list when a config
    # exists, else the seed defaults (a fresh repo enables superpowers by
    # default). `config_value` derives the wiring decision from the same source —
    # a non-empty `wired` means "on", empty means "opted out" — preserving the
    # v1 `wire_superpowers` precedence (CLI `--no-superpowers` > config > on).
    wired = default_wired()
    config_value: bool | None = None
    try:
        from dummyindex.context.domains.config import ConfigError, read_config

        cfg = read_config(project_root / ".context")
        if cfg is not None:
            wired = cfg.wired
            config_value = bool(cfg.wired)
    except ConfigError:
        config_value = None

    enabled = resolve_enabled(cli_opt_out=no_superpowers, config_value=config_value)
    result = wire_default_plugins(wired, project_root, enabled=enabled)
    install_result = install_default_plugins(project_root, enabled=enabled)
    info, warn = describe_wire_result(result)
    install_info, install_warn = describe_install_result(install_result)
    for line in (*info, *install_info):
        print(f"  {line}")
    for line in (*warn, *install_warn):
        print(f"  {line}", file=sys.stderr)
