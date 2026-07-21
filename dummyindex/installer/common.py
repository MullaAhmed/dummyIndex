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

_CODEX_SKILL_PREAMBLE = """\
## Codex host compatibility

This installed copy is running in **Codex**. The workflow body is shared with
the Claude Code edition; the rules below override Claude-specific vocabulary in
this file and in any companion markdown it asks you to read:

- Invoke skills with `$<skill-name>` (or select them through `/skills`). A
  `/dummyindex...` example is the equivalent Claude Code spelling, not a Codex
  slash command.
- Use Codex subagents for delegated work. Map a read-only/exploration task to
  `explorer`, an implementation task to `worker`, and any other unavailable
  named `subagent_type` or `general-purpose` agent to `default`. Inline the
  persona mandate in the delegated prompt. Do not try to call Claude's `Task`,
  `Agent`, or `Skill` tools by name.
- Treat companion references to Claude's `Read`, `Write`, `Edit`, `Bash`,
  `Glob`, or `Grep` as host vocabulary, not literal tool requirements. Use
  Codex's native file reading/search, shell, and patch/edit mechanisms while
  preserving read-before-edit and atomic-write requirements; do not look for
  tools with those Claude-specific names.
- When the workflow says `AskUserQuestion`, ask the user directly with the
  normal Codex input mechanism.
- Invoke another installed skill with `$<skill-name>`. Translate a binding
  `— via /<skill>` annotation to `— via $<skill>`.
- Claude's `/tokens` command is intentionally not copied: `dummyindex usage`
  parses Claude Code transcripts. For the active Codex session use Codex's
  native `/status` (context and session tokens) or `/usage` (account usage).
  Run `dummyindex usage` on Codex only when the user explicitly wants saved
  Claude Code transcript history.
- When onboarding or audit asks which model to use, offer `current` and use it
  for the running Codex model. It is the recommended Codex choice; Claude
  model labels in the shared workflow are only meaningful on Claude Code.
- dummyindex currently installs its managed session hooks only for Claude Code,
  even though Codex has its own hook system. For a Codex-only install, persist
  `--no-hook` when asked; durable project guidance comes from the active Codex
  project instruction file.
- Whenever this workflow runs `dummyindex ingest`, `dummyindex context init`,
  or `dummyindex install`, preserve the host selection it resolved: use
  `--platform codex` for a Codex-only integration and `--platform both` when
  the user intentionally maintains both hosts. Never fall back to the legacy
  Claude-only default merely because the shared example omitted the flag.
- Codex project guidance lives in the active project instruction file:
  `AGENTS.override.md`, `AGENTS.md`, or a configured fallback. Codex custom
  agents live in `.codex/agents/*.toml`. The
  `.claude/` hooks, agents, commands, and marketplace
  wiring generated by dummyindex are Claude integrations and must not block the
  core `.context/` indexing, planning, audit, build, memory, or GC workflows. If
  an equipped Claude agent is not available to Codex, use the built-in mapping
  above and preserve its mandate in the delegated prompt.

"""


def platforms_for(value: str) -> tuple[str, ...]:
    """Expand a validated platform selector to concrete host names."""
    if value == "both":
        return ("claude", "codex")
    if value in ("claude", "codex"):
        return (value,)
    choices = "|".join(SUPPORTED_PLATFORMS)
    raise ValueError(f"platform must be {choices}, got {value!r}")


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
    """Substitute the package version and add Codex's host vocabulary map."""
    rendered = text.replace("__VERSION__", PACKAGE_VERSION)
    if platform != "codex":
        return rendered

    # Keep YAML frontmatter at byte zero.  Codex requires name + description
    # there and ignores the body until the skill activates.
    if rendered.startswith("---\n"):
        close = rendered.find("\n---\n", 4)
        if close != -1:
            body_start = close + len("\n---\n")
            return (
                rendered[:body_start]
                + "\n"
                + _CODEX_SKILL_PREAMBLE
                + rendered[body_start:]
            )
    return _CODEX_SKILL_PREAMBLE + rendered


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
