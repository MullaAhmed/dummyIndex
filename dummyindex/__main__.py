"""dummyindex CLI — thin entrypoint dispatching to the real surfaces.

Two surfaces:

1. `dummyindex install [--scope user|project] [--dir PATH] [--skill-only]`
   — copy the skill into Claude Code's skills directory (user-global at
   `~/.claude/skills/dummyindex/SKILL.md`, or per-repo at
   `<PATH>/.claude/skills/dummyindex/SKILL.md`). When the resolved
   project candidate (``--dir`` if given, else CWD) is a git repo, this
   also runs the full project init: builds ``.context/``, writes a
   managed CLAUDE.md block, and installs the SessionStart drift hook.
   Pass ``--skill-only`` to opt out of the project init step.
   The implementation lives in ``dummyindex/installer/``.
2. `dummyindex ingest <path>` (a.k.a. `dummyindex context init <path>`) —
   stand-alone project init for cases where ``install`` already ran or
   you need to init a directory other than the one you installed from.

`dummyindex context <subcommand>` covers the rest of the surface —
incremental rebuilds, retrieval (`query`), enrichment, session memory,
and the v0.15 build loop (`propose` / `equip` / `build`). Run
`dummyindex context --help` for the full list.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dummyindex.installer import (
    PACKAGE_VERSION as __version__,
    parse_install_args,
    install,
    uninstall,
)


def _run_usage(args: list[str]) -> int:
    """`dummyindex usage [chat|daily|session|monthly|blocks]` — token report.

    Thin CLI boundary: parse the kind, call the usage domain, print the
    rendered string. Mirrors the top-level `install`/`uninstall` pattern
    (logic in the domain package, print + exit codes here).
    """
    import datetime as _dt

    from dummyindex.usage import (
        ReportKind,
        UsageError,
        build_report,
        default_projects_root,
        resolve_session_id,
    )

    kind = ReportKind.CHAT
    if args:
        if args[0] in ("-h", "--help"):
            print("Usage: dummyindex usage [chat|daily|session|monthly|blocks]")
            return 0
        try:
            kind = ReportKind(args[0])
        except ValueError:
            valid = ", ".join(k.value for k in ReportKind)
            print(
                f"error: unknown usage report {args[0]!r} (choose: {valid})",
                file=sys.stderr,
            )
            return 2
        rest = args[1:]
        if rest:
            print(f"error: unexpected argument(s): {rest}", file=sys.stderr)
            return 2

    try:
        text = build_report(
            kind,
            projects_root=default_projects_root(),
            now=_dt.datetime.now(_dt.timezone.utc),
            session_id=resolve_session_id(),
            cwd=Path.cwd(),
        )
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(text)
    return 0


def _print_help() -> None:
    print("Usage: dummyindex <command> [args]")
    print()
    print("Commands:")
    print("  install [--scope user|project] [--dir PATH] [--skill-only]")
    print("          [--no-onboarding] [--defaults]")
    print("                            install the Claude Code skill, and — when the")
    print(
        "                            target dir is a git repo — also build .context/,"
    )
    print(
        "                            write CLAUDE.md, and install the SessionStart drift hook."
    )
    print(
        "                            user scope (default): ~/.claude/skills/dummyindex/SKILL.md"
    )
    print(
        "                            project scope:        <PATH>/.claude/skills/dummyindex/SKILL.md"
    )
    print(
        "                            --skill-only         suppress the project init step"
    )
    print("                                                 (just register the skill).")
    print("                            --defaults / --no-onboarding")
    print(
        "                                                 write a default .context/config.json"
    )
    print(
        "                                                 non-interactively (CI/scripted) so the"
    )
    print(
        "                                                 skill skips its onboarding questions."
    )
    print("  uninstall [--scope user|project] [--dir PATH]")
    print("                            remove the Claude Code skill")
    print()
    print("  ingest [path] [--root DIR] [--docs PATH]...")
    print(
        "                            index <path> into <root>/.context/ + write <root>/.claude/CLAUDE.md"
    )
    print("                            (alias for `context init`; default path: cwd)")
    print(
        "                            Smart default: when <path> is a relative subdir of cwd,"
    )
    print(
        "                            <root> = cwd (the enclosing repo). Use --root to override."
    )
    print(
        "                            --docs PATH (repeatable) adds external doc roots; in-repo"
    )
    print("                            docs are auto-discovered.")
    print()
    print("  context init [path] [--root DIR] [--docs PATH]...   same as `ingest`")
    print("  context rebuild [--changed] [path] [--root DIR] [--docs PATH]...")
    print("                            rebuild .context/")
    print(
        "  context bootstrap [path] [--root DIR]            regenerate CLAUDE.md block only"
    )
    print(
        "  context enrich-plan [path] [--root DIR]          emit .context/cache/_enrich_plan.json"
    )
    print("  context enrich-apply [path] [--root DIR] --from-json FILE")
    print("                            merge {node_id: abstract} JSON into tree.json")
    print(
        '  context features-rename [--root DIR] --from ID --to ID [--name "..."] [--summary "..."]'
    )
    print(
        "                            atomically rename a feature folder and update all JSON refs"
    )
    print("  context refresh-indexes [path] [--root DIR]")
    print(
        "                            rebuild .context/INDEX.md from disk (call after enrichment)"
    )
    print('  context query "..." [--root DIR] [--top-k N] [--json]')
    print(
        "                            ranked feature shortlist for a query (PageIndex-style, no LLM)"
    )
    print()
    print(
        "  context <subcommand>      full list + flags: run `dummyindex context --help`. Others:"
    )
    _detailed = {
        "init", "rebuild", "bootstrap", "enrich-plan", "enrich-apply",
        "features-rename", "refresh-indexes", "query",
    }
    try:
        # Lazy import (only runs on --help). Derived from the enum so this
        # list can never drift when a subcommand is added.
        from dummyindex.context.enums import ContextSubcommand

        _others = ", ".join(
            sorted(s.value for s in ContextSubcommand if s.value not in _detailed)
        )
    except Exception:  # pragma: no cover — help must never crash
        _others = "(see `dummyindex context --help`)"
    import textwrap

    # break_on_hyphens=False: never split a subcommand name like
    # "council-log" across lines.
    for _line in textwrap.wrap(_others, width=50, break_on_hyphens=False):
        print(f"                            {_line}")
    print()
    print("  usage [chat|daily|session|monthly|blocks]")
    print("                            token usage from Claude Code transcripts.")
    print(
        "                            chat (default): this session — context window now +"
    )
    print(
        "                            deduplicated totals incl. subagents (the /tokens command)."
    )
    print(
        "                            daily/session/monthly/blocks: aggregate every project."
    )
    print()
    print("  --version, -V             print version")
    print("  --help, -h                show this message")
    print()


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _print_help()
        return

    cmd = sys.argv[1]

    if cmd in ("--version", "-V"):
        print(__version__)
        return

    if cmd == "install":
        scope, project_dir, skill_only, no_onboarding, defaults = parse_install_args(
            sys.argv[2:]
        )
        install(
            scope=scope,
            project_dir=project_dir,
            skill_only=skill_only,
            no_onboarding=no_onboarding,
            defaults=defaults,
        )
        return

    if cmd == "uninstall":
        scope, project_dir, *_rest = parse_install_args(sys.argv[2:])
        uninstall(scope=scope, project_dir=project_dir)
        return

    if cmd == "usage":
        sys.exit(_run_usage(sys.argv[2:]))

    if cmd == "context":
        from dummyindex.cli import dispatch as _context_dispatch

        sys.exit(_context_dispatch(sys.argv[2:]))

    if cmd == "ingest":
        from dummyindex.cli import dispatch as _context_dispatch

        sys.exit(_context_dispatch(["init", *sys.argv[2:]]))

    print(f"error: unknown command {cmd!r}", file=sys.stderr)
    _print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
