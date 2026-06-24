"""`dummyindex install` — copy the skill tree + auto-init the project."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .common import (
    _SKILL_REGISTRATION,
    _SKILLS_DIR,
    PACKAGE_VERSION,
    SKILL_REL,
    _install_commands,
    _skill_src,
)


def install(
    *,
    scope: str = "user",
    project_dir: Path | None = None,
    skill_only: bool = False,
    no_onboarding: bool = False,
    defaults: bool = False,
    no_superpowers: bool = False,
) -> None:
    """Copy the skill into Claude Code's skills directory, then auto-init the
    current project if it's a git repo.

    scope="user"    -> ~/.claude/skills/dummyindex/SKILL.md  (default)
    scope="project" -> <project_dir>/.claude/skills/dummyindex/SKILL.md
                       (project_dir defaults to CWD)

    Auto-init: after the skill copy, if the resolved project candidate
    (``project_dir`` when given, else CWD) is a git repo — a ``.git/``
    directory *or* a submodule/worktree ``.git`` pointer file — this also
    runs the full ``init`` flow on it: builds ``.context/``,
    writes a managed CLAUDE.md block, and installs the SessionStart
    drift hook (so every new Claude session in the repo sees a report
    of source files newer than their `.context/features/<id>/` docs).
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

    src = _skill_src("skill.md")
    if not src.exists():
        print(
            f"error: {src} not found - reinstall dummyindex from source",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    dst = base / SKILL_REL  # ~/.claude/skills/dummyindex/SKILL.md
    skill_dir = dst.parent  # ~/.claude/skills/dummyindex/
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Copy the SKILL.md (entry point) plus every companion markdown under
    # skills/agents/, skills/council/, skills/retrieval/. The orchestrator
    # references them as relative paths so the whole tree must ship.
    # The SKILL.md gets a `__VERSION__` placeholder substituted with the
    # installed package version so the user can verify what's running.
    dst.write_text(
        src.read_text(encoding="utf-8").replace("__VERSION__", PACKAGE_VERSION),
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

    # The session-memory handoff ships as its OWN top-level skill so it is
    # invocable as /dummyindex-remember — a sibling of /dummyindex, not a
    # companion nested under it. (Claude Code discovers skills by
    # .claude/skills/<name>/SKILL.md.)
    mem_src = _SKILLS_DIR / "memory" / "SKILL.md"
    if mem_src.is_file():
        mem_dst = base / ".claude" / "skills" / "dummyindex-remember" / "SKILL.md"
        mem_dst.parent.mkdir(parents=True, exist_ok=True)
        mem_dst.write_text(
            mem_src.read_text(encoding="utf-8").replace("__VERSION__", PACKAGE_VERSION),
            encoding="utf-8",
        )
        print(f"  memory skill     ->  {mem_dst}")

    # Sibling skills — each its OWN top-level skill dir (siblings of
    # /dummyindex), so Claude Code discovers
    # /dummyindex-plan|equip|build|audit|update.
    for sub_name, skill_label in (
        ("plan", "dummyindex-plan"),
        ("equip", "dummyindex-equip"),
        ("build", "dummyindex-build"),
        ("audit", "dummyindex-audit"),
        ("gc", "dummyindex-gc"),
        ("update", "dummyindex-update"),
    ):
        bl_src = _SKILLS_DIR / sub_name / "SKILL.md"
        if not bl_src.is_file():
            continue
        bl_dst = base / ".claude" / "skills" / skill_label / "SKILL.md"
        bl_dst.parent.mkdir(parents=True, exist_ok=True)
        bl_dst.write_text(
            bl_src.read_text(encoding="utf-8").replace("__VERSION__", PACKAGE_VERSION),
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
                shutil.copy(item, comp_dst / item.name)
        print(f"  sibling skill    ->  {bl_dst}")

    (skill_dir / ".dummyindex_version").write_text(PACKAGE_VERSION, encoding="utf-8")
    print(f"  skill installed  ->  {dst}")
    print(
        f"  companions       ->  {sum(1 for _ in skill_dir.rglob('*.md')) - 1} markdown(s)"
    )

    copied = _install_commands(base)
    if copied:
        print(f"  commands         ->  {', '.join('/' + Path(c).stem for c in copied)}")

    if scope == "user":
        claude_md = Path.home() / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8")
            # Probe for the registration SENTINEL, not a bare "dummyindex"
            # mention: a user CLAUDE.md may name dummyindex without ever
            # carrying our managed block. "**dummyindex** (" is the stable,
            # unique opening of the `_SKILL_REGISTRATION` bullet (NOT
            # bootstrap's BEGIN_MARKER — a different marker).
            if "**dummyindex** (" in content:
                print("  CLAUDE.md        ->  already registered (no change)")
            else:
                claude_md.write_text(
                    content.rstrip() + _SKILL_REGISTRATION, encoding="utf-8"
                )
                print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
        else:
            claude_md.parent.mkdir(parents=True, exist_ok=True)
            claude_md.write_text(_SKILL_REGISTRATION.lstrip(), encoding="utf-8")
            print(f"  CLAUDE.md        ->  created at {claude_md}")

    # Auto-init the resolved project candidate if it's a git repo. Skip
    # silently for non-repo dirs (user just wanted the skill) and when
    # the caller explicitly opted out via --skill-only. `is_git_repo`
    # accepts submodule/worktree `.git` files, not just `.git/` dirs.
    from dummyindex.context import is_git_repo

    auto_init_target = (project_dir or Path(".")).resolve()
    target_is_repo = is_git_repo(auto_init_target)
    init_ran = False
    if not skill_only and target_is_repo:
        init_ran = _auto_init_project(auto_init_target, no_superpowers=no_superpowers)
        if init_ran and (defaults or no_onboarding):
            _write_default_config(auto_init_target)
        # Heal an existing repo's stale config (pre-v2 schema / renamed value) so
        # `/dummyindex-update` upgrades it in place. A value-preserving migration,
        # not a clobber — current configs are left untouched (see `_needs_migration`).
        _migrate_existing_config(auto_init_target)
        # Fold equip-installed plugins back into config.wired so `/dummyindex-update`
        # never silently drops a plugin the user equipped (e.g. a v1→v2 migration
        # reseeds wired from defaults only). Best-effort, idempotent, no churn.
        _reconcile_wired_step(auto_init_target)

    print()
    if init_ran:
        print(f"Done. Open Claude Code in {auto_init_target} and type:")
    elif scope == "project":
        target = (project_dir or Path(".")).resolve()
        print(f"Done. Open Claude Code in {target} and type:")
    else:
        print("Done. Open Claude Code and type:")
    print()
    print("  /dummyindex .")
    print()
    if not skill_only and not init_ran and not target_is_repo:
        # Tell users *why* nothing else happened so they don't assume the
        # install was silently incomplete.
        print(
            f"  (no git repo at {auto_init_target} — skipped project init.\n"
            f"   run `dummyindex ingest <path>` from a project directory\n"
            f"   to build .context/ and install the SessionStart drift hook.)"
        )
        print()


def _auto_init_project(project_root: Path, *, no_superpowers: bool = False) -> bool:
    """Run the same flow as `dummyindex context init <project_root>`:
    build the deterministic backbone into ``.context/``, write the
    managed CLAUDE.md block, and install the SessionStart drift hook.

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
        from dummyindex.context.output.claude_md import reconcile_claude_md
    except Exception as exc:
        print(f"  auto-init skipped: import failed ({exc})", file=sys.stderr)
        return False

    # NON-DESTRUCTIVE on a curated index. A bare `install` (e.g. the
    # /dummyindex-update flow) must never re-cluster a council-enriched
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
        try:
            claude_result = reconcile_claude_md(project_root)
            print(f"  CLAUDE.md (proj) ->  {claude_result.message}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  CLAUDE.md (proj) ->  skipped ({exc})", file=sys.stderr)
        hooks_ok = _install_project_hooks(project_root, install_hooks_fn)
        _wire_default_plugins_step(project_root, no_superpowers=no_superpowers)
        return hooks_ok

    try:
        result = build_all(
            project_root,
            out_root=project_root,
            bootstrap=True,
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

    hooks_ok = _install_project_hooks(project_root, install_hooks_fn)
    _wire_default_plugins_step(project_root, no_superpowers=no_superpowers)
    return hooks_ok


def _install_project_hooks(project_root: Path, install_hooks_fn) -> bool:
    """Install the SessionStart/Stop/PreCompact hooks; print the outcome.

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


def _write_default_config(project_root: Path) -> None:
    """Write the recommended defaults to ``<project>/.context/config.json``.

    Used by ``install --defaults`` / ``--no-onboarding`` (the non-interactive
    CI path) right after a successful auto-init. Best-effort: a failure here
    doesn't fail the install, since the index itself already built. Never
    clobbers an existing config — onboarding (or a prior run) owns it.
    """
    try:
        from dummyindex.context.domains.config import (
            CONFIG_REL,
            ConfigError,
            default_config,
            write_config,
        )

        config_path = project_root / ".context" / CONFIG_REL
        if config_path.exists():
            print("  config.json      ->  kept existing (already configured)")
            return
        write_config(project_root / ".context", default_config())
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
        print(f"  config.json      ->  wired reconcile skipped ({exc})", file=sys.stderr)


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
