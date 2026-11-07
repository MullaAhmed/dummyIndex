"""`dummyindex uninstall` — remove the skill tree from the chosen scope."""

from __future__ import annotations

import sys
from pathlib import Path

from .common import (
    _SIBLING_SKILLS,
    COMMANDS_REL,
    _first_symlink_component,
    normalize_platform_arg,
    platforms_for,
    remove_commands,
    skills_root_rel,
)
from .link import remove_dangling_family_links


def uninstall(
    *,
    scope: str = "user",
    project_dir: Path | None = None,
    platform: str = "both",
) -> None:
    """Remove the skill (and version stamp) from the chosen scope.

    ``platform`` defaults to ``"both"``, like ``install()``, so a flagless
    uninstall removes what a flagless install wrote. ``"claude"`` or
    ``"agents"``/``"codex"`` narrows removal to one side.
    """
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be 'user' or 'project', got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        platform = normalize_platform_arg(platform)
    except ValueError as exc:
        print(f"error: --{exc}", file=sys.stderr)
        sys.exit(1)
    try:
        concrete_platforms = platforms_for(platform)
    except ValueError as exc:
        print(f"error: --{exc}", file=sys.stderr)
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    removed: list[str] = []
    for host in concrete_platforms:
        removed.extend(_remove_skill_family(base, host, scope=scope))

    if "codex" in concrete_platforms:
        # Removing the real `.agents` tree leaves owned Claude-side links
        # dangling, so sweep them right after the codex family is gone (only
        # `OURS_DANGLING`, never FOREIGN). `--platform claude` skips this branch:
        # there `_remove_skill_family` unlinks the links without following them.
        allowed_symlinks = (
            frozenset({base / ".claude", base / ".claude" / "skills"})
            if scope == "user"
            else frozenset()
        )
        swept = remove_dangling_family_links(base, allowed_symlinks=allowed_symlinks)
        for path in swept:
            removed.append(str(path))
        references = _remove_dangling_references(
            base, allowed_symlinks=allowed_symlinks
        )
        removed.extend(references)

        if "claude" not in concrete_platforms and (swept or references):
            # An agents-only removal also took out the Claude surface (linked
            # layouts have no Claude-side bytes). Warn and print the restore command.
            print(
                f"  warning: --platform agents removed the only real skill "
                f"tree; {len(swept) + len(references)} Claude-side references pointed into it and "
                f"were removed too — the Claude Code surface at {base} is gone",
                file=sys.stderr,
            )
            scope_flag = (
                f"--scope project --dir {base}"
                if scope == "project"
                else "--scope user"
            )
            print(
                f"  restore Claude Code without Codex: dummyindex install "
                f"{scope_flag} --platform claude"
            )

    if "claude" in concrete_platforms:
        allowed_symlinks = (
            frozenset({base / ".claude"}) if scope == "user" else frozenset()
        )
        for name in remove_commands(base, allowed_symlinks=allowed_symlinks):
            removed.append(str(base / COMMANDS_REL / name))
        for directory in (base / COMMANDS_REL, base / ".claude"):
            if (
                _first_symlink_component(
                    base, directory, allowed_symlinks=allowed_symlinks
                )
                is not None
            ):
                break
            try:
                directory.rmdir()
            except OSError:
                break

    if "codex" in concrete_platforms:
        removed.extend(
            _remove_codex_guidance(
                scope=scope,
                project_dir=project_dir,
            )
        )

    if removed:
        print(f"  skill removed  ->  {removed[0]}")
    else:
        print("nothing to remove")


def _remove_dangling_references(
    base: Path, *, allowed_symlinks: frozenset[Path]
) -> list[str]:
    """Thin owned discovery entries have the same target dependency as links."""
    from .ownership import read_manifest, remove_family

    removed = []
    for family in ("dummyindex", *(label for _, label in _SIBLING_SKILLS)):
        canonical = base / skills_root_rel("codex") / family / "SKILL.md"
        native = base / skills_root_rel("claude") / family
        if canonical.exists() or canonical.is_symlink() or native.is_symlink():
            continue
        if (
            _first_symlink_component(base, native, allowed_symlinks=allowed_symlinks)
            is not None
        ):
            continue
        manifest = read_manifest(native)
        if manifest is not None and manifest.get("layout") == "reference":
            removed.extend(
                str(native / name) for name in remove_family(native, family=family)
            )
    return removed


def _remove_skill_family(base: Path, host: str, *, scope: str) -> list[str]:
    """Remove unchanged owned files and aliases, preserving edits and unknowns."""
    from .ownership import remove_family

    removed: list[str] = []
    root = base / skills_root_rel(host)
    allowed = (
        frozenset({base / skills_root_rel(host).parts[0]})
        if scope == "user"
        else frozenset()
    )
    for family in ("dummyindex", *(label for _, label in _SIBLING_SKILLS)):
        directory = root / family
        unsafe = _first_symlink_component(base, directory, allowed_symlinks=allowed)
        if unsafe is not None and unsafe != directory:
            print(
                f"  skill removal skipped: refusing directory symlink {unsafe}",
                file=sys.stderr,
            )
            continue
        if directory.is_symlink():
            directory.unlink()
            removed.append(str(directory))
            continue
        for relative in remove_family(directory, family=family):
            removed.append(str(directory / relative))
        if directory.exists():
            print(f"  skill preserved -> {directory} (edited or unknown files remain)")
    for directory in (root, root.parent):
        try:
            directory.rmdir()
        except OSError:
            break
    return removed


def _remove_codex_guidance(
    *,
    scope: str,
    project_dir: Path | None,
) -> list[str]:
    """Remove only dummyindex's managed AGENTS blocks for this uninstall.

    User scope cleans global guidance plus a project block explicitly stamped
    as user-auto-init ownership. Project/ingest-owned and legacy unowned blocks
    stay intact. Project scope cleans the selected project's block regardless
    of owner. Each cleanup is best-effort: a malformed file is reported and
    left unchanged while skill removal remains successful.
    """
    from dummyindex.context.output.agents_md import (
        PROJECT_OWNER_USER_AUTO_INIT,
        remove_global_agents_md,
        remove_project_agents_md,
    )

    removed: list[str] = []
    if scope == "user":
        global_result = remove_global_agents_md(Path.home())
        removed.extend(str(path) for path in global_result.removed)
        for issue in global_result.errors:
            print(
                f"  Codex global guidance -> skipped {issue.path} ({issue.message})",
                file=sys.stderr,
            )
        project_root = (project_dir or Path(".")).resolve()
        project_result = remove_project_agents_md(
            project_root,
            owner=PROJECT_OWNER_USER_AUTO_INIT,
        )
        removed.extend(str(path) for path in project_result.removed)
        for issue in project_result.errors:
            print(
                f"  Codex auto-init guidance -> skipped {issue.path} ({issue.message})",
                file=sys.stderr,
            )
        return removed

    project_root = (project_dir or Path(".")).resolve()
    project_result = remove_project_agents_md(project_root)
    removed.extend(str(path) for path in project_result.removed)
    for issue in project_result.errors:
        print(
            f"  Codex project guidance -> skipped {issue.path} ({issue.message})",
            file=sys.stderr,
        )
    return removed
