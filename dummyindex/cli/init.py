"""`dummyindex context init` — full deterministic backbone build + CLAUDE.md bootstrap."""
from __future__ import annotations
import sys
from pathlib import Path
from .common import (
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
    resolve_doc_paths,
)


def run(args: list[str]) -> int:
    from dummyindex.context.build.runner import build_all

    # Pull --no-hooks / --force / --no-superpowers out before path/root parsing.
    install_hooks = "--no-hooks" not in args
    force = "--force" in args
    no_superpowers = "--no-superpowers" in args
    args = [a for a in args if a not in ("--no-hooks", "--force", "--no-superpowers")]

    scope, explicit_root, rest = parse_path_and_root(args)
    doc_values, rest = pull_repeatable_flag(rest, "docs")
    if rest:
        print(f"error: unknown argument(s) for `init`: {rest}", file=sys.stderr)
        return 2
    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    extra_doc_roots = resolve_doc_paths(doc_values, base=Path.cwd())

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
        bootstrap=True,
        dummyindex_version=di_version,
        extra_doc_roots=extra_doc_roots,
    )
    print(
        f"context init: wrote {len(result.written)} files to {result.context_dir}"
    )
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    if result.languages:
        print(f"  languages: {', '.join(result.languages)}")
    if scope.resolve() != out_root:
        print(f"  scope:  {scope.resolve()}")
        print(f"  root:   {out_root}")
    if result.bootstrapped:
        print("  CLAUDE.md  ->  managed block written")

    if install_hooks:
        from dummyindex.context.hooks import install as install_hooks_fn

        hook_result = install_hooks_fn(out_root)
        if hook_result.installed:
            print(f"  hooks      ->  installed: {', '.join(hook_result.installed)}")
        elif hook_result.skipped:
            print(f"  hooks      ->  already current ({len(hook_result.skipped)})")
        if hook_result.errors:
            for name, err in hook_result.errors:
                print(f"  hooks warning ({name}): {err}", file=sys.stderr)

    from dummyindex.context.default_plugins import (
        describe_install_result,
        describe_wire_result,
        install_default_plugins,
        resolve_enabled,
        wire_default_plugins,
    )

    config_value: bool | None = None
    try:
        from dummyindex.context.domains.config import ConfigError, read_config

        cfg = read_config(out_root / ".context")
        config_value = cfg.wire_superpowers if cfg is not None else None
    except ConfigError:
        config_value = None

    enabled = resolve_enabled(cli_opt_out=no_superpowers, config_value=config_value)
    wire_result = wire_default_plugins(out_root, enabled=enabled)
    install_result = install_default_plugins(out_root, enabled=enabled)
    info, warn = describe_wire_result(wire_result)
    install_info, install_warn = describe_install_result(install_result)
    for line in (*info, *install_info):
        print(f"  {line}")
    for line in (*warn, *install_warn):
        print(f"  {line}", file=sys.stderr)

    return 0

