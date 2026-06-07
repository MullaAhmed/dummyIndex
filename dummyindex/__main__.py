"""dummyindex CLI — Claude Code skill installer + context-engine entry point.

Two surfaces:

1. `dummyindex install [--scope user|project] [--dir PATH] [--skill-only]`
   — copy the skill into Claude Code's skills directory (user-global at
   `~/.claude/skills/dummyindex/SKILL.md`, or per-repo at
   `<PATH>/.claude/skills/dummyindex/SKILL.md`). When the resolved
   project candidate (``--dir`` if given, else CWD) is a git repo, this
   also runs the full project init: builds ``.context/``, writes a
   managed CLAUDE.md block, and installs the SessionStart drift hook.
   Pass ``--skill-only`` to opt out of the project init step.
2. `dummyindex ingest <path>` (a.k.a. `dummyindex context init <path>`) —
   stand-alone project init for cases where ``install`` already ran or
   you need to init a directory other than the one you installed from.

`dummyindex context <subcommand>` covers the rest of the surface —
incremental rebuilds, retrieval (`query`), enrichment, session memory,
and the v0.15 build loop (`propose` / `equip` / `build`). Run
`dummyindex context --help` for the full list.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional


try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("dummyindex")
except Exception:
    __version__ = "unknown"


_SKILLS_DIR = Path(__file__).with_name("skills")

# Where the Claude Code skill lives, relative to the scope root.
# user scope     -> $HOME / SKILL_REL    = ~/.claude/skills/dummyindex/SKILL.md
# project scope  -> <cwd> / SKILL_REL    = <cwd>/.claude/skills/dummyindex/SKILL.md
SKILL_REL = Path(".claude") / "skills" / "dummyindex" / "SKILL.md"

# Bundled slash commands copied into <scope>/.claude/commands/ on install.
# Currently just /tokens, which shells out to `dummyindex usage`.
_COMMAND_FILES = ("tokens.md",)
COMMANDS_REL = Path(".claude") / "commands"


_SKILL_REGISTRATION = (
    "\n# dummyindex\n"
    "- **dummyindex** (`~/.claude/skills/dummyindex/SKILL.md`) - index any "
    "codebase into `.context/`. Trigger: `/dummyindex` or `/dummyindex <path>`.\n"
    "When the user types `/dummyindex`, invoke the Skill tool with "
    '`skill: "dummyindex"` before doing anything else.\n'
    "When working in a directory that has a `.context/` folder, consult "
    "`.context/HOW_TO_USE.md` first, then the index files it points to "
    "(`PROJECT.md`, `architecture/overview.md`, `map/symbols.json`, "
    "`tree.json`, `conventions/naming.md`, `playbooks/*.md`) before "
    "grepping or opening source files at random.\n"
)


def _skill_src(name: str = "skill.md") -> Path:
    return _SKILLS_DIR / name


def _install_commands(base: Path) -> list[str]:
    """Copy bundled slash commands into ``<base>/.claude/commands/``.

    Returns the filenames copied. Best-effort per file: a missing source (an
    incomplete package build) is skipped with a stderr note rather than
    failing the whole install.
    """
    commands_dir = base / COMMANDS_REL
    copied: list[str] = []
    for name in _COMMAND_FILES:
        src = _SKILLS_DIR / "commands" / name
        if not src.exists():
            print(f"  command skipped: {src} not found", file=sys.stderr)
            continue
        commands_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, commands_dir / name)
        copied.append(name)
    return copied


def _remove_commands(base: Path) -> list[str]:
    """Remove the bundled slash commands from ``<base>/.claude/commands/``."""
    commands_dir = base / COMMANDS_REL
    removed: list[str] = []
    for name in _COMMAND_FILES:
        target = commands_dir / name
        if target.exists():
            target.unlink()
            removed.append(name)
    return removed


def install(
    *,
    scope: str = "user",
    project_dir: Optional[Path] = None,
    skill_only: bool = False,
    no_onboarding: bool = False,
    defaults: bool = False,
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
        src.read_text(encoding="utf-8").replace("__VERSION__", __version__),
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
            mem_src.read_text(encoding="utf-8").replace("__VERSION__", __version__),
            encoding="utf-8",
        )
        print(f"  memory skill     ->  {mem_dst}")

    # Build-loop skills — each its OWN top-level skill dir (siblings of
    # /dummyindex), so Claude Code discovers /dummyindex-plan|equip|build.
    for sub_name, skill_label in (
        ("plan", "dummyindex-plan"),
        ("equip", "dummyindex-equip"),
        ("build", "dummyindex-build"),
    ):
        bl_src = _SKILLS_DIR / sub_name / "SKILL.md"
        if not bl_src.is_file():
            continue
        bl_dst = base / ".claude" / "skills" / skill_label / "SKILL.md"
        bl_dst.parent.mkdir(parents=True, exist_ok=True)
        bl_dst.write_text(
            bl_src.read_text(encoding="utf-8").replace("__VERSION__", __version__),
            encoding="utf-8",
        )
        # equip ships render templates alongside its SKILL.md.
        tmpl_src = _SKILLS_DIR / sub_name / "templates"
        if tmpl_src.is_dir():
            tmpl_dst = bl_dst.parent / "templates"
            tmpl_dst.mkdir(parents=True, exist_ok=True)
            # Copy everything shipped under templates/ (mirrors the
            # pyproject package-data glob `templates/*`, so a non-.tmpl
            # template can never ship-but-not-install).
            for tmpl in sorted(tmpl_src.glob("*")):
                if tmpl.is_file():
                    shutil.copy(tmpl, tmpl_dst / tmpl.name)
        print(f"  build-loop skill ->  {bl_dst}")

    (skill_dir / ".dummyindex_version").write_text(__version__, encoding="utf-8")
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
            if "dummyindex" in content:
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
        init_ran = _auto_init_project(auto_init_target)
        if init_ran and (defaults or no_onboarding):
            _write_default_config(auto_init_target)

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


def _auto_init_project(project_root: Path) -> bool:
    """Run the same flow as `dummyindex context init <project_root>`:
    build the deterministic backbone into ``.context/``, write the
    managed CLAUDE.md block, and install the SessionStart drift hook.

    Returns True on success, False on any failure (printed to stderr but
    not raised — the skill install itself already succeeded, and we
    don't want to make the whole command exit non-zero just because a
    secondary project-init step hit a snag).
    """
    try:
        from dummyindex.context.build.runner import build_all
        from dummyindex.context.hooks import install as install_hooks_fn
    except Exception as exc:
        print(f"  auto-init skipped: import failed ({exc})", file=sys.stderr)
        return False

    try:
        di_version = _pkg_version("dummyindex")
    except Exception:
        di_version = "unknown"

    try:
        result = build_all(
            project_root,
            out_root=project_root,
            bootstrap=True,
            dummyindex_version=di_version,
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


def uninstall(*, scope: str = "user", project_dir: Optional[Path] = None) -> None:
    """Remove the skill (and version stamp) from the chosen scope."""
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be 'user' or 'project', got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    dst = base / SKILL_REL  # ~/.claude/skills/dummyindex/SKILL.md
    skill_dir = dst.parent  # ~/.claude/skills/dummyindex/

    removed: list[str] = []
    if dst.exists():
        dst.unlink()
        removed.append(str(dst))

    # Remove every companion markdown installed alongside.
    for subdir in ("agents", "council", "retrieval"):
        sub_dst = skill_dir / subdir
        if sub_dst.is_dir():
            for md in sub_dst.glob("*.md"):
                md.unlink()
            try:
                sub_dst.rmdir()
            except OSError:
                pass

    version_file = skill_dir / ".dummyindex_version"
    if version_file.exists():
        version_file.unlink()

    # Sibling top-level skills (memory + build-loop) live in their own dirs.
    skills_root = base / ".claude" / "skills"
    for sibling in ("dummyindex-remember", "dummyindex-plan", "dummyindex-equip", "dummyindex-build"):
        sib_dir = skills_root / sibling
        if not sib_dir.is_dir():
            continue
        for path in sorted(sib_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            sib_dir.rmdir()
        except OSError:
            pass
        removed.append(str(sib_dir))

    for name in _remove_commands(base):
        removed.append(str(base / COMMANDS_REL / name))

    # Best-effort: remove now-empty parent directories up to the scope root,
    # stopping at the first non-empty one.
    for d in (skill_dir, skill_dir.parent, skill_dir.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break

    if removed:
        print(f"  skill removed  ->  {removed[0]}")
    else:
        print("nothing to remove")


def _parse_install_args(
    args: list[str],
) -> tuple[str, Optional[Path], bool, bool, bool]:
    scope = "user"
    project_dir: Optional[Path] = None
    skill_only = False
    no_onboarding = False
    defaults = False
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--scope="):
            scope = a.split("=", 1)[1]
            i += 1
        elif a == "--scope" and i + 1 < len(args):
            scope = args[i + 1]
            i += 2
        elif a.startswith("--dir="):
            project_dir = Path(a.split("=", 1)[1])
            i += 1
        elif a == "--dir" and i + 1 < len(args):
            project_dir = Path(args[i + 1])
            i += 2
        elif a == "--skill-only":
            skill_only = True
            i += 1
        elif a == "--no-onboarding":
            no_onboarding = True
            i += 1
        elif a == "--defaults":
            defaults = True
            i += 1
        elif a in ("--platform", "--platform=claude") or a.startswith("--platform="):
            # Legacy v1 flag — the multi-platform installers are gone.
            # Skip silently so old `dummyindex install --platform claude`
            # docs continue to "just work" instead of erroring.
            if a == "--platform" and i + 1 < len(args):
                i += 2
            else:
                i += 1
        else:
            print(f"error: unknown install argument {a!r}", file=sys.stderr)
            sys.exit(2)
    return scope, project_dir, skill_only, no_onboarding, defaults


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
        scope, project_dir, skill_only, no_onboarding, defaults = _parse_install_args(
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
        scope, project_dir, *_rest = _parse_install_args(sys.argv[2:])
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
