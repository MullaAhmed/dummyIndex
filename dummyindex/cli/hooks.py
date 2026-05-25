"""`dummyindex context hooks` — install / uninstall / status the auto-refresh hooks."""
from __future__ import annotations
import sys
from ._common import _parse_path_and_root, _resolve_context_root


def _cmd_hooks(args: list[str]) -> int:
    """Manage auto-refresh hooks: install | uninstall | status."""
    from dummyindex.context.hooks import (
        install as hooks_install,
        status as hooks_status,
        uninstall as hooks_uninstall,
    )

    if not args:
        print("error: usage: dummyindex context hooks install|uninstall|status", file=sys.stderr)
        return 2

    verb, rest = args[0], args[1:]
    if verb not in ("install", "uninstall", "status"):
        print(f"error: unknown hooks verb {verb!r}", file=sys.stderr)
        return 2

    scope, explicit_root, leftover = _parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2

    project_root = _resolve_context_root(scope, explicit_root=explicit_root)

    if verb == "install":
        result = hooks_install(project_root)
        if result.installed:
            print(f"hooks install: installed {', '.join(result.installed)}")
        if result.skipped:
            print(f"hooks install: skipped (already current): {', '.join(result.skipped)}")
        for name, err in result.errors:
            print(f"  error ({name}): {err}", file=sys.stderr)
        return 0 if not result.errors else 1
    if verb == "uninstall":
        result = hooks_uninstall(project_root)
        if result.removed:
            print(f"hooks uninstall: removed {', '.join(result.removed)}")
        if result.skipped:
            print(f"hooks uninstall: skipped: {', '.join(result.skipped)}")
        for name, err in result.errors:
            print(f"  error ({name}): {err}", file=sys.stderr)
        return 0 if not result.errors else 1
    # status
    s = hooks_status(project_root)
    print(f"hooks status @ {project_root}")
    print(f"  git/post-commit       {'✓' if s.git_post_commit else '✗'}")
    print(f"  claude/PostToolUse    {'✓' if s.claude_post_tool_use else '✗'}")
    print(f"  claude/SessionStart   {'✓' if s.claude_session_start else '✗'}")
    return 0 if s.all_installed else 1

