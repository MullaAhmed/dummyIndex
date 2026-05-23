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
    target = Path(args[0]) if args else Path(".")
    print(
        f"context init: not yet implemented (target: {target.resolve()})",
        file=sys.stderr,
    )
    return 1


def _cmd_rebuild(args: list[str]) -> int:
    changed_only = "--changed" in args
    print(
        f"context rebuild: not yet implemented (changed_only={changed_only})",
        file=sys.stderr,
    )
    return 1


def _cmd_bootstrap(args: list[str]) -> int:
    target = Path(args[0]) if args else Path(".")
    print(
        f"context bootstrap: not yet implemented (target: {target.resolve()})",
        file=sys.stderr,
    )
    return 1


_HANDLERS: dict[str, Callable[[list[str]], int]] = {
    "init": _cmd_init,
    "rebuild": _cmd_rebuild,
    "bootstrap": _cmd_bootstrap,
}
