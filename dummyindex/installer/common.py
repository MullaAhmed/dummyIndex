"""Shared installer constants + bundled slash-command copy/remove helpers."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


try:
    from importlib.metadata import version as _pkg_version

    PACKAGE_VERSION = _pkg_version("dummyindex")
except Exception:
    PACKAGE_VERSION = "unknown"


_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

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


def remove_commands(base: Path) -> list[str]:
    """Remove the bundled slash commands from ``<base>/.claude/commands/``."""
    commands_dir = base / COMMANDS_REL
    removed: list[str] = []
    for name in _COMMAND_FILES:
        target = commands_dir / name
        if target.exists():
            target.unlink()
            removed.append(name)
    return removed
