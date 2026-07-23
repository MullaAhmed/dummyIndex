"""`dummyindex context bootstrap` — regenerate selected host guidance."""

from __future__ import annotations

import sys

from .common import parse_path_and_root, pull_repeatable_flag, resolve_context_root


def run(args: list[str]) -> int:
    from dummyindex.context.output.bootstrap import (
        bootstrap_claude_md,
        ensure_guidance_target_in_scope,
        preflight_claude_md,
    )
    from dummyindex.installer.common import normalize_platform_arg

    scope, explicit_root, rest = parse_path_and_root(args)
    platform_values, rest = pull_repeatable_flag(rest, "platform")
    if rest:
        print(f"error: unknown argument(s) for `bootstrap`: {rest}", file=sys.stderr)
        return 2
    if len(platform_values) > 1:
        print("error: --platform may be specified only once", file=sys.stderr)
        return 2
    platform = platform_values[0] if platform_values else "claude"
    try:
        platform = normalize_platform_arg(platform)
    except ValueError:
        print(
            f"error: --platform must be claude|agents|both, got {platform!r}",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    claude_md = out_root / ".claude" / "CLAUDE.md"
    if platform in {"codex", "both"}:
        from dummyindex.context.output.agents_md import (
            bootstrap_project_agents_md,
            preflight_project_agents_md,
        )

    # ``both`` is a single user operation. Validate both existing targets,
    # marker layouts, symlink boundaries, Codex ownership, and byte budget
    # before either host file changes. Filesystem state can still race after
    # this point, but every deterministic conflict is reported atomically.
    if platform == "both":
        try:
            ensure_guidance_target_in_scope(out_root, claude_md)
            preflight_claude_md(claude_md)
            preflight_project_agents_md(out_root)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3

    if platform in {"claude", "both"}:
        try:
            ensure_guidance_target_in_scope(out_root, claude_md)
            bootstrap_claude_md(claude_md)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(f"CLAUDE.md  ->  managed block written: {claude_md.resolve()}")

    if platform in {"codex", "both"}:
        try:
            agents_path = bootstrap_project_agents_md(out_root)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 3
        print(f"Codex guidance  ->  managed block written: {agents_path}")

    return 0
