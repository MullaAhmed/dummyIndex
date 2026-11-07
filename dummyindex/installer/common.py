"""Shared installer constants + host-aware skill/command helpers."""

from __future__ import annotations

import re
import stat
import sys
from enum import Enum
from pathlib import Path

from ..versioning import compare_versions, parse_version

try:
    from importlib.metadata import version as _pkg_version

    PACKAGE_VERSION = _pkg_version("dummyindex")
except Exception:
    PACKAGE_VERSION = "unknown"


_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

SUPPORTED_PLATFORMS = ("claude", "codex", "both")

# Ownership evidence: a family main dir carries a version stamp file, or (for
# a copy installed before the portable-host rewrite) the legacy heading its
# rendered SKILL.md used to carry. See `is_owned_copy` below.
_VERSION_STAMP_NAME = ".dummyindex_version"
_LEGACY_CODEX_HEADING_RE = re.compile(r"(?m)^## Codex host compatibility\b")

# Matches a whole line carrying a `test-anchor:` HTML comment — the marker
# shape `tests/cli/test_cli_doc_sync_policy_canary.py` uses to delimit its
# region-scoped doc-drift canary in `dummyindex/skills/skill.md` (and, for
# consistency, the repo-internal `docs/COMMANDS.md` / `docs/guide/07-cli.md`
# copies). That marker namespace is deliberately test-only scaffolding, never
# a managed region any tool parses — unlike the reserved `dummyindex:*`
# comment namespace — so it must never leak into an installed skill. Narrow
# and anchored to the exact comment shape (not a generic `<!--.*-->` strip):
# `skill.md` may legitimately carry other HTML comments that must survive
# rendering untouched. The regex is line-anchored, so an inline, list-item,
# or blockquote-prefixed marker would survive it — the guarantee against a
# leak is `test_render_skill_strips_test_anchor_markers`, which asserts no
# `test-anchor:` survives rendering of the real `skill.md`, not this pattern.
_TEST_ANCHOR_LINE_RE = re.compile(
    r"(?m)^[ \t]*<!--[ \t]*test-anchor:[A-Za-z0-9_-]+:(?:begin|end)[ \t]*-->[ \t]*\n?"
)


class LinkMode(str, Enum):
    """Tri-state control for whether `install()` links or copies the Claude side.

    ``AUTO`` (the default) links when possible and falls back to thin references on
    symlink incapability; ``LINK`` is the strict form (errors instead of
    falling back); ``COPY`` is the escape hatch — today's real-tree-only
    behavior, unchanged.
    """

    AUTO = "auto"
    LINK = "link"
    COPY = "copy"

    # Render as the value ("auto"), never the enum repr ("LinkMode.AUTO") —
    # matches every other closed-alphabet enum in this codebase (e.g.
    # `dummyindex/context/enums.py:DocConfidence`).
    __str__ = str.__str__


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
    ("fleet", "dummyindex-fleet"),
    ("update", "dummyindex-update"),
    ("evolve", "dummyindex-evolve"),
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

1. **Claude Code** — use this canonical workflow with your native tools.
   A `.claude/skills` link or thin reference is discovery metadata; do not
   follow it back from this file or treat it as another implementation.
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
    """Substitute the package version, strip test-only markers, and add the
    portable-host preamble.

    Every rendered copy — Claude and Codex/portable-host alike — has its
    `test-anchor:*` canary marker lines dropped whole, so a test-only region
    delimiter never ships inside an installed `SKILL.md`. Ordinary comments
    (anything not matching that exact shape) pass through untouched.
    """
    rendered = text.replace("__VERSION__", PACKAGE_VERSION)
    rendered = _TEST_ANCHOR_LINE_RE.sub("", rendered)
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
    from .ownership import sync_family

    files = {}
    for name in _COMMAND_FILES:
        source = _SKILLS_DIR / "commands" / name
        if source.is_file():
            files[name] = source.read_text(encoding="utf-8")
    result = sync_family(
        commands_dir, files, family="dummyindex-commands", version=PACKAGE_VERSION
    )
    for name in result.preserved:
        print(f"  command preserved -> {commands_dir / name} (edited or unproven)")
    return list(result.written)


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
    from .ownership import remove_family

    return list(remove_family(commands_dir, family="dummyindex-commands"))


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


