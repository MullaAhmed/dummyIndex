"""`dummyindex install` repair — scoped, evidence-gated, symlink-safe.

Repairs skill-family copies an older version left behind. `scan_installed_copies`
is the one four-root stamp scan (``check --versions`` wraps it, so both agree on
"installed"). `plan_repairs` gates each rewrite on ownership evidence, staleness
and symlink safety, never on a directory name. `execute_repairs` and `dedupe`
re-run the symlink preflight right before acting and isolate failures per copy.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from dummyindex.codex_guidance import codex_home

from .common import (
    _LEGACY_CODEX_HEADING_RE,  # noqa: F401 - re-exported for existing importers
    _SIBLING_SKILLS,
    _VERSION_STAMP_NAME,
    PACKAGE_VERSION,
    _compare_stamp,
    _has_legacy_codex_heading,
    _read_stamp,
    _skill_src,
    is_owned_copy,  # noqa: F401 - re-exported for existing importers (install.py:147)
    skill_rel,
    skills_root_rel,
)
from .install import _install_skill_family, _symlinked_skill_install_directory
from .link import FamilyLinkState, classify_family_link, remove_dangling_family_links
from .uninstall import _remove_skill_family


@dataclass(frozen=True)
class InstalledCopy:
    """One of the four canonical (scope, host) skill-family locations.

    ``path`` is the family's main skill directory, never the stamp file.
    ``stamp`` is the raw ``.dummyindex_version`` text under it, or ``None`` when
    missing, empty or unreadable.
    """

    scope: str  # "user" | "project"
    host: str  # "claude" | "codex"
    path: Path
    stamp: str | None


@dataclass(frozen=True)
class RepairCandidate:
    """A proven, stale copy inside this invocation's scope — safe to rewrite."""

    copy: InstalledCopy
    reason: str


@dataclass(frozen=True)
class RepairReport:
    """A detected copy left untouched, with why and the exact fix command.

    ``remediation`` is ``None`` only for an informational report (a current
    `OURS_HEALTHY` link), so `describe_plan` prints no fix suffix for it.
    """

    scope: str
    host: str
    path: Path
    reason: str
    remediation: str | None = None


@dataclass(frozen=True)
class DuplicateFamily:
    """The same skill family proven installed at both user and project scope."""

    host: str
    user_copy: InstalledCopy
    project_copy: InstalledCopy


@dataclass(frozen=True)
class RepairPlan:
    """Rewrite-vs-report classification for one repair invocation.

    ``selected_platforms`` is carried from `plan_repairs` so `describe_plan` can
    tell whether Codex is involved without a second parameter.
    """

    to_rewrite: tuple[RepairCandidate, ...]
    to_report: tuple[RepairReport, ...]
    duplicates: tuple[DuplicateFamily, ...]
    codex_home: Path
    selected_platforms: tuple[str, ...]


@dataclass(frozen=True)
class RepairError:
    """One rewrite or dedupe-removal candidate whose action failed independently.

    `execute_repairs` and `dedupe` record each per-copy failure in this shape
    and print one stderr line instead of aborting the run.
    """

    copy: InstalledCopy
    message: str


@dataclass(frozen=True)
class RepairExecutionResult:
    """Independent per-copy outcomes for one `execute_repairs` run.

    A failure on one copy is reported once on stderr and never blocks the rest.
    ``reported`` is `plan.to_report` passed through, so one object describes
    the whole run.
    """

    repaired: tuple[InstalledCopy, ...]
    reported: tuple[RepairReport, ...]
    errors: tuple[RepairError, ...]


@dataclass(frozen=True)
class DedupeResult:
    """Independent per-family outcomes for one `dedupe` run.

    ``removed`` is every path removed across all families; ``errors`` holds one
    `RepairError` per family refused (symlinked path) or failed (`OSError`).
    """

    removed: tuple[str, ...]
    errors: tuple[RepairError, ...]


