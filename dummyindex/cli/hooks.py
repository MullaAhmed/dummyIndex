"""`dummyindex context hooks` — manage dummyindex's Claude Code session hooks."""

from __future__ import annotations

import sys

from .common import parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    """Manage the session hooks: install | uninstall | status | defer-check.

    ``--global`` targets ``~/.claude/settings.json`` (default ``--local`` =
    the repo's ``.claude/settings.json``). ``defer-check`` is a pure exit-code
    probe used by the global hook guard: exit 0 when the repo has its own
    ``--local`` install (so the global hook should yield), else exit 1.
    """
    from dummyindex.context.hooks import (
        install as hooks_install,
    )
    from dummyindex.context.hooks import (
        local_install_present,
    )
    from dummyindex.context.hooks import (
        status as hooks_status,
    )
    from dummyindex.context.hooks import (
        uninstall as hooks_uninstall,
    )

    if not args:
        print(
            "error: usage: dummyindex context hooks "
            "install|uninstall|status|defer-check [--global]",
            file=sys.stderr,
        )
        return 2

    verb, rest = args[0], args[1:]
    if verb not in ("install", "uninstall", "status", "defer-check"):
        print(f"error: unknown hooks verb {verb!r}", file=sys.stderr)
        return 2

    # Pull the scope flag before path/root parsing so it isn't flagged leftover.
    scope = "local"
    pruned: list[str] = []
    for a in rest:
        if a == "--global":
            scope = "global"
        elif a == "--local":
            scope = "local"
        else:
            pruned.append(a)

    cfg_scope, explicit_root, leftover = parse_path_and_root(pruned)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2

    project_root = resolve_context_root(cfg_scope, explicit_root=explicit_root)

    if verb == "defer-check":
        # Silent probe: exit code is the whole contract.
        return 0 if local_install_present(project_root) else 1
    if verb == "install":
        result = hooks_install(project_root, scope=scope)
        if result.installed:
            print(f"hooks install: installed {', '.join(result.installed)}")
        if result.refreshed:
            print(
                "hooks install: refreshed (body updated): "
                f"{', '.join(result.refreshed)}"
            )
        if result.skipped:
            print(
                f"hooks install: skipped (already current): {', '.join(result.skipped)}"
            )
        # Emit-only advisories (e.g. the statusLine nudge): surface them so the
        # computed nudge actually reaches the user. install() never writes them.
        for nudge in result.nudges:
            print(f"  {nudge}")
        for name, err in result.errors:
            print(f"  error ({name}): {err}", file=sys.stderr)
        return 0 if not result.errors else 1
    if verb == "uninstall":
        result = hooks_uninstall(project_root, scope=scope)
        if result.removed:
            print(f"hooks uninstall: removed {', '.join(result.removed)}")
        if result.skipped:
            print(f"hooks uninstall: skipped: {', '.join(result.skipped)}")
        for name, err in result.errors:
            print(f"  error ({name}): {err}", file=sys.stderr)
        return 0 if not result.errors else 1
    # status
    s = hooks_status(project_root, scope=scope)
    print(f"hooks status @ {project_root} (scope={scope})")
    print(f"  claude/SessionStart   {'✓' if s.claude_session_start else '✗'}")
    print(f"  claude/Stop           {'✓' if s.claude_stop else '✗'}")
    print(f"  claude/PreCompact     {'✓' if s.claude_pre_compact else '✗'}")
    print(f"  claude/PreToolUse     {'✓' if s.claude_pre_tool_use else '✗'}")
    return 0 if s.all_installed else 1
