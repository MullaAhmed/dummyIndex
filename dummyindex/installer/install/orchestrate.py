"""`dummyindex install` — copy the skill tree + auto-init the project.

See the package docstring (``install/__init__.py``) for the split rationale.

Module-identity note: `run_link_install` below is called through
`_install_pkg` (this package's own `__init__.py`), not as a bare name imported
from `..link`. `tests/test_install_link.py`'s
`importlib.import_module("dummyindex.installer.install")` +
`monkeypatch.setattr(install_module, "run_link_install", ...)` patches the
PACKAGE's own attribute; a bare-name call resolved via this module's own
globals would never observe that patch. The self-import is safe despite
executing while the package is still initializing — see `link/sweep.py`'s
identical note for the full explanation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import dummyindex.installer.install as _install_pkg
from dummyindex.context.domains.config import ConfigError

from ..common import (
    _SKILL_REGISTRATION,
    LinkMode,
    _install_commands,
    _skill_src,
    platforms_for,
    skill_rel,
    skills_root_rel,
)
from ..link import FamilyLinkState, LinkCapabilityError, classify_family_link
from ..link import verify_family_links as _verify_family_links
from .family_write import _install_skill_family, _symlinked_skill_install_directory
from .link_dispatch import (
    _all_claude_families_missing,
    _backfill_sibling_stamps,
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
    """Install the skill family for Claude Code, Codex, or both hosts.

    Claude uses ``.claude/skills`` and slash-command aliases. Codex uses the
    open Agent Skills location ``.agents/skills`` and ``$skill-name`` mentions.
    The default is ``platform="both"`` — a plain call installs Claude Code
    and Codex together (the universal-install compatibility break; pass
    ``platform="claude"`` or ``platform="codex"`` explicitly to narrow to one
    host).

    ``link_mode`` (``LinkMode.AUTO`` by default) is the CLI-parsed
    ``--link``/``--copy`` tri-state selector for the Claude side of a
    ``"both"``/``"claude"`` install (spec: symlink-single-source-install).
    ``AUTO`` links the 8 enumerated skill families to the real
    ``.agents/skills`` tree whenever possible — including converting a
    duplicated proven Claude copy or a claude-only layout (the forced
    migration) — and falls back to writing a real, unlinked Claude tree on
    symlink incapability or an unqualifying ``--platform claude`` narrowing
    (an ``.agents`` family that isn't provably current). ``LINK`` is the
    strict form: it exits 1 instead of falling back. ``COPY`` is today's
    real-tree-only behavior, unchanged, and never converts an existing
    linked layout back. Linking (when it happens) always runs *after* the
    repair pass below has landed every rewrite, never before.

    Auto-init: after the skill copy, if the resolved project candidate
    (``project_dir`` when given, else CWD) is a git repo — a ``.git/``
    directory *or* a submodule/worktree ``.git`` pointer file — this also
    runs the host-aware ``init`` flow on it: builds ``.context/`` and writes
    managed Claude guidance and/or the active Codex project instruction file.
    Claude installs its managed hooks and default plugins; Codex relies on
    durable project guidance and the installed skills.
    Pass ``skill_only=True`` (``--skill-only`` on the CLI) to suppress
    this and just install the skill — useful when running ``install``
    from a directory that happens to be a git repo but isn't the project
    you want indexed.

    ``no_superpowers`` remains a compatibility keyword for callers written
    before the default set grew beyond that plugin. Both opt-out spellings
    resolve immediately to the same one-run gate.

    Repair: every run also plans and executes a repair pass
    (``installer.repair``) scoped to this invocation's selected platforms at
    its targeted scope root — a stale, proven copy there is rewritten; a
    stale copy at every other detected root, and any user+project duplicate,
    is report-only with a remediation hint. An existing-but-unprovable copy
    at this invocation's own target scope×platform (no ``.dummyindex_version``
    stamp and no legacy heading — an install interrupted after SKILL.md but
    before the stamp, which is written last) is written directly rather than
    left report-only forever. ``force_downgrade`` (CLI ``--force-downgrade``)
    allows rewriting a copy stamped newer than this package version, which is
    report-only otherwise. ``dedupe`` (CLI ``--dedupe user|project``)
    additionally removes that scope's copy of any skill family proven
    duplicated at both scopes, filtered to this invocation's selected
    platforms — never anything else, and never without this explicit flag.
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

    src = _skill_src("skill.md")
    if not src.exists():
        print(
            f"error: {src} not found - reinstall dummyindex from source",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    # The two repair.py trust roots, independent of `scope`: the resolved
    # project-directory candidate (reused below for auto-init too, so this is
    # the one `.resolve()` call for that value) and the GENUINE user home.
    # Never swap these, and never substitute CWD for `user_home` — repair's
    # no-follow guards anchor on exactly these two roots.
    project_root = (project_dir or Path(".")).resolve()
    user_home = Path.home()
    # ONE host-root allowlist per run for the Claude-side family-link
    # machinery (the preflight admission below, the direct-write loop, the
    # link dispatch after `execute_repairs`, and `_install_commands` all share
    # this SAME value) — never HOME-derived, never two divergent notions of
    # what a dotfiles-managed `.claude` is allowed to be (spec: symlink-
    # single-source-install, "Wave 3 obligation"; see `link.py`'s module
    # docstring for the invariant these two entries satisfy).
    claude_link_allowlist = (
        frozenset({base / ".claude", base / ".claude" / "skills"})
        if scope == "user"
        else frozenset()
    )
    host_allowed_symlinks: dict[str, frozenset[Path]] = {}
    for host in concrete_platforms:
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
        # Recorded per host so the sibling-stamp backfill below (run once,
        # after `execute_repairs`, for every selected host tree) reuses the
        # IDENTICAL parent-chain allowlist this preflight already computed —
        # never a second, divergent notion of which host-root symlink this
        # run tolerates.
        host_allowed_symlinks[host] = allowed_symlinks
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
            # The preflight admission (spec: symlink-single-source-install,
            # "The preflight admission"): admit a family dir iff it
            # classifies OURS_HEALTHY / OURS_DANGLING / MATERIALIZED, in
            # EVERY LinkMode (AUTO, LINK, COPY) — the preflight itself never
            # converts anything, it only decides whether to refuse. Every
            # other state (FOREIGN, and any deeper companion-dir symlink
            # under a real family) keeps today's refusal byte-for-byte:
            # `_symlinked_skill_install_directory` below is UNCHANGED, only
            # the allowlist it is given grows to admit the provably-ours
            # top-level family symlinks/materialized files.
            #
            # A SIBLING's own healthy link now classifies OURS_HEALTHY like
            # any other family (HIGH-2 fix, spec: symlink-single-source-
            # install): `_backfill_sibling_stamps` (below, run once per host
            # tree after `execute_repairs`) mints `.dummyindex_version` onto
            # every sibling REAL directory whose family main dir is provably
            # stamped, so a sibling's `.agents` link target now carries the
            # same ownership evidence `classify_family_link`'s OURS_HEALTHY
            # already requires — no second, weaker classifier is needed to
            # admit it, and the plain sweep below is the whole story.
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
    from ..repair import describe_plan, execute_repairs, is_owned_copy, plan_repairs

    repair_plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope=scope,
        selected_platforms=concrete_platforms,
        skill_only=skill_only,
        force_downgrade=force_downgrade,
    )
    # Set below, in the direct-write loop, iff the Claude family was MISSING
    # entirely this run (fresh install) — the ONE state the link dispatch's
    # post-check (below) is allowed to write for. OURS_DANGLING/MATERIALIZED
    # are deliberately excluded: those already got their own report line
    # under --copy above and must stay report-only, never routed through
    # `_install_skill_family` (which raises OSError for either — see its own
    # unconditional write-path guard).
    claude_missing_deferred = False
    for host in concrete_platforms:
        # A never-before-installed host at this scope has nothing for repair
        # to prove stale (`plan_repairs` only classifies an existing family
        # dir) — write it directly, exactly as every prior release did. An
        # existing-but-unprovable dir (no `.dummyindex_version` stamp and no
        # legacy heading) is also written here: `plan_repairs` never treats a
        # bare dir-name match as a rewrite candidate, so without this branch
        # an install interrupted after SKILL.md but before the stamp (written
        # last) would never complete on rerun. Any *provable* existing dir —
        # current, stale, newer, unknown, or symlinked — defers entirely to
        # `execute_repairs` below, so it is never double-written here.
        family_dir = (base / skill_rel(host)).parent
        if host == "claude":
            # Direct-write loop (spec: symlink-single-source-install, "The
            # preflight admission" + "CLI surface"): consult
            # classify_family_link FIRST. OURS_DANGLING / MATERIALIZED must
            # never reach the unconditional `mkdir(exist_ok=True)` inside
            # `_install_skill_family` — both raise FileExistsError there (a
            # dangling symlink, or a regular file occupying the family-dir
            # slot). Under --copy, report with the remediation instead of
            # crashing; under AUTO/LINK, defer entirely to
            # `create_family_links` (dispatched below, after
            # `execute_repairs`, per the pinned sequencing) — never written
            # here either way.
            #
            # MISSING (nothing at the MAIN family slot yet) is ALSO deferred
            # — but only on a genuinely blank slate (`_all_claude_families_
            # missing`, below): whether this run actually links is only known
            # after the narrowing gate + the capability probe inside the link
            # dispatch below, and `_install_skill_family` stamps only the
            # MAIN family, never its siblings. Writing the real tree here,
            # before that's decided, is exactly the bug this fixes — every
            # unstamped sibling real dir it creates is later refused by
            # `create_family_links` ("no .dummyindex_version stamp"),
            # permanently duplicating the family instead of linking it. The
            # link dispatch's own post-check performs this write instead, but
            # only when `create_family_links` was never called this run
            # (explicit --copy, or an AUTO capability fallback) — see the
            # "never neither" check there. A MIXED state (MAIN missing but a
            # SIBLING already a real, unproven dir — e.g. an old <=0.25.0
            # partial install with a stale companion) is NOT deferred: that
            # sibling still needs `_install_skill_family`'s own repair/purge
            # pass (stale `*.tmpl` twins, refreshed companions), which only
            # runs when this call isn't skipped — deferring here would
            # silently drop that cleanup for the rest of this run's life.
            classification = classify_family_link(
                family_dir, base, allowed_symlinks=claude_link_allowlist
            )
            if classification.state in (
                FamilyLinkState.OURS_DANGLING,
                FamilyLinkState.MATERIALIZED,
            ):
                if link_mode is LinkMode.COPY:
                    print(
                        _link_state_report_line(classification, base=base, scope=scope)
                    )
                continue
            if classification.state is FamilyLinkState.MISSING and (
                _all_claude_families_missing(base)
            ):
                claude_missing_deferred = True
                continue
        # HIGH-2 residual (spec: symlink-single-source-install, "The
        # preflight admission"): a family-dir symlink that classifies
        # anything OTHER than OURS_DANGLING/MATERIALIZED/MISSING above —
        # most notably FOREIGN, e.g. its `.agents` target lost its
        # ownership evidence between the preflight admission and here —
        # must still never reach `_install_skill_family`: it raises
        # `OSError` on its own unconditional `skill_dir.is_symlink()` guard,
        # uncaught by this loop. Report/defer instead:
        # `plan_repairs`/`describe_plan` below still reports it via today's
        # unchanged FOREIGN refusal path.
        if not family_dir.is_symlink() and (
            not family_dir.is_dir() or not is_owned_copy(family_dir)
        ):
            _install_skill_family(base, host, src)
    execute_repairs(repair_plan)
    for line in describe_plan(repair_plan):
        print(line)

    # HIGH-1 fix (spec: symlink-single-source-install): backfill
    # `.dummyindex_version` onto every sibling REAL directory whose family
    # main dir is already provably stamped, for EACH selected host tree —
    # run once, after `execute_repairs` has landed every rewrite, and
    # BEFORE the link dispatch below decides whether to convert anything.
    # Without this, a realistic pre-existing install (main stamped, every
    # sibling real and unstamped, exactly as every prior release shipped)
    # permanently duplicates every sibling: `create_family_links` requires
    # the stamp specifically before it will replace a real directory with a
    # link.
    for host in concrete_platforms:
        _backfill_sibling_stamps(
            base, host, allowed_symlinks=host_allowed_symlinks[host]
        )

    # ----- link-mode dispatch (Wave 3): the sole point deciding whether this
    # run links the Claude side, called AFTER every rewrite above has landed
    # (`.agents/skills/**` real, `execute_repairs` done) — the proposal's
    # pinned sequencing, so `create_family_links` never links against a
    # stale/partial `.agents` tree. Never touches `.claude/**` when "claude"
    # is not among this invocation's selected platforms (the `--platform
    # agents` narrowing).
    if "claude" in concrete_platforms:
        effective_link_mode = link_mode
        if link_mode is not LinkMode.COPY and "codex" not in concrete_platforms:
            # `--platform claude` (agents not selected) is an explicit
            # narrowing: `plan_repairs`/`execute_repairs` above never freshen
            # an out-of-scope `.agents` copy this run, so AUTO must not
            # silently link onto a stale/unproven `.agents` family, and
            # strict LINK must refuse loudly rather than fall back.
            if not _claude_narrowing_link_gate(
                base, link_mode=link_mode, force_downgrade=force_downgrade
            ):
                effective_link_mode = LinkMode.COPY

        def _land_deferred_claude_write() -> None:
            """Perform the deferred MISSING-family Claude write (queued
            above in the direct-write loop) exactly when it is still owed —
            `claude_missing_deferred` and no real dir has landed since.
            Shared by the happy path below and the MEDIUM-1 exception
            handler so the "never neither" invariant is enforced
            identically either way (spec: symlink-single-source-install).
            """
            if not claude_missing_deferred:
                return
            claude_family_dir = (base / skill_rel("claude")).parent
            if not claude_family_dir.is_dir() or not is_owned_copy(claude_family_dir):
                _install_skill_family(base, "claude", src)

        try:
            link_install_result = _install_pkg.run_link_install(
                base,
                link_mode=effective_link_mode,
                allowed_symlinks=claude_link_allowlist,
            )
        except LinkCapabilityError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            # MEDIUM-1 fix (spec: symlink-single-source-install): any OTHER
            # `run_link_install` failure must not leave the Claude side with
            # NEITHER links nor real dirs — land the deferred blank-slate
            # write before translating this into a clean stderr line, never a
            # raw, uncaught traceback. Scope of the guarantee: on the
            # blank-slate install this guards (`claude_missing_deferred`, set
            # only when every family slot was MISSING), the run ends with 8
            # real Claude dirs. It is NOT a literal per-family invariant — a
            # hand-deleted partial layout (main present, some siblings
            # removed) that ALSO hits an unexpected link failure can leave
            # those siblings absent; that state is non-destructive (the main
            # skill survives, `/dummyindex` still works) and a plain rerun
            # self-heals to all 8 links.
            _land_deferred_claude_write()
            print(
                f"error: link install failed unexpectedly ({exc!r}) — the "
                "Claude side was written as a real tree instead of linking "
                "this run",
                file=sys.stderr,
            )
            sys.exit(1)
        # `create_family_links` was never dispatched this run (an explicit
        # --copy request, or an AUTO capability-probe fallback) — the
        # MISSING-family write deferred above in the direct-write loop must
        # land NOW. Without this, a symlink-incapable host (or a plain
        # --copy fresh install) would end the run with NEITHER a link NOR a
        # real Claude tree — exactly one of {8 links, 8 real dirs} must
        # exist, never a mix, never neither. `_land_deferred_claude_write`
        # itself gates on `claude_missing_deferred` (not just `link_result
        # is None`): OURS_DANGLING/MATERIALIZED already got their own
        # report line above and must stay report-only under --copy, never
        # routed through `_install_skill_family` here too.
        if link_install_result.link_result is None:
            _land_deferred_claude_write()
        _print_link_install_result(base, link_install_result)

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
        # Reuse the SAME allowlist the link-mode machinery above uses — one
        # allowance per run, never a second, narrower notion of what
        # dotfiles-managed `.claude` symlink is tolerated (spec: "Wave 3
        # obligation").
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