def scan_installed_copies(
    out_root: Path, *, user_home: Path | None = None
) -> tuple[InstalledCopy, ...]:
    """Scan the four canonical roots for an installed skill family.

    Returns exactly four entries in fixed order: project/claude, project/codex,
    user/claude, user/codex (the `check --versions` order). A location with no
    readable stamp is still listed, with ``stamp=None``.
    """
    home = user_home if user_home is not None else Path.home()
    roots = (
        ("project", "claude", out_root),
        ("project", "codex", out_root),
        ("user", "claude", home),
        ("user", "codex", home),
    )
    return tuple(
        InstalledCopy(
            scope=scope,
            host=host,
            path=(base / skill_rel(host)).parent,
            stamp=_read_stamp((base / skill_rel(host)).parent / _VERSION_STAMP_NAME),
        )
        for scope, host, base in roots
    )


def _find_copy(
    copies: tuple[InstalledCopy, ...], *, scope: str, host: str
) -> InstalledCopy | None:
    """The one copy at ``(scope, host)`` from an already-scanned tuple, or
    ``None`` — used to look up a Claude row's same-scope Codex sibling."""
    for candidate in copies:
        if candidate.scope == scope and candidate.host == host:
            return candidate
    return None


def _classify_claude_row(
    copy: InstalledCopy, copies: tuple[InstalledCopy, ...]
) -> RepairReport | None:
    """Report a Claude-host copy by link state, or ``None`` to fall through.

    Runs before ownership/staleness checks and writes nothing (links belong to
    `create_family_links`). `OURS_HEALTHY` is informational, never a rewrite:
    staleness is judged on the codex row it points at. Dangling, materialized,
    `FOREIGN` and migration-candidate (`NOT_A_LINK` beside a proven same-scope
    codex family) copies are reported; other `NOT_A_LINK` and `MISSING` give ``None``.
    """
    scope_root = _scope_root(copy)
    allowed = _host_root_allowlist(scope_root, "claude", copy.scope)
    classification = classify_family_link(
        copy.path, scope_root, allowed_symlinks=allowed
    )
    remediation = _remediation_command(copy.scope, copy.host, base=scope_root)

    if classification.state is FamilyLinkState.OURS_HEALTHY:
        return RepairReport(
            scope=copy.scope,
            host=copy.host,
            path=copy.path,
            reason="linked -> .agents (current)",
            # No remediation: healthy + current has nothing to fix — see
            # `RepairReport.remediation`'s docstring.
        )
    if classification.state is FamilyLinkState.OURS_DANGLING:
        return RepairReport(
            scope=copy.scope,
            host=copy.host,
            path=copy.path,
            reason=(
                "linked -> .agents (dangling): the .agents target is "
                "missing; healed automatically by a plain reinstall under "
                "AUTO/LINK, or pass --copy to materialize a fresh copy here"
            ),
            remediation=remediation,
        )
    if classification.state is FamilyLinkState.MATERIALIZED:
        return RepairReport(
            scope=copy.scope,
            host=copy.host,
            path=copy.path,
            reason=(
                "linked -> .agents (materialized file): replaced with a "
                "real symlink automatically by a plain reinstall under "
                "AUTO/LINK, or pass --copy to leave it as a plain file"
            ),
            remediation=remediation,
        )
    if classification.state is FamilyLinkState.FOREIGN:
        unsafe = _symlinked_skill_install_directory(
            scope_root, copy.host, allowed_symlinks=allowed
        )
        reason = (
            f"refusing to rewrite through directory symlink {unsafe}"
            if unsafe is not None
            else f"refusing to rewrite: {classification.detail}"
        )
        return RepairReport(
            scope=copy.scope,
            host=copy.host,
            path=copy.path,
            reason=reason,
            remediation=remediation,
        )
    if classification.state is FamilyLinkState.NOT_A_LINK:
        codex_sibling = _find_copy(copies, scope=copy.scope, host="codex")
        if (
            _is_proven(copy)
            and codex_sibling is not None
            and codex_sibling.path.is_dir()
            and _is_proven(codex_sibling)
        ):
            return RepairReport(
                scope=copy.scope,
                host=copy.host,
                path=copy.path,
                reason=(
                    "migration candidate: a proven real Claude copy exists "
                    f"alongside a proven .agents family at {codex_sibling.path}"
                    " — converted to a link the next time install selects "
                    "claude (AUTO/LINK)"
                ),
                remediation=remediation,
            )
        return None
    return None  # FamilyLinkState.MISSING


