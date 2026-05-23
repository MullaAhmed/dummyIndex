"""`dummyindex context <subcommand>` dispatch.

Wired in from `dummyindex/__main__.py`. PR 1 ships stubs for `init`, `rebuild`,
and `bootstrap`; real implementations land in PR 2–PR 5.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

_USAGE = """\
Usage: dummyindex context <subcommand> [args]

Subcommands:
  init [path]              Initialize .context/ in the target repo (default: cwd)
  rebuild [--changed]      Rebuild .context/ (use --changed for incremental)
  bootstrap [path]         Write/regenerate the CLAUDE.md managed block

Run `dummyindex context <subcommand> --help` for subcommand help.
"""


def dispatch(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    subcmd, rest = argv[0], argv[1:]
    handler = _HANDLERS.get(subcmd)
    if handler is None:
        print(f"error: unknown context subcommand '{subcmd}'", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    return handler(rest)


def _cmd_init(args: list[str]) -> int:
    from dummyindex.context.runner import build_all

    target = Path(args[0]) if args and not args[0].startswith("--") else Path(".")
    try:
        from importlib.metadata import version
        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"
    result = build_all(target, bootstrap=True, dummyindex_version=di_version)
    print(f"context init: wrote {len(result.written)} files to {result.context_dir}")
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    if result.languages:
        print(f"  languages: {', '.join(result.languages)}")
    if result.bootstrapped:
        print(f"  CLAUDE.md  ->  managed block written")
    return 0


def _cmd_rebuild(args: list[str]) -> int:
    changed_only = "--changed" in args
    # Allow `rebuild [--changed] [path]` in either order
    path_args = [a for a in args if not a.startswith("--")]
    target = Path(path_args[0]) if path_args else Path(".")
    try:
        from importlib.metadata import version
        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    if changed_only:
        from dummyindex.context.incremental import rebuild_changed
        result = rebuild_changed(target, dummyindex_version=di_version)
        if result.skipped:
            print("context rebuild: no source files changed; .context/ unchanged.")
            return 0
        ch = result.changes
        print(
            f"context rebuild: {len(ch.added)} added, {len(ch.modified)} modified, "
            f"{len(ch.removed)} removed → rebuilt {result.build_result.context_dir}"
            if result.build_result else "rebuild ran"
        )
        return 0
    from dummyindex.context.runner import build_all
    result = build_all(target, dummyindex_version=di_version)
    print(f"context rebuild: wrote {len(result.written)} files to {result.context_dir}")
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    return 0


def _cmd_bootstrap(args: list[str]) -> int:
    from dummyindex.context.bootstrap import (
        UnbalancedMarkersError,
        bootstrap_claude_md,
    )

    target = Path(args[0]) if args else Path(".")
    claude_md = target / "CLAUDE.md"
    try:
        bootstrap_claude_md(claude_md)
    except UnbalancedMarkersError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(f"CLAUDE.md  ->  managed block written: {claude_md.resolve()}")
    return 0


_HANDLERS: dict[str, Callable[[list[str]], int]] = {
    "init": _cmd_init,
    "rebuild": _cmd_rebuild,
    "bootstrap": _cmd_bootstrap,
}
