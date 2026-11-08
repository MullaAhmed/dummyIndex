"""Auto-init / project-init helpers: the ``.context/`` build + Claude/Codex
guidance + hooks + default-plugins steps that run after the skill install.

`_install_project_hooks` is called via `_install_pkg`, even from this file, so a
test that patches it on the package (`tests/test_install.py`) is seen here. The
self-import during package init is safe; see `link/sweep.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import dummyindex.installer.install as _install_pkg
from dummyindex.context.domains.config import ConfigError

from ..common import PACKAGE_VERSION, platforms_for


def _auto_init_project(
    project_root: Path,
    *,
    no_default_plugins: bool = False,
    no_superpowers: bool = False,
    platform: str = "claude",
    codex_guidance_owner: str = "project",
    force_downgrade: bool = False,
) -> bool:
    """Run the `dummyindex context init` flow: build ``.context/``, write the
    selected host guidance, and add Claude integrations when requested.

    ``force_downgrade`` lets the curated refresh lower a newer
    ``meta.dummyindex_version`` stamp. Both branches print the migration report.
    Returns False when the imports, refresh or build fail (reported on stderr,
    never raised: the skill install already succeeded), else True.
    """
    # Preserve the old direct-call seam while carrying one canonical gate
    # through the rest of the orchestration.
    no_default_plugins = no_default_plugins or no_superpowers
    try:
        from dummyindex.cli.migrate import has_foldable_legacy_claude_md
        from dummyindex.context.build import (
            enriched_index_status,
            refresh_deterministic_artifacts,
        )
        from dummyindex.context.build.runner import build_all
        from dummyindex.context.build.upgrade import format_migration_report
        from dummyindex.context.hooks import install as install_hooks_fn
        from dummyindex.context.output.agents_md import bootstrap_project_agents_md
        from dummyindex.context.output.claude_md import reconcile_claude_md
    except Exception as exc:
        print(f"  auto-init skipped: import failed ({exc})", file=sys.stderr)
        return False

    concrete_platforms = platforms_for(platform)
    use_claude = "claude" in concrete_platforms
    use_codex = "codex" in concrete_platforms

    # Non-destructive on a curated index: a bare `install` (e.g. the update flow)
    # must never re-cluster an enriched taxonomy into community-N stubs, so it
    # only refreshes deterministic artefacts. Re-clustering needs `rebuild --full`
    # or a fresh `ingest`; a deterministic-only or absent index full-builds.
    context_dir = project_root / ".context"
    status = enriched_index_status(context_dir) if context_dir.is_dir() else None
    if status is not None and status.enriched:
        try:
            refresh = refresh_deterministic_artifacts(
                project_root,
                extra_doc_roots=(),
                dummyindex_version=PACKAGE_VERSION,
                allow_downgrade=force_downgrade,
            )
        except Exception as exc:
            print(f"  auto-init skipped: refresh failed ({exc})", file=sys.stderr)
            return False
        print(
            f"  .context/        ->  curated index preserved — refreshed "
            f"{len(refresh.written)} deterministic artefact(s) (no re-cluster)"
        )
        for line in format_migration_report(refresh.migration, refresh.failed):
            print(line)
        if status.desync:
            print(
                "  .context/        ->  warning: features/INDEX.json does not "
                "list the curated feature dirs on disk — index desync; run "
                "`dummyindex context refresh-indexes` or restore INDEX.json"
            )
        if use_claude or has_foldable_legacy_claude_md(project_root):
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
            _install_pkg._install_project_hooks(project_root, install_hooks_fn)
            _wire_default_plugins_step(
                project_root,
                no_default_plugins=no_default_plugins,
                platform=platform,
            )
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
    for line in format_migration_report(result.migration):
        print(line)
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

    # Claude-platform installs already folded via build_all(bootstrap=True);
    # codex-only installs fold a dummyindex-generated legacy root file here —
    # never creating guidance, never touching an active Codex instruction.
    if not use_claude and has_foldable_legacy_claude_md(project_root):
        try:
            claude_result = reconcile_claude_md(project_root)
            print(f"  CLAUDE.md (proj) ->  {claude_result.message}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  CLAUDE.md (proj) ->  skipped ({exc})", file=sys.stderr)

    if use_claude:
        _install_pkg._install_project_hooks(project_root, install_hooks_fn)
        _wire_default_plugins_step(
            project_root,
            no_default_plugins=no_default_plugins,
            platform=platform,
        )
    _refresh_equipment_step(project_root)
    return True


def _refresh_equipment_step(project_root: Path) -> None:
    """Refresh equip-generated tools to the just-installed templates.

    In an equipped repo (``.context/equipment.json``), re-render and re-baseline
    pristine generated tools whose fresh render differs, so a reinstall carries
    the toolkit forward. Never-clobber: a USER_MODIFIED tool is always skipped.
    Best-effort (a failure never fails the install); a silent no-op when the repo
    is not equipped.
    """
    try:
        from dummyindex.cli.equip.common import fresh_rendered
        from dummyindex.context.domains.equip import EQUIPMENT_REL, refresh
    except Exception as exc:  # pragma: no cover - defensive import guard
        print(f"  equipment        ->  refresh skipped ({exc})", file=sys.stderr)
        return
    context_dir = project_root / ".context"
    if not (context_dir / EQUIPMENT_REL).is_file():
        return  # not equipped — nothing to refresh
    try:
        rendered = fresh_rendered(project_root, context_dir)
        report = refresh(
            project_root,
            fresh_renders={item.name: content for item, _path, content in rendered},
            fresh_items={item.name: item for item, _path, _content in rendered},
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
    """Install UserPromptSubmit/SessionStart/Stop/PreCompact/PreToolUse hooks.

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