def plan_repairs(
    *,
    project_root: Path,
    user_home: Path,
    target_scope: str,
    selected_platforms: tuple[str, ...],
    skill_only: bool = False,
    force_downgrade: bool = False,
    package_version: str = PACKAGE_VERSION,
) -> RepairPlan:
    """Classify every detected copy as a rewrite candidate or a report line.

    Scans both scope roots, but only a copy at ``target_scope`` for a host in
    ``selected_platforms`` can be rewritten; every other copy is report-only.
    ``skill_only`` is accepted for symmetry with `install()` and ignored: the
    skill tree is written regardless of ``--skill-only``.
    """
    del skill_only  # inert here — see docstring
    if target_scope not in ("user", "project"):
        raise ValueError(
            f"target_scope must be 'user' or 'project', got {target_scope!r}"
        )
    unsupported = sorted(set(selected_platforms) - {"claude", "codex"})
    if unsupported:
        raise ValueError(f"selected_platforms must be claude|codex, got {unsupported}")

    copies = scan_installed_copies(project_root, user_home=user_home)
    to_rewrite: list[RepairCandidate] = []
    to_report: list[RepairReport] = []

    for copy in copies:
        if copy.host == "claude":
            claude_report = _classify_claude_row(copy, copies)
            if claude_report is not None:
                to_report.append(claude_report)
                continue

        if not copy.path.is_dir():
            to_report.extend(_orphaned_sibling_reports(copy))
            continue

        legacy_heading = _has_legacy_codex_heading(copy.path / "SKILL.md")
        should_rewrite, reason = _decide_rewrite(
            copy,
            legacy_heading=legacy_heading,
            package_version=package_version,
            force_downgrade=force_downgrade,
        )
        remediation = _remediation_command(
            copy.scope, copy.host, base=_scope_root(copy)
        )

        if not should_rewrite:
            to_report.append(
                RepairReport(
                    scope=copy.scope,
                    host=copy.host,
                    path=copy.path,
                    reason=reason,
                    remediation=remediation,
                )
            )
            continue

        in_scope = copy.scope == target_scope and copy.host in selected_platforms
        if not in_scope:
            to_report.append(
                RepairReport(
                    scope=copy.scope,
                    host=copy.host,
                    path=copy.path,
                    reason=(
                        f"{reason}, but outside this invocation's selected "
                        f"scope/platform — rerun with --scope {copy.scope} "
                        f"--platform {'agents' if copy.host == 'codex' else copy.host}"
                    ),
                    remediation=remediation,
                )
            )
            continue

        base = _scope_root(copy)
        unsafe = _symlinked_skill_install_directory(
            base,
            copy.host,
            allowed_symlinks=_host_root_allowlist(base, copy.host, copy.scope),
        )
        if unsafe is not None:
            to_report.append(
                RepairReport(
                    scope=copy.scope,
                    host=copy.host,
                    path=copy.path,
                    reason=f"refusing to rewrite through directory symlink {unsafe}",
                    remediation=remediation,
                )
            )
            continue

        to_rewrite.append(RepairCandidate(copy=copy, reason=reason))

    duplicates = _find_duplicate_families(
        copies, project_root=project_root, user_home=user_home
    )

    return RepairPlan(
        to_rewrite=tuple(to_rewrite),
        to_report=tuple(to_report),
        duplicates=duplicates,
        codex_home=codex_home(user_home),
        selected_platforms=tuple(selected_platforms),
    )


