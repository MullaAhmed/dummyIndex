"""`dummyindex context init` — full deterministic backbone build + CLAUDE.md bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

from .common import (
    parse_kv_flags,
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
    resolve_doc_paths,
)


def _wire_default_plugins_step(
    project_root: Path,
    *,
    platform: str,
    no_default_plugins: bool,
) -> None:
    """Reconcile and materialize selected defaults at the CLI boundary."""
    # This one-run gate precedes every default-specific config, settings, and
    # runner action. It is deliberately not persisted.
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
        migrate_config_in_place,
        read_config,
        reconcile_default_plugins,
        reconcile_wired_with_equipment,
    )

    # Disclosure must precede config reconciliation, settings mutation, and
    # runner probes because the pinned defaults are reviewed third-party code.
    for line in describe_default_plugin_trust():
        print(f"  {line}")

    context_dir = project_root / ".context"
    try:
        # Validate strictly before tolerant migration helpers so malformed
        # state never falls back to default_wired().
        read_config(context_dir)
        if migrate_config_in_place(context_dir):
            print("  config.json      ->  migrated to current schema")
        if reconcile_wired_with_equipment(context_dir):
            print("  config.json      ->  folded equipped plugins into wired")
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
    wire_result = wire_default_plugins(wired, project_root, enabled=enabled)
    install_result = install_default_plugins(
        project_root,
        wired=wired,
        enabled=enabled,
    )
    info, warn = describe_wire_result(wire_result)
    install_info, install_warn = describe_install_result(install_result)
    for line in (*info, *install_info):
        print(f"  {line}")
    for line in (*warn, *install_warn):
        print(f"  {line}", file=sys.stderr)


def run(args: list[str]) -> int:
    from dummyindex.context.build.runner import build_all

    # Pull one-run boolean gates out before path/root parsing. Both plugin flag
    # spellings intentionally resolve to one canonical value here.
    install_hooks = "--no-hooks" not in args
    force = "--force" in args
    no_default_plugins = any(
        flag in args for flag in ("--no-default-plugins", "--no-superpowers")
    )
    args = [
        a
        for a in args
        if a
        not in (
            "--no-hooks",
            "--force",
            "--no-default-plugins",
            "--no-superpowers",
        )
    ]

    scope, explicit_root, rest = parse_path_and_root(args)
    doc_values, rest = pull_repeatable_flag(rest, "docs")
    # `--depth light|standard|deep` is a one-run override for the council depth
    # this ingest's first council pass runs at. It is never written to config;
    # `parse_kv_flags` recognises it via the shared value-flag alphabet.
    parsed, rest = parse_kv_flags(rest, allowed={"--depth", "--platform"})
    if rest:
        print(f"error: unknown argument(s) for `init`: {rest}", file=sys.stderr)
        return 2
    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    extra_doc_roots = resolve_doc_paths(doc_values, base=Path.cwd())

    from dummyindex.installer.common import normalize_platform_arg

    platform = parsed.get("platform", "claude")
    try:
        platform = normalize_platform_arg(platform)
    except ValueError:
        print(
            f"error: --platform must be claude|agents|both, got {platform!r}",
            file=sys.stderr,
        )
        return 2
    use_claude = platform in {"claude", "both"}
    use_codex = platform in {"codex", "both"}

    from dummyindex.context.domains.config import (
        ConfigError as _ConfigError,
    )
    from dummyindex.context.domains.config import (
        CouncilMode,
        DepthCommand,
        resolve_depth,
    )

    depth = parsed.get("depth")
    if depth is not None and depth not in {m.value for m in CouncilMode}:
        print(
            f"error: --depth must be light|standard|deep, got {depth!r}",
            file=sys.stderr,
        )
        return 2
    try:
        council_mode = resolve_depth(out_root / ".context", DepthCommand.INGEST, depth)
    except _ConfigError as exc:
        # The flag is already validated above, so a ConfigError here means a
        # malformed config.json — surface its real message instead of
        # misreporting it as a depth-flag problem.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # `init` (== `ingest`) means "first build": it re-clusters from scratch
    # and overwrites features/INDEX.json, tree.json, meta.json. An enriched
    # index proves this is NOT the first build, so refuse unless --force —
    # otherwise a stray `ingest` silently shatters the curated taxonomy.
    if not force:
        from dummyindex.context.build import is_enriched_index

        if is_enriched_index(out_root / ".context"):
            print(
                "error: curated index detected — `init`/`ingest` would discard "
                "the curated taxonomy + enrichment. Pass --force to rebuild from "
                "scratch anyway, or use `rebuild --changed` to refresh "
                "non-destructively.",
                file=sys.stderr,
            )
            return 2

    try:
        from importlib.metadata import version

        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    result = build_all(
        scope,
        out_root=out_root,
        bootstrap=use_claude,
        dummyindex_version=di_version,
        extra_doc_roots=extra_doc_roots,
    )
    print(f"context init: wrote {len(result.written)} files to {result.context_dir}")
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    print(f"  council depth: {council_mode.value}")
    if result.languages:
        print(f"  languages: {', '.join(result.languages)}")
    if scope.resolve() != out_root:
        print(f"  scope:  {scope.resolve()}")
        print(f"  root:   {out_root}")
    if result.bootstrapped:
        print("  CLAUDE.md  ->  managed block written")
    if use_codex:
        from dummyindex.context.output.agents_md import bootstrap_project_agents_md

        try:
            agents_path = bootstrap_project_agents_md(out_root)
        except (OSError, ValueError) as exc:
            # The index build is already complete.  Host guidance is a
            # best-effort integration step, so surface the actionable file
            # error without turning a recoverable conflict into a traceback.
            print(f"  Codex guidance -> skipped ({exc})", file=sys.stderr)
        else:
            print(f"  Codex guidance -> managed block written: {agents_path}")

    if install_hooks and use_claude:
        from dummyindex.context.hooks import install as install_hooks_fn

        hook_result = install_hooks_fn(out_root)
        if hook_result.installed:
            print(f"  hooks      ->  installed: {', '.join(hook_result.installed)}")
        elif hook_result.skipped:
            print(f"  hooks      ->  already current ({len(hook_result.skipped)})")
        if hook_result.errors:
            for name, err in hook_result.errors:
                print(f"  hooks warning ({name}): {err}", file=sys.stderr)

    if not use_claude:
        return 0

    _wire_default_plugins_step(
        out_root,
        platform=platform,
        no_default_plugins=no_default_plugins,
    )

    return 0
