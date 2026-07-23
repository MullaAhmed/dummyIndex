"""Shared installer constants + host-aware skill/command helpers."""

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

SUPPORTED_PLATFORMS = ("claude", "codex", "both")

# Where the Claude Code skill lives, relative to the scope root.
# user scope     -> $HOME / SKILL_REL    = ~/.claude/skills/dummyindex/SKILL.md
# project scope  -> <cwd> / SKILL_REL    = <cwd>/.claude/skills/dummyindex/SKILL.md
SKILL_REL = Path(".claude") / "skills" / "dummyindex" / "SKILL.md"

# Codex follows the open Agent Skills convention.  Current Codex releases scan
# ``.agents/skills`` at both user and repository scope; ``~/.codex/skills`` is a
# legacy/community convention and is intentionally not used here.
CODEX_SKILL_REL = Path(".agents") / "skills" / "dummyindex" / "SKILL.md"

# ``.agents/skills`` is the cross-harness Agent Skills location, not a
# Codex-only one (Cursor, Copilot CLI, OpenCode, Amp, Gemini CLI/Antigravity,
# Goose, Pi, and Cline all scan it too). Same path, host-neutral name; the
# internal ``"codex"`` token is unchanged everywhere else.
AGENTS_SKILL_REL = CODEX_SKILL_REL

# Bundled slash commands copied into <scope>/.claude/commands/ on install.
# Currently just /tokens, which shells out to `dummyindex usage`.
_COMMAND_FILES = ("tokens.md",)
COMMANDS_REL = Path(".claude") / "commands"

_SIBLING_SKILLS = (
    ("memory", "dummyindex-remember"),
    ("plan", "dummyindex-plan"),
    ("equip", "dummyindex-equip"),
    ("build", "dummyindex-build"),
    ("audit", "dummyindex-audit"),
    ("gc", "dummyindex-gc"),
    ("update", "dummyindex-update"),
)


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

_PORTABLE_HOST_PREAMBLE = """\
## Portable host compatibility

This installed copy is shared by every host that discovers `.agents/skills`,
not one specific product. Identify your host, then apply the one matching row
below — these rules override Claude-specific vocabulary in this file and in
any companion markdown it asks you to read:

1. **Claude Code** — this is native vocabulary for you. When both this copy
   and the `.claude/skills` copy of the same skill are installed, prefer the
   `.claude/skills` copy.
2. **Skill-native hosts** — your host exposes installed skills plus named or
   generic subagents (examples: Codex, Cursor, Copilot CLI, OpenCode, Amp,
   Gemini CLI/Antigravity, Goose, Pi, Cline). Invoke this skill, and any
   companion skill it names, through your host's own skill mechanism rather
   than Claude's `Skill` tool. Delegate implementation and exploration work to
   your host's native subagents, inlining the persona mandate this workflow
   describes into the delegated prompt instead of looking for a named Claude
   subagent type.
3. **Generic fallback** — no skill runner, no named subagents. Use your
   native file, search, and shell tools directly and treat every Claude tool
   name in this workflow (`Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`,
   `Task`, `Agent`, `AskUserQuestion`) as vocabulary, not a requirement —
   ask the user directly instead of `AskUserQuestion` when the workflow calls
   for a choice, and never write `.claude/**`: that tree belongs to a real
   Claude Code install and this row has no way to keep it correct.

"""


def platforms_for(value: str) -> tuple[str, ...]:
    """Expand a validated platform selector to concrete host names."""
    if value == "both":
        return ("claude", "codex")
    if value in ("claude", "codex"):
        return (value,)
    choices = "|".join(SUPPORTED_PLATFORMS)
    raise ValueError(f"platform must be {choices}, got {value!r}")


# Set once the deprecated ``codex`` platform alias has printed its stderr
# notice, so a process that calls :func:`normalize_platform_arg` many times
# (repeated CLI invocations, batch installs) warns exactly once.
_CODEX_PLATFORM_ALIAS_WARNED = False