def execute_repairs(plan: RepairPlan) -> RepairExecutionResult:
    """Rewrite every proven, stale copy in ``plan.to_rewrite``.

    Best-effort per copy: a failure prints one stderr line and never blocks the
    rest. Uses `install()`'s ``_install_skill_family`` so a repair matches a fresh
    install, and re-runs the symlink preflight right before writing.
    """
    src = _skill_src("skill.md")
    repaired: list[InstalledCopy] = []
    errors: list[RepairError] = []
    for candidate in plan.to_rewrite:
        copy = candidate.copy
        base = _scope_root(copy)
        unsafe = _symlinked_skill_install_directory(
            base,
            copy.host,
            allowed_symlinks=_host_root_allowlist(base, copy.host, copy.scope),
        )
        if unsafe is not None:
            message = f"refusing to write through directory symlink {unsafe}"
            errors.append(RepairError(copy=copy, message=message))
            print(
                f"  repair skipped   ->  {copy.scope} {copy.host} {copy.path}: {message}",
                file=sys.stderr,
            )
            continue
        try:
            complete = _install_skill_family(base, copy.host, src, force_downgrade=True)
            if complete is False:
                raise OSError(
                    "preserved customized or unproven files; repair is incomplete"
                )
        except (OSError, ValueError) as exc:
            errors.append(RepairError(copy=copy, message=str(exc)))
            print(
                f"  repair skipped   ->  {copy.scope} {copy.host} {copy.path}: {exc}",
                file=sys.stderr,
            )
            continue
        repaired.append(copy)
    return RepairExecutionResult(
        repaired=tuple(repaired),
        reported=plan.to_report,
        errors=tuple(errors),
    )


def dedupe(
    scope: str,
    *,
    project_root: Path,
    user_home: Path,
    selected_platforms: tuple[str, ...] | None = None,
) -> DedupeResult:
    """Remove ``scope``'s copy of every family proven installed at both scopes.

    Only `_remove_skill_family` runs: never commands or managed guidance, and a
    linked Claude family is unlinked, never followed. ``selected_platforms``
    limits removal by host (deletion obeys the write scoping); ``None`` removes all.
    Per family the symlink preflight re-runs first; a refusal or `OSError` is
    reported, never blocking the rest. A codex removal then sweeps dangling links.
    """
    if scope not in ("user", "project"):
        raise ValueError(f"scope must be 'user' or 'project', got {scope!r}")
    if selected_platforms is not None:
        unsupported = sorted(set(selected_platforms) - {"claude", "codex"})
        if unsupported:
            raise ValueError(
                f"selected_platforms must be claude|codex, got {unsupported}"
            )
    copies = scan_installed_copies(project_root, user_home=user_home)
    duplicates = _find_duplicate_families(
        copies, project_root=project_root, user_home=user_home
    )
    if selected_platforms is not None:
        duplicates = tuple(d for d in duplicates if d.host in selected_platforms)
    removed: list[str] = []
    errors: list[RepairError] = []
    for dup in duplicates:
        copy = dup.user_copy if scope == "user" else dup.project_copy
        base = _scope_root(copy)
        allowed = _host_root_allowlist(base, copy.host, scope)
        # The generic managed-directory symlink refusal would block every dedupe
        # of a linked Claude side (`OURS_HEALTHY`/`OURS_DANGLING` are a symlink at
        # the family dir). Admit those two so `_remove_skill_family` unlinks the
        # link, never the target; every other state keeps the refusal.
        admit_link = copy.host == "claude" and classify_family_link(
            copy.path, base, allowed_symlinks=allowed
        ).state in (FamilyLinkState.OURS_HEALTHY, FamilyLinkState.OURS_DANGLING)
        unsafe = (
            None
            if admit_link
            else _symlinked_skill_install_directory(
                base, copy.host, allowed_symlinks=allowed
            )
        )
        if unsafe is not None:
            message = f"refusing to remove through directory symlink {unsafe}"
            errors.append(RepairError(copy=copy, message=message))
            print(
                f"  dedupe skipped   ->  {scope} {copy.host} {copy.path}: {message}",
                file=sys.stderr,
            )
            continue
        try:
            removed.extend(_remove_skill_family(base, dup.host, scope=scope))
        except OSError as exc:
            errors.append(RepairError(copy=copy, message=str(exc)))
            print(
                f"  dedupe skipped   ->  {scope} {copy.host} {copy.path}: {exc}",
                file=sys.stderr,
            )
            continue
        if dup.host == "codex":
            # As in `uninstall`: Claude-side links into the removed `.agents`
            # tree must not dangle. The sweep never touches `FOREIGN` links.
            dangling = remove_dangling_family_links(
                base, allowed_symlinks=_host_root_allowlist(base, "claude", scope)
            )
            removed.extend(str(path) for path in dangling)
    return DedupeResult(removed=tuple(removed), errors=tuple(errors))


