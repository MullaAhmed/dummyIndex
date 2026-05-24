"""dummyindex CLI — Claude Code skill installer + context-engine entry point.

Two surfaces:

1. `dummyindex install [--scope user|project] [--dir PATH]` — copy the
   skill into Claude Code's skills directory (user-global at
   `~/.claude/skills/dummyindex/SKILL.md`, or per-repo at
   `<PATH>/.claude/skills/dummyindex/SKILL.md`).
2. `dummyindex ingest <path>` (a.k.a. `dummyindex context init <path>`) —
   run the deterministic backbone: detect → extract → build_structure
   → tree.json / map / conventions / graph / playbooks + a managed
   block in `<path>/CLAUDE.md`. The `/dummyindex` skill then does the
   LLM-driven enrichment on top of that.

`dummyindex context rebuild|bootstrap|enrich-plan|enrich-apply` are
additional subcommands for incremental refresh, re-bootstrapping just
the CLAUDE.md block, and the enrichment work-list/writeback.
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


def install(*, scope: str = "user", project_dir: Optional[Path] = None) -> None:
    """Copy the skill into Claude Code's skills directory.

    scope="user"    -> ~/.claude/skills/dummyindex/SKILL.md  (default)
    scope="project" -> <project_dir>/.claude/skills/dummyindex/SKILL.md
                       (project_dir defaults to CWD)
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

    base = (
        (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    )
    dst = base / SKILL_REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    (dst.parent / ".dummyindex_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {dst}")

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

    print()
    if scope == "project":
        target = (project_dir or Path(".")).resolve()
        print(f"Done. Open Claude Code in {target} and type:")
    else:
        print("Done. Open Claude Code and type:")
    print()
    print("  /dummyindex .")
    print()


def uninstall(*, scope: str = "user", project_dir: Optional[Path] = None) -> None:
    """Remove the skill (and version stamp) from the chosen scope."""
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be 'user' or 'project', got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (
        (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    )
    dst = base / SKILL_REL

    removed: list[str] = []
    if dst.exists():
        dst.unlink()
        removed.append(str(dst))
    version_file = dst.parent / ".dummyindex_version"
    if version_file.exists():
        version_file.unlink()

    # Best-effort: remove now-empty parent directories up to the scope root,
    # stopping at the first non-empty one.
    for d in (dst.parent, dst.parent.parent, dst.parent.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break

    if removed:
        print(f"  skill removed  ->  {removed[0]}")
    else:
        print("nothing to remove")


def _parse_install_args(args: list[str]) -> tuple[str, Optional[Path]]:
    scope = "user"
    project_dir: Optional[Path] = None
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
    return scope, project_dir


def _print_help() -> None:
    print("Usage: dummyindex <command> [args]")
    print()
    print("Commands:")
    print("  install [--scope user|project] [--dir PATH]")
    print("                            install the Claude Code skill")
    print(
        "                            user scope (default): ~/.claude/skills/dummyindex/SKILL.md"
    )
    print(
        "                            project scope:        <PATH>/.claude/skills/dummyindex/SKILL.md"
    )
    print("  uninstall [--scope user|project] [--dir PATH]")
    print("                            remove the Claude Code skill")
    print()
    print("  ingest [path] [--root DIR]")
    print("                            index <path> into <root>/.context/ + update CLAUDE.md")
    print("                            (alias for `context init`; default path: cwd)")
    print("                            Smart default: when <path> is a relative subdir of cwd,")
    print("                            <root> = cwd (the enclosing repo). Use --root to override.")
    print()
    print("  context init [path] [--root DIR]                 same as `ingest`")
    print("  context rebuild [--changed] [path] [--root DIR]  rebuild .context/")
    print("  context bootstrap [path] [--root DIR]            regenerate CLAUDE.md block only")
    print("  context enrich-plan [path] [--root DIR]          emit .context/_enrich_plan.json")
    print("  context enrich-apply [path] [--root DIR] --from-json FILE")
    print("                            merge {node_id: abstract} JSON into tree.json")
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
        scope, project_dir = _parse_install_args(sys.argv[2:])
        install(scope=scope, project_dir=project_dir)
        return

    if cmd == "uninstall":
        scope, project_dir = _parse_install_args(sys.argv[2:])
        uninstall(scope=scope, project_dir=project_dir)
        return

    if cmd == "context":
        from dummyindex.context.cli import dispatch as _context_dispatch

        sys.exit(_context_dispatch(sys.argv[2:]))

    if cmd == "ingest":
        from dummyindex.context.cli import dispatch as _context_dispatch

        sys.exit(_context_dispatch(["init", *sys.argv[2:]]))

    print(f"error: unknown command {cmd!r}", file=sys.stderr)
    _print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
