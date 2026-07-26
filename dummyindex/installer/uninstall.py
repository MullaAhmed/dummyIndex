"""`dummyindex uninstall` — remove the skill tree from the chosen scope."""

from __future__ import annotations

import sys
from pathlib import Path

from .common import (
    _SIBLING_SKILLS,
    COMMANDS_REL,
    _first_symlink_component,
    _remove_owned_tree_no_follow,
    normalize_platform_arg,
    platforms_for,
    remove_commands,
    skill_rel,
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

    ``platform`` defaults to ``"both"`` — matching ``install()``'s default, on
    both the CLI parser (``parse_uninstall_args``) and this function
    signature, so a flagless ``dummyindex uninstall`` removes what a
    flagless ``dummyindex install`` wrote. Pass ``--platform claude`` or
    ``--platform agents`` (programmatically, ``platform="claude"`` or
    ``platform="codex"``) to narrow the removal to one side.
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
        # Removing the real `.agents/skills/<family>` tree turns every
        # dummyindex-owned Claude-side link that pointed at it into a
        # dangling one (spec: symlink-single-source-install, "Uninstall").
        # A dummyindex-owned link must never dangle after a dummyindex
        # uninstall, so sweep them here — right after the codex family is
        # gone, before any other cleanup. `--platform claude` never reaches
        # this branch, so it keeps removing the 8 links unchanged (existing
        # `_remove_skill_family` no-follow behavior). FOREIGN links are
        # never touched: `remove_dangling_family_links` only unlinks
        # `OURS_DANGLING` classifications.
        allowed_symlinks = (
            frozenset({base / ".claude", base / ".claude" / "skills"})
            if scope == "user"
            else frozenset()
        )
        swept = remove_dangling_family_links(base, allowed_symlinks=allowed_symlinks)
        for path in swept:
            removed.append(str(path))

        if "claude" not in concrete_platforms and swept:
            # The user asked to narrow removal to codex/agents only, but the
            # linked layout has no Claude-side bytes of its own — the sweep
            # above just took out the Claude Code surface too. Tell them,
            # and hand back the exact command that restores it (spec:
            # symlink-single-source-install, "Uninstall").
            print(
                f"  warning: --platform agents removed the only real skill "
                f"tree; {len(swept)} Claude-side links pointed into it and "
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


def _remove_skill_family(base: Path, host: str, *, scope: str) -> list[str]:
    """Remove one host's skill-family tree (main dir + siblings) at ``base``.

    Extracted from ``uninstall()`` so the same no-follow removal is shared
    with repair's ``dedupe()`` — never the full ``uninstall()`` orchestration,
    so slash commands and managed guidance blocks are never touched by a
    dedupe run. ``scope`` controls only whether the user-scope host-root
    dotfiles symlink stays followable, mirroring ``install()``'s own
    allowlist exactly.
    """
    removed: list[str] = []
    dst = base / skill_rel(host)
    skill_dir = dst.parent
    allowed_symlinks = (
        frozenset({base / skills_root_rel(host).parts[0]})
        if scope == "user"
        else frozenset()
    )
    linked_skill_parent = _first_symlink_component(
        base, skill_dir, allowed_symlinks=allowed_symlinks
    )
    if linked_skill_parent is not None and linked_skill_parent != skill_dir:
        print(
            f"  skill removal skipped: refusing to traverse directory "
            f"symlink {linked_skill_parent}",
            file=sys.stderr,
        )
        return removed
    if skill_dir.is_symlink():
        # Never follow a configured skill-directory link into an external
        # tree.  Removing the scoped link is the complete uninstall; its
        # target belongs to whoever created the link.
        skill_dir.unlink()
        removed.append(str(skill_dir))
    else:
        if dst.exists() or dst.is_symlink():
            dst.unlink()
            removed.append(str(dst))

        # Remove every companion markdown installed alongside.  A companion
        # directory may itself have been replaced by a symlink; unlink that
        # leaf without reading or modifying its target.
        for subdir in ("agents", "council", "retrieval"):
            sub_dst = skill_dir / subdir
            if sub_dst.is_symlink():
                sub_dst.unlink()
                continue
            if sub_dst.is_dir():
                for md in sub_dst.glob("*.md"):
                    md.unlink()
                try:
                    sub_dst.rmdir()
                except OSError:
                    pass

        version_file = skill_dir / ".dummyindex_version"
        if version_file.exists() or version_file.is_symlink():
            version_file.unlink()

    skills_root = base / skills_root_rel(host)
    for _sub_name, sibling in _SIBLING_SKILLS:
        sib_dir = skills_root / sibling
        if not sib_dir.exists() and not sib_dir.is_symlink():
            continue
        linked_sibling_parent = _first_symlink_component(
            base, sib_dir, allowed_symlinks=allowed_symlinks
        )
        if linked_sibling_parent is not None and linked_sibling_parent != sib_dir:
            print(
                f"  skill removal skipped: refusing to traverse directory "
                f"symlink {linked_sibling_parent}",
                file=sys.stderr,
            )
            continue
        _remove_owned_tree_no_follow(sib_dir)
        removed.append(str(sib_dir))

    # Best-effort: remove empty host directories up to the scope root.
    for directory in (skill_dir, skill_dir.parent, skill_dir.parent.parent):
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