# ----- ownership evidence + owned-tree removal -------------------------------
#
# Hoisted from `repair.py` / `uninstall.py` (this is the bottom layer both
# import) so `link.py` can reuse them without creating an import cycle.
# `repair.py` and `uninstall.py` re-export these names unchanged.
#
# Monkeypatch trap for future test authors: `is_owned_copy` below resolves
# `_read_stamp`/`_has_legacy_codex_heading` from THIS module's globals (plain
# name lookup at call time), not from whatever module re-exported them — so
# patching `repair._read_stamp` (or `repair._has_legacy_codex_heading`) has
# no effect on `is_owned_copy`; it only affects direct callers in `repair.py`
# itself, such as `scan_installed_copies`.


def _read_stamp(stamp_path: Path) -> str | None:
    try:
        value = stamp_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _has_legacy_codex_heading(skill_md: Path) -> bool:
    """Whether a rendered SKILL.md still carries the pre-portable-host heading."""
    try:
        body = skill_md.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(_LEGACY_CODEX_HEADING_RE.search(body))


def is_owned_copy(path: Path) -> bool:
    """Whether ``path`` (a family's main skill dir) carries ownership evidence.

    True when a ``.dummyindex_version`` stamp is present and non-empty, or
    the legacy ``## Codex host compatibility`` heading is found in its
    ``SKILL.md`` — the same OR `_decide_rewrite`/`_is_proven` gate rewrites
    and duplicate-detection on. Exposed here (no leading underscore) so
    callers outside this module — namely `install()`'s direct-write loop,
    which must self-heal an existing-but-unprovable dir left by an install
    interrupted after SKILL.md but before the stamp (written last) — never
    reimplement the heading regex or duplicate the stamp-reading contract. A
    bare dir-name match is never ownership evidence on its own, mirroring
    every other ownership check in this module.
    """
    stamp = _read_stamp(path / _VERSION_STAMP_NAME)
    return stamp is not None or _has_legacy_codex_heading(path / "SKILL.md")


def _remove_owned_tree_no_follow(path: Path) -> None:
    """Whole-tree cleanup is allowed only when every file is proven pristine."""
    from .ownership import family_is_pristine

    if path.is_symlink():
        path.unlink()
        return
    family = path.name
    suffix = ".dummyindex-old.tmp"
    if family.startswith(".") and family.endswith(suffix):
        family = family[1 : -len(suffix)]
    if not family_is_pristine(path, family=family):
        raise OSError(f"preserving edited or unproven installed family: {path}")

    def remove_plain_tree(directory: Path) -> None:
        for child in directory.iterdir():
            info = child.lstat()
            if stat.S_ISLNK(info.st_mode) or bool(
                getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            ):
                raise OSError(f"refusing changed link during family cleanup: {child}")
            if stat.S_ISDIR(info.st_mode):
                remove_plain_tree(child)
            else:
                child.unlink()
        directory.rmdir()

    remove_plain_tree(path)


# ----- version comparison -----------------------------------------------------
#
# The implementation now lives in the neutral top-level `dummyindex/versioning.py`
# (`parse_version` / `compare_versions`) so `context/` can share it without
# importing `installer/`. Originally hoisted here from `repair.py` (the same
# comparator `installer/install/link_dispatch.py`'s `_agents_family_stamp_state`
# used to duplicate independently — an audit confirmed both agreed on every
# ordering). These private names stay as plain aliases so `repair.py`,
# `ownership.py`, `install/orchestrate.py`, and `install/link_dispatch.py` keep
# importing them unchanged. `_compare_stamp` now returns a `VersionOrder`, a
# `(str, Enum)` that compares equal to and renders as "older" | "equal" |
# "newer" | "unknown", so every `==` / `in` / f-string caller is unaffected.

_parse_version = parse_version
_compare_stamp = compare_versions