def normalize_platform_arg(value: str) -> str:
    """Map the public ``--platform`` selector to the installer's internal token.

    Accepts the public vocabulary ``claude|agents|both`` plus the deprecated
    ``codex`` alias, and returns the existing internal platform token unchanged
    everywhere else in the installer (``agents`` -> ``"codex"``;
    ``SUPPORTED_PLATFORMS``, :func:`platforms_for`, and every internal
    ``"codex"`` comparison are untouched by this alias). Passing the legacy
    ``codex`` spelling prints a one-time deprecation notice to stderr — the
    module-level guard ensures repeated calls in one process warn only once.
    """
    global _CODEX_PLATFORM_ALIAS_WARNED
    if value == "agents":
        return "codex"
    if value in ("claude", "both"):
        return value
    if value == "codex":
        if not _CODEX_PLATFORM_ALIAS_WARNED:
            print(
                "warning: --platform codex is deprecated, use --platform agents",
                file=sys.stderr,
            )
            _CODEX_PLATFORM_ALIAS_WARNED = True
        return "codex"
    raise ValueError(f"platform must be claude|agents|both, got {value!r}")


def skill_rel(platform: str) -> Path:
    """Main skill destination relative to a user/project scope root."""
    if platform == "claude":
        return SKILL_REL
    if platform == "codex":
        return CODEX_SKILL_REL
    raise ValueError(f"concrete platform required, got {platform!r}")


def skills_root_rel(platform: str) -> Path:
    return skill_rel(platform).parent.parent


def render_skill(text: str, *, platform: str) -> str:
    """Substitute the package version and add the portable-host preamble."""
    rendered = text.replace("__VERSION__", PACKAGE_VERSION)
    if platform != "codex":
        return rendered

    # Keep YAML frontmatter at byte zero.  Codex (and every other Agent
    # Skills host) requires name + description there and ignores the body
    # until the skill activates.
    if rendered.startswith("---\n"):
        close = rendered.find("\n---\n", 4)
        if close != -1:
            body_start = close + len("\n---\n")
            return (
                rendered[:body_start]
                + "\n"
                + _PORTABLE_HOST_PREAMBLE
                + rendered[body_start:]
            )
    return _PORTABLE_HOST_PREAMBLE + rendered


def _skill_src(name: str = "skill.md") -> Path:
    return _SKILLS_DIR / name


def _install_commands(
    base: Path, *, allowed_symlinks: frozenset[Path] = frozenset()
) -> list[str]:
    """Copy bundled slash commands into ``<base>/.claude/commands/``.

    Returns the filenames copied. Best-effort per file: a missing source (an
    incomplete package build) is skipped with a stderr note rather than
    failing the whole install.
    """
    commands_dir = base / COMMANDS_REL
    linked_parent = _first_symlink_component(
        base, commands_dir, allowed_symlinks=allowed_symlinks
    )
    if linked_parent is not None:
        print(
            f"  commands skipped: refusing to write through directory symlink "
            f"{linked_parent}",
            file=sys.stderr,
        )
        return []
    copied: list[str] = []
    for name in _COMMAND_FILES:
        src = _SKILLS_DIR / "commands" / name
        if not src.exists():
            print(f"  command skipped: {src} not found", file=sys.stderr)
            continue
        commands_dir.mkdir(parents=True, exist_ok=True)
        target = commands_dir / name
        if target.is_symlink():
            # Replace only the scoped link, never the file it points at.
            target.unlink()
        shutil.copy(src, target)
        copied.append(name)
    return copied


def remove_commands(
    base: Path, *, allowed_symlinks: frozenset[Path] = frozenset()
) -> list[str]:
    """Remove the bundled slash commands from ``<base>/.claude/commands/``."""
    commands_dir = base / COMMANDS_REL
    if (
        _first_symlink_component(base, commands_dir, allowed_symlinks=allowed_symlinks)
        is not None
    ):
        return []
    removed: list[str] = []
    for name in _COMMAND_FILES:
        target = commands_dir / name
        if target.exists() or target.is_symlink():
            target.unlink()
            removed.append(name)
    return removed


def _first_symlink_component(
    base: Path,
    path: Path,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> Path | None:
    """First non-allowlisted symlink below ``base`` on the way to ``path``."""
    current = base
    try:
        relative = path.relative_to(base)
    except ValueError:
        return None
    for part in relative.parts:
        current = current / part
        if current.is_symlink() and current not in allowed_symlinks:
            return current
    return None