def describe_plan(plan: RepairPlan) -> tuple[str, ...]:
    """Printable summary lines for one repair plan.

    Empty when the plan has no candidate, report or duplicate and Codex is not
    selected, so a clean Claude-only install prints no "active Codex home" line.
    """
    has_findings = bool(plan.to_rewrite or plan.to_report or plan.duplicates)
    if not has_findings and "codex" not in plan.selected_platforms:
        return ()
    lines: list[str] = [f"  repair report    ->  active Codex home: {plan.codex_home}"]
    for candidate in plan.to_rewrite:
        lines.append(
            f"  repair candidate ->  {candidate.copy.scope} {candidate.copy.host} "
            f"{candidate.copy.path} ({candidate.reason})"
        )
    for report in plan.to_report:
        suffix = f" — fix with: {report.remediation}" if report.remediation else ""
        lines.append(
            f"  repair report    ->  {report.scope} {report.host} {report.path}: "
            f"{report.reason}{suffix}"
        )
    for dup in plan.duplicates:
        lines.append(
            f"  duplicate        ->  {dup.host} installed at both "
            f"{dup.user_copy.path} (user) and {dup.project_copy.path} (project); "
            "remove one with --dedupe <user|project>"
        )
    return tuple(lines)


# --- staleness
# Ownership evidence and `_compare_stamp` live in `common.py` (shared with
# `link/`); the import above re-exports them for existing importers.


def _decide_rewrite(
    copy: InstalledCopy,
    *,
    legacy_heading: bool,
    package_version: str,
    force_downgrade: bool,
) -> tuple[bool, str]:
    """Whether one existing copy is proven, stale, and safe to rewrite.

    Assumes the caller already confirmed ``copy.path.is_dir()`` — a family
    whose main dir is missing is never proven here (see
    :func:`_orphaned_sibling_reports` instead).
    """
    if legacy_heading:
        return (
            True,
            "legacy `## Codex host compatibility` preamble (pre-portable-host "
            "install); per-file ownership checks preserve edits",
        )
    if copy.stamp is None:
        return (
            False,
            "no ownership evidence: no .dummyindex_version stamp and no legacy "
            "Codex heading — a dir-name match alone is never enough",
        )
    staleness = _compare_stamp(copy.stamp, package_version)
    if staleness == "older":
        return (
            True,
            f"stamp {copy.stamp} is older than {package_version}; "
            "per-file ownership checks preserve edits",
        )
    if staleness == "equal":
        # Already current — never a rewrite target, and there is nothing for
        # `force_downgrade` to force: it exists to override "newer"/"unknown",
        # not to churn a copy that already matches.
        return (
            False,
            f"stamp {copy.stamp} already matches {package_version}; no rewrite needed",
        )
    if force_downgrade:
        return (
            True,
            f"stamp {copy.stamp!r} is {staleness} vs {package_version}; "
            "--force-downgrade permits preparation; per-file ownership checks preserve edits",
        )
    if staleness == "newer":
        return (
            False,
            f"stamp {copy.stamp} is newer than {package_version}; report-only "
            "(pass --force-downgrade to override)",
        )
    # staleness == "unknown"
    return (
        False,
        f"stamp {copy.stamp!r} is unparseable against {package_version}; "
        "report-only (pass --force-downgrade to override)",
    )