def _migrate_existing_config(project_root: Path) -> bool:
    """Upgrade a loadable-but-stale ``.context/config.json`` in place.

    Run on every repo install so an update heals configs written before a
    schema bump or renamed value. Value-preserving: only a stale config is
    rewritten, so it is silent on a current repo and never clobbers user choices.
    """
    from dummyindex.context.domains.config import migrate_config_in_place

    moved = migrate_config_in_place(project_root / ".context")
    if moved:
        print("  config.json      ->  migrated to current schema")
    return moved


def _reconcile_wired_step(project_root: Path) -> bool:
    """Fold equip-installed plugins into ``config.wired`` (heal declared intent).

    Run on every repo install so an update never drops an equipped plugin: a
    v1→v2 migration reseeds ``wired`` from defaults only, and older CLIs equipped
    without writing ``wired``. Reconciles against ``equipment.json`` on the
    ``<plugin>@<marketplace>`` key. Idempotent; silent when nothing needs folding.
    """
    from dummyindex.context.domains.config import reconcile_wired_with_equipment

    moved = reconcile_wired_with_equipment(project_root / ".context")
    if moved:
        print("  config.json      ->  folded equipped plugins into wired")
    return moved


def _wire_default_plugins_step(
    project_root: Path,
    *,
    no_default_plugins: bool,
    platform: str = "claude",
) -> None:
    """Enable dummyindex's default plugins in the project settings.json.

    Best-effort, like the hook install: a settings snag is reported but never
    fails the init. Reads ``.context/config.json`` (if present) for a persisted
    opt-out; the one-run default-plugin gate overrides it.
    """
    # The one-run opt-out is an early gate: no config migration/backfill,
    # settings read/write, runner probe, or trust noise occurs beyond it.
    if no_default_plugins:
        return

    from dummyindex.context.default_plugins import (
        default_wired,
        describe_default_plugin_trust,
        describe_install_result,
        describe_wire_result,
        install_default_plugins,
        resolve_enabled,
        wire_default_plugins,
    )
    from dummyindex.context.domains.config import (
        ConfigError,
        read_config,
        reconcile_default_plugins,
    )

    # Disclose reviewed third-party provenance before the first config
    # reconciliation, settings action, or runner probe.
    for line in describe_default_plugin_trust():
        print(f"  {line}")

    context_dir = project_root / ".context"
    try:
        # Validate first. Migration helpers intentionally tolerate malformed
        # state, but orchestration must fail closed rather than seed defaults.
        read_config(context_dir)
        _migrate_existing_config(project_root)
        _reconcile_wired_step(project_root)
        if reconcile_default_plugins(context_dir, platform=platform):
            print("  config.json      ->  reconciled default plugins")
        cfg = read_config(context_dir)
    except (ConfigError, OSError) as exc:
        print(
            f"  plugins warning  ->  skipped defaults (invalid config: {exc})",
            file=sys.stderr,
        )
        return

    wired = default_wired() if cfg is None else cfg.wired
    config_value = None if cfg is None else cfg.default_plugins_enabled
    enabled = resolve_enabled(cli_opt_out=False, config_value=config_value)
    result = wire_default_plugins(wired, project_root, enabled=enabled)
    install_result = install_default_plugins(
        project_root,
        wired=wired,
        enabled=enabled,
    )
    info, warn = describe_wire_result(result)
    install_info, install_warn = describe_install_result(install_result)
    for line in (*info, *install_info):
        print(f"  {line}")
    for line in (*warn, *install_warn):
        print(f"  {line}", file=sys.stderr)
