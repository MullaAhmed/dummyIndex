"""`dummyindex install` — copy the skill tree + auto-init the project.

`run_link_install` is called via `_install_pkg`, not a bare name, so a test that
patches it on the package (`tests/test_install_link.py`) is seen here. The
self-import during package init is safe; see `link/sweep.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import dummyindex.installer.install as _install_pkg
from dummyindex.context.domains.config import ConfigError

from ..common import (
    _SKILL_REGISTRATION,
    PACKAGE_VERSION,
    LinkMode,
    _compare_stamp,
    _install_commands,
    _read_stamp,
    _skill_src,
    platforms_for,
    skill_rel,
    skills_root_rel,
)
from ..link import FamilyLinkState, LinkCapabilityError
from ..link import verify_family_links as _verify_family_links
from .family_write import (
    _install_skill_family,
    _install_skill_references,
    _symlinked_skill_install_directory,
)
from .link_dispatch import (
    _claude_narrowing_link_gate,
    _link_state_report_line,
    _print_link_install_result,
)
from .project_init import (
    _auto_init_project,
    _migrate_existing_config,
    _write_default_config,
)


def install(
    *,
    scope: str = "user",
    project_dir: Path | None = None,
    skill_only: bool = False,
    no_onboarding: bool = False,
    defaults: bool = False,
    no_default_plugins: bool = False,
    no_superpowers: bool = False,
    platform: str = "both",
    dedupe: str | None = None,
    force_downgrade: bool = False,
    link_mode: LinkMode = LinkMode.AUTO,
) -> None:
    """Prepare canonical skills, optional Claude aliases, and project integration.

    AUTO uses shared `.agents/skills` bodies and Claude directory links or thin
    discovery references. LINK requires links; COPY explicitly prepares full
    native copies. Existing ownership hashes gate every update and conversion.
    `skill_only` skips project initialization; scope/config policies are unchanged.
    """
    no_default_plugins = no_default_plugins or no_superpowers
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be 'user' or 'project', got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    if dedupe is not None and dedupe not in ("user", "project"):
        print(
            f"error: --dedupe must be 'user' or 'project', got {dedupe!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        concrete_platforms = platforms_for(platform)
    except ValueError as exc:
        print(f"error: --{exc}", file=sys.stderr)
        sys.exit(1)

    skill_platforms = concrete_platforms
    if "claude" in concrete_platforms and link_mode is not LinkMode.COPY:
        skill_platforms = ("claude", "codex")

    src = _skill_src("skill.md")
    if not src.exists():
        print(
            f"error: {src} not found - reinstall dummyindex from source",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    # repair.py's two trust roots, independent of `scope`: the resolved project
    # dir (also the auto-init target) and the genuine user home. Never swap them
    # or use CWD for `user_home`: repair's no-follow guards anchor on these.
    project_root = (project_dir or Path(".")).resolve()
    user_home = Path.home()
    # One Claude-side allowlist per run, shared by the preflight, the link
    # dispatch and `_install_commands`: never HOME-derived, never two notions of
    # an allowed dotfiles `.claude` (invariant: `link/__init__.py`).
    claude_link_allowlist = (
        frozenset({base / ".claude", base / ".claude" / "skills"})
        if scope == "user"
        else frozenset()
    )
    for host in skill_platforms:
        # A user may deliberately manage ~/.claude or ~/.agents as a dotfiles
        # symlink. That host root is user-owned configuration, so follow it at
        # user scope while continuing to reject any deeper managed-directory
        # link (and every project-scope link).
        host_root = base / skills_root_rel(host).parts[0]
        allowed_symlinks = (
            claude_link_allowlist
            if host == "claude"
            else (frozenset({host_root}) if scope == "user" else frozenset())
        )
        if scope == "user" and host_root.is_symlink():
            try:
                resolved_host_root = host_root.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                print(
                    f"error: refusing to install through user host root symlink "
                    f"{host_root}: target is unavailable ({exc})",
                    file=sys.stderr,
                )
                sys.exit(1)
            if not resolved_host_root.is_dir():
                print(
                    f"error: refusing to install through user host root symlink "
                    f"{host_root}: target is not a directory "
                    f"({resolved_host_root})",
                    file=sys.stderr,
                )
                sys.exit(1)
        directory_allowlist = allowed_symlinks
        if host == "claude":
            # Admit only links already classified as owned by the existing machinery.
            links = _verify_family_links(base, allowed_symlinks=allowed_symlinks)
            admitted = frozenset(
                classification.path
                for classification in links
                if classification.state
                in (
                    FamilyLinkState.OURS_HEALTHY,
                    FamilyLinkState.OURS_DANGLING,
                    FamilyLinkState.MATERIALIZED,
                )
            )
            directory_allowlist = allowed_symlinks | admitted
        unsafe_link = _symlinked_skill_install_directory(
            base, host, allowed_symlinks=directory_allowlist
        )
        if unsafe_link is not None:
            # Narrow the remediation to the *other* host: the refusal fires
            # per-host, so whichever side is clean is always installable by
            # excluding the symlinked one via --platform.
            narrow_platform = "agents" if host == "claude" else "claude"
            narrowed_side = "claude" if host == "claude" else "agents"
            print(
                f"error: refusing to install through managed directory symlink "
                f"{unsafe_link} (pass --platform {narrow_platform} to skip the "
                f"{narrowed_side} side)",
                file=sys.stderr,
            )
            sys.exit(1)
    from ..repair import describe_plan, execute_repairs, plan_repairs

    repair_plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope=scope,
        selected_platforms=skill_platforms,
        skill_only=skill_only,
        force_downgrade=force_downgrade,
    )
    # Repair uses the same per-file ownership checks as fresh preparation.
    repair_result = execute_repairs(repair_plan)
    failed_hosts = {
        error.copy.host for error in repair_result.errors if error.copy.scope == scope
    }
    complete = not failed_hosts
    for line in describe_plan(repair_plan):
        print(line)
    # Version equality is insufficient: stock guidance can change within a
    # development version. The file hashes make this pass idempotent and safe.
    if "codex" in skill_platforms and "codex" not in failed_hosts:
        complete = (
            _install_skill_family(base, "codex", src, force_downgrade=force_downgrade)
            is not False
        ) and complete
    claude_stamp = _read_stamp(
        (base / skill_rel("claude")).parent / ".dummyindex_version"
    )
    newer_claude = (
        "claude" in concrete_platforms
        and claude_stamp
        and _compare_stamp(claude_stamp, PACKAGE_VERSION) in ("newer", "unknown")
    )
    if "claude" in failed_hosts:
        print("  claude family preserved (repair failed; see diagnostic)")
    elif newer_claude and not force_downgrade:
        complete = False
        print(
            "  claude family preserved (newer or unknown version; --force-downgrade required)"
        )
    elif "claude" in concrete_platforms:
        if link_mode is LinkMode.COPY:
            for classification in _verify_family_links(
                base, allowed_symlinks=claude_link_allowlist
            ):
                if classification.state in (
                    FamilyLinkState.OURS_DANGLING,
                    FamilyLinkState.MATERIALIZED,
                ):
                    print(
                        _link_state_report_line(classification, base=base, scope=scope)
                    )
            directory = (base / skill_rel("claude")).parent
            if not directory.is_symlink() and not (
                directory.exists() and not directory.is_dir()
            ):
                complete = (
                    _install_skill_family(
                        base, "claude", src, force_downgrade=force_downgrade
                    )
                    is not False
                ) and complete
        else:
            if not (base / skill_rel("codex")).is_file():
                print(
                    "error: shared SKILL.md is missing; native references were not prepared",
                    file=sys.stderr,
                )
                sys.exit(1)
            if link_mode is LinkMode.LINK:
                _claude_narrowing_link_gate(
                    base, link_mode=link_mode, force_downgrade=force_downgrade
                )
            try:
                result = _install_pkg.run_link_install(
                    base, link_mode=link_mode, allowed_symlinks=claude_link_allowlist
                )
            except LinkCapabilityError as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(1)
            except Exception as exc:
                _install_skill_references(base, src, force_downgrade=force_downgrade)
                print(
                    f"error: link install failed ({exc}); shared references prepared",
                    file=sys.stderr,
                )
                sys.exit(1)
            _print_link_install_result(base, result)
            if result.link_result is not None and (
                result.link_result.errors or result.link_result.skipped
            ):
                complete = False
            if link_mode is LinkMode.AUTO:
                complete = (
                    _install_skill_references(
                        base, src, force_downgrade=force_downgrade
                    )
                    is not False
                ) and complete

    if dedupe is not None:
        from ..repair import dedupe as _dedupe_family

        dedupe_result = _dedupe_family(
            dedupe,
            project_root=project_root,
            user_home=user_home,
            selected_platforms=concrete_platforms,
        )
        for removed_path in dedupe_result.removed:
            print(f"  dedupe removed   ->  {removed_path}")
        # One stderr line per failed family is already printed inside
        # `_dedupe_family` — best-effort, never aborts the install.

    if "claude" in concrete_platforms:
        # Same allowlist as the link machinery above: one allowance per run.
        copied = _install_commands(base, allowed_symlinks=claude_link_allowlist)
        if copied:
            commands = ", ".join("/" + Path(c).stem for c in copied)
            print(f"  claude commands  ->  {commands}")

    if scope == "user" and "claude" in concrete_platforms:
        _register_claude_user_skill()
    if scope == "user" and "codex" in concrete_platforms:
        _register_codex_user_skill()

    # Auto-init the resolved project candidate if it's a git repo. Skip
    # silently for non-repo dirs (user just wanted the skill) and when
    # the caller explicitly opted out via --skill-only. `is_git_repo`
    # accepts submodule/worktree `.git` files, not just `.git/` dirs.
    from dummyindex.context import is_git_repo

    auto_init_target = project_root
    target_is_repo = is_git_repo(auto_init_target)
    init_ran = False
    if not skill_only and target_is_repo:
        init_ran = _auto_init_project(
            auto_init_target,
            no_default_plugins=no_default_plugins,
            platform=platform,
            codex_guidance_owner=("user-auto-init" if scope == "user" else "project"),
            force_downgrade=force_downgrade,
        )
        if init_ran and (defaults or no_onboarding):
            _write_default_config(auto_init_target, platform=platform)
        # Codex has no native default-plugin pass, but a plain Codex reinstall
        # still preserves the historical schema-healing behavior. The one-run
        # default opt-out remains an earlier gate and leaves config byte-stable.
        if not no_default_plugins and "claude" not in concrete_platforms:
            try:
                _migrate_existing_config(auto_init_target)
            except (ConfigError, OSError) as exc:  # pragma: no cover - defensive
                print(
                    f"  config.json      ->  migration skipped ({exc})",
                    file=sys.stderr,
                )

    selected = " + ".join(
        "Claude Code" if p == "claude" else "Codex" for p in concrete_platforms
    )
    if platform == "claude":
        invocations = ("/dummyindex .",)
    elif platform == "codex":
        invocations = ("$dummyindex .",)
    else:
        invocations = ("Claude Code: /dummyindex .", "Codex:      $dummyindex .")
    print()
    if not complete:
        print(
            "error: partial installation; edited, unproven or failed families were preserved. Review the diagnostics and source check before retrying.",
            file=sys.stderr,
        )
        sys.exit(1)
    if init_ran:
        print(f"Done. Open {selected} in {auto_init_target} and run:")
    elif scope == "project":
        target = (project_dir or Path(".")).resolve()
        print(f"Done. Open {selected} in {target} and run:")
    else:
        print(f"Done. Open {selected} and run:")
    print()
    for invocation in invocations:
        print(f"  {invocation}")
    print()
    if not skill_only and not init_ran and not target_is_repo:
        platform_flag = "" if platform == "claude" else f" --platform {platform}"
        print(
            f"  (no git repo at {auto_init_target} — skipped project init.\n"
            f"   run `dummyindex ingest <path>{platform_flag}` from a project directory\n"
            f"   to build .context/ and write the host guidance.)"
        )
        print()


def _register_claude_user_skill() -> None:
    claude_md = Path.home() / ".claude" / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        if "**dummyindex** (" in content:
            print("  CLAUDE.md        ->  already registered (no change)")
            return
        claude_md.write_text(content.rstrip() + _SKILL_REGISTRATION, encoding="utf-8")
        print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
        return
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text(_SKILL_REGISTRATION.lstrip(), encoding="utf-8")
    print(f"  CLAUDE.md        ->  created at {claude_md}")


def _register_codex_user_skill() -> None:
    """Add a managed pointer to Codex's active user-global instruction file."""
    try:
        from dummyindex.context.output.agents_md import bootstrap_global_agents_md

        path = bootstrap_global_agents_md(Path.home())
    except (OSError, ValueError) as exc:
        print(f"  Codex guidance   ->  skipped ({exc})", file=sys.stderr)
        return
    print(f"  Codex guidance   ->  registered in {path}")