def _orphaned_sibling_reports(copy: InstalledCopy) -> list[RepairReport]:
    """Report every sibling skill still present when the family's main dir is gone."""
    base = _scope_root(copy)
    skills_root = base / skills_root_rel(copy.host)
    reports: list[RepairReport] = []
    for _sub_name, sibling_label in _SIBLING_SKILLS:
        sib_dir = skills_root / sibling_label
        if not sib_dir.exists() and not sib_dir.is_symlink():
            continue
        reports.append(
            RepairReport(
                scope=copy.scope,
                host=copy.host,
                path=sib_dir,
                reason=f"orphaned: family main dir {copy.path} is missing",
                remediation=_remediation_command(copy.scope, copy.host, base=base),
            )
        )
    return reports


def _find_duplicate_families(
    copies: tuple[InstalledCopy, ...],
    *,
    project_root: Path,
    user_home: Path,
) -> tuple[DuplicateFamily, ...]:
    """Pair proven user+project copies of the same host.

    Same-root scopes yield nothing (one physical install seen twice). A pair is
    also skipped when either side is a symlink resolving into the other's scope
    root. A project Claude link into the project's own ``.agents`` still pairs
    with a real user Claude copy: two real Claude surfaces.
    """
    if _same_root(project_root, user_home):
        return ()
    by_host: dict[str, dict[str, InstalledCopy]] = {}
    for copy in copies:
        if not copy.path.is_dir() or not _is_proven(copy):
            continue
        by_host.setdefault(copy.host, {})[copy.scope] = copy
    duplicates: list[DuplicateFamily] = []
    for host, scopes in sorted(by_host.items()):
        if "user" not in scopes or "project" not in scopes:
            continue
        user_copy, project_copy = scopes["user"], scopes["project"]
        if _link_resolves_into_scope_root(
            user_copy, project_root
        ) or _link_resolves_into_scope_root(project_copy, user_home):
            continue
        duplicates.append(
            DuplicateFamily(host=host, user_copy=user_copy, project_copy=project_copy)
        )
    return tuple(duplicates)


def _link_resolves_into_scope_root(copy: InstalledCopy, other_root: Path) -> bool:
    """Whether ``copy.path`` is a symlink resolving inside ``other_root``.

    An `OSError` while resolving means "no", so an unresolvable link keeps the
    pair reported, not hidden. That is safe: `_remove_skill_family` only unlinks
    a linked family dir and never follows it into its target.
    """
    if not copy.path.is_symlink():
        return False
    try:
        resolved = copy.path.resolve(strict=False)
        resolved_other_root = other_root.resolve(strict=False)
    except OSError:
        return False
    return resolved.is_relative_to(resolved_other_root)


def _is_proven(copy: InstalledCopy) -> bool:
    return copy.stamp is not None or _has_legacy_codex_heading(copy.path / "SKILL.md")


def _same_root(a: Path, b: Path) -> bool:
    """Whether ``a`` and ``b`` resolve to the identical physical directory.

    Fails **closed**: when `.resolve()` raises `OSError` (e.g. a symlink
    loop), the roots are treated as possibly the same rather than
    definitely different, so `_find_duplicate_families` skips treating any
    family as a duplicate instead of risking removal of the user's sole
    physical copy.
    """
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return True


# --- path/allowlist helpers


def _scope_root(copy: InstalledCopy) -> Path:
    """Recover the scope root (project dir or user home) under `copy.path`.

    Pure path arithmetic — `skill_rel(host).parent` is always exactly three
    components (`<host_dir>/skills/dummyindex`), so walking up that many
    parents from the family main dir lands back on the original scope root
    regardless of symlinks or how deep that root itself sits.
    """
    depth = len(skill_rel(copy.host).parent.parts)
    return copy.path.parents[depth - 1]


def _host_root_allowlist(base: Path, host: str, scope: str) -> frozenset[Path]:
    """User scope admits a symlinked host root (``.claude``/``.agents``); else none."""
    if scope != "user":
        return frozenset()
    return frozenset({base / skills_root_rel(host).parts[0]})


def _remediation_command(scope: str, host: str, *, base: Path) -> str:
    """The exact `dummyindex install` invocation that would repair one copy."""
    platform_flag = "agents" if host == "codex" else host
    if scope == "project":
        return f"dummyindex install --platform {platform_flag} --scope project --dir {base}"
    return f"dummyindex install --platform {platform_flag} --scope user"
