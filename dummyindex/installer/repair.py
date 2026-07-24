"""`dummyindex install` repair — scoped, evidence-gated, symlink-safe.

Rerunning ``install`` (directly, or via the ``dummyindex-update`` skill) does
more than restamp the version: it repairs skill-family copies an older
dummyindex version left behind, within tight scope and safety bounds. This
module is the single place that logic lives:

- **The scanner** (:func:`scan_installed_copies`) is the one four-root
  ``.dummyindex_version`` scan in the codebase. It used to be duplicated as
  ``cli/check.py``'s ``_read_skill_stamps``; that function is now a thin
  label-formatting wrapper around this scanner, so ``check --versions`` and
  repair can never drift on what "installed" means.
- **The plan** (:func:`plan_repairs`) classifies every detected copy as a
  rewrite candidate or a report line, gated on ownership evidence, staleness,
  and symlink safety — never on a bare directory-name match.
- **The executor** (:func:`execute_repairs`) rewrites only the plan's proven
  candidates, reusing the exact primitive ``install()`` already uses
  (``_install_skill_family``), with per-copy error isolation mirroring
  ``AgentsMdCleanupResult``.
- **Dedupe** (:func:`dedupe`) removes one scope's copy of a family proven
  installed at both user and project scope, via ``_remove_skill_family`` —
  never the full ``uninstall()`` orchestration, so commands and managed
  guidance blocks are untouched. An optional ``selected_platforms`` further
  restricts REMOVAL to matching hosts, mirroring the platform×scope model
  ``plan_repairs``/``execute_repairs`` already enforce — deletion is a
  stricter form of write, so it must obey the same scoping. The informational
  duplicate report (``plan.duplicates``) always lists every detected
  duplicate; only removal is filtered. Re-runs the same symlink preflight
  ``execute_repairs`` runs immediately before each family's removal, and is
  best-effort per family: one failing family reports and continues rather
  than aborting the rest (mirrors :class:`RepairExecutionResult`'s isolation
  contract via :class:`DedupeResult`).

Deliberately out of scope here (Wave 4's job): wiring any of this into
``install()``, and refreshing managed ``CLAUDE.md``/``AGENTS.md`` blocks —
those go through the existing ownership-aware bootstrap primitives already,
unrelated to the skill-family tree this module repairs. That is also why
these functions take no ``skill_only`` flag: the skill-family tree they
repair is exactly what ``_install_skill_family`` already writes unconditionally
regardless of ``--skill-only`` in ``install()`` today, so there is nothing
here for that flag to gate.
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

    ``path`` is the family's main skill directory (e.g.
    ``…/.claude/skills/dummyindex``), never the stamp file itself. ``stamp``
    is the raw text read from ``.dummyindex_version`` under it, or ``None``
    when the stamp is missing, empty, or unreadable — mirroring the layer
    semantics ``check --versions`` already reports (never raises, never
    short-circuits: every root is read independently).
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

    ``remediation`` is ``None`` for a purely informational report — an
    `OURS_HEALTHY` linked family is current and has nothing to fix, so
    `describe_plan` must not print a `-- fix with:` suffix for it. Every
    other report (a real problem: dangling link, materialized file, foreign
    refusal, staleness, migration candidate) supplies a real remediation.
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

    ``selected_platforms`` is carried through from the `plan_repairs` call
    that built this plan so `describe_plan` can tell "nothing to report" from
    "nothing to report, but Codex is involved" without a second parameter.
    """

    to_rewrite: tuple[RepairCandidate, ...]
    to_report: tuple[RepairReport, ...]
    duplicates: tuple[DuplicateFamily, ...]
    codex_home: Path
    selected_platforms: tuple[str, ...]


@dataclass(frozen=True)
class RepairError:
    """One rewrite or dedupe-removal candidate whose action failed independently.

    Shared between :func:`execute_repairs` and :func:`dedupe` — both catch a
    per-copy failure, wrap it in this same shape, and print one stderr line
    rather than letting it abort the rest of the run.
    """

    copy: InstalledCopy
    message: str


@dataclass(frozen=True)
class RepairExecutionResult:
    """Independent per-copy outcomes for one `execute_repairs` run.

    Mirrors `AgentsMdCleanupResult`'s isolation contract: a budget-exceeded
    block, an `UnbalancedMarkersError`-style hand-damage, or a plain `OSError`
    on one copy is caught, reported once on stderr, and never blocks the
    rest. ``reported`` is `plan.to_report` passed straight through, so a
    caller has one object describing the whole run — what was rewritten,
    what stayed report-only, and what one copy's failure looked like.
    """

    repaired: tuple[InstalledCopy, ...]
    reported: tuple[RepairReport, ...]
    errors: tuple[RepairError, ...]


@dataclass(frozen=True)
class DedupeResult:
    """Independent per-family outcomes for one `dedupe` run.

    Mirrors `RepairExecutionResult`'s isolation contract: a symlinked scope
    root is refused-and-reported, and a plain `OSError` removing one
    duplicate family is caught, reported once on stderr, and never blocks
    the rest. ``removed`` is every path successfully removed across all
    families; ``errors`` is one `RepairError` per family that was refused or
    failed.
    """

    removed: tuple[str, ...]
    errors: tuple[RepairError, ...]


def scan_installed_copies(
    out_root: Path, *, user_home: Path | None = None
) -> tuple[InstalledCopy, ...]:
    """Scan the four canonical roots for an installed skill family.

    Returns exactly four entries, in this fixed order: project/claude,
    project/codex, user/claude, user/codex — the same order `check
    --versions` has always printed. A missing or unreadable stamp reports
    ``stamp=None`` for that layer; the location is still enumerated (unlike a
    plain directory listing) so a caller can tell "we looked and found
    nothing" from "we never looked".
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
    """Classify one Claude-host copy via `classify_family_link` BEFORE any
    ownership/staleness decision runs. Repair writes no links itself
    (`create_family_links` is the single write owner) — every branch here
    only reports:

    - `OURS_HEALTHY` -> reported as already-linked, current; NEVER a rewrite
      candidate. Staleness is evaluated and repaired on the Codex row only
      (the real target the link points at). Carries no remediation — a
      healthy, current link is informational, not a problem to fix.
    - `OURS_DANGLING` / `MATERIALIZED` -> reported; the same run's
      `create_family_links` heals both under AUTO/LINK, so the report names
      the COPY-mode remediation instead.
    - `FOREIGN` -> today's refusal path: reuses
      `_symlinked_skill_install_directory`'s exact message shape whenever it
      applies (the leaf/parent-chain symlink cases this state is built from),
      so the refusal text never drifts from what already shipped.
    - `NOT_A_LINK` alongside a proven same-scope Codex family -> reported as
      a migration candidate (a plain reinstall converts it once claude is
      selected). A `NOT_A_LINK` copy with no proven Codex sibling, and
      `MISSING`, return ``None`` so the caller's pre-existing
      ownership/staleness/orphaned-sibling logic runs exactly as before.
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

    Scans both scope roots so an out-of-scope copy can still be reported
    with a remediation hint, but only a copy at ``target_scope``'s root, for
    a host in ``selected_platforms``, is ever a rewrite candidate — every
    other detected copy is report-only, even when it is independently stale.
    ``skill_only`` is accepted only for call-site symmetry with `install()`;
    see the module docstring for why it has no effect here.
    """
    del skill_only  # inert here — see module docstring
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

    Best-effort per copy: a failure on one candidate prints a single stderr
    report line and never blocks the rest. Reuses the exact rendering path
    `install()` uses (``_install_skill_family``) so a repaired copy is
    byte-identical to a fresh install — and re-runs the symlink preflight
    immediately before writing, in case the filesystem changed between
    planning and execution.
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
            _install_skill_family(base, copy.host, src)
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
    """Remove ``scope``'s copy of every family proven duplicated at both scopes.

    Never calls the `uninstall()` entry point and never touches slash
    commands or managed guidance blocks — only `_remove_skill_family`, the
    same no-follow primitive `uninstall()` itself now uses. A repo whose two
    scope roots resolve to the same directory (home == project) never has a
    duplicate, so this is a silent no-op there; likewise when nothing at
    ``scope`` is proven to exist at both scopes.

    ``selected_platforms``, when given, restricts REMOVAL to duplicate
    families whose host is in it — deletion is a stricter form of write and
    must obey the same platform×scope model `plan_repairs`/`execute_repairs`
    already enforce, so ``install --platform claude --dedupe project`` never
    removes an ``.agents`` (codex) duplicate. The informational duplicate
    report (`plan_repairs`'s ``plan.duplicates``) stays unfiltered — only
    this removal is scoped. ``None`` (the default, and every pre-existing
    direct caller) removes every proven duplicate regardless of host,
    matching the behavior before this scoping existed.

    Best-effort per family, exactly like `execute_repairs`: before removing,
    re-runs the identical symlink preflight install/repair use against the
    family's scope root, refusing (and reporting) a symlinked component
    rather than removing through it; an `OSError` from `_remove_skill_family`
    is caught, reported once on stderr, and never blocks the remaining
    duplicate families.

    After successfully removing a **codex** family, also sweeps
    `remove_dangling_family_links` on that same scope root — the shared
    primitive `uninstall` uses for the same purpose — so a Claude-side link
    into the just-removed `.agents` tree never dangles just because this
    removal came from dedupe instead of uninstall. Removing a **claude**
    family never triggers this sweep (there is nothing on the Claude side
    for it to protect in that direction); a linked Claude side being deduped
    is itself removed as a link only, never its target — `_remove_skill_family`
    already never follows a symlinked family dir (`uninstall.py`).
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
        # `_symlinked_skill_install_directory`'s generic "never traverse a
        # managed-directory symlink" refusal predates link mode and would
        # otherwise refuse EVERY dedupe of a legitimately linked Claude side
        # (`OURS_HEALTHY`/`OURS_DANGLING` are exactly a symlink at the family
        # dir position) — admit those two states so `_remove_skill_family`'s
        # own no-follow unlink runs and removes the LINK, never the target.
        # Every other state (a real dir with a foreign companion-dir symlink,
        # or a genuinely FOREIGN family-dir symlink) keeps today's refusal.
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
            # Mirrors the sweep `uninstall` runs after removing a codex
            # family (`remove_dangling_family_links`): a Claude-side link
            # pointing at the `.agents` tree just removed here must not be
            # left dangling just because this removal came from dedupe
            # rather than uninstall. `FOREIGN` links (and every other
            # non-dangling state) are left untouched by the sweep itself.
            dangling = remove_dangling_family_links(
                base, allowed_symlinks=_host_root_allowlist(base, "claude", scope)
            )
            removed.extend(str(path) for path in dangling)
    return DedupeResult(removed=tuple(removed), errors=tuple(errors))


def describe_plan(plan: RepairPlan) -> tuple[str, ...]:
    """Printable summary lines for one repair plan (Wave 4 prints these).

    Silent when there is nothing to say: no rewrite candidate, no
    report-only copy, no duplicate, and Codex isn't among this invocation's
    selected platforms. A clean Claude-only install with an empty plan
    prints nothing, instead of an "active Codex home" line that has no
    bearing on what just ran.
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


# ----- staleness --------------------------------------------------------------
#
# Ownership evidence (`_read_stamp`, `_has_legacy_codex_heading`,
# `is_owned_copy`, `_VERSION_STAMP_NAME`, `_LEGACY_CODEX_HEADING_RE`) now
# lives in `common.py` (the shared bottom layer `link.py` also needs); the
# names above are re-exported via the `.common` import at the top of this
# module so every existing importer keeps working unchanged. `_compare_stamp`
# also now lives in `common.py` — the comparator `installer/install/
# link_dispatch.py`'s `_agents_family_stamp_state` used to duplicate
# independently (confirmed to agree on every ordering) — imported unchanged
# from there above, so this module's own call sites below are untouched.


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
            "install) — hand-edits to this installed copy are not preserved",
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
            f"stamp {copy.stamp} is older than {package_version} — hand-edits "
            "to this installed copy are not preserved",
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
            "--force-downgrade forced the rewrite — hand-edits to this "
            "installed copy are not preserved",
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

    A repo whose two scope roots resolve to the same directory never has a
    duplicate — that would just be one physical install seen twice.

    Pairing is same-host across scopes, so a Claude link and its own
    ``.agents`` target never pair (different host rows entirely). The real
    interplay is cross-scope, same-host: a user-scope REAL Claude copy
    alongside a project-scope Claude LINK that resolves to the PROJECT's own
    ``.agents`` family is a genuine duplicate (two real Claude surfaces) and
    stays reported. `_link_resolves_into_scope_root` excludes a pair ONLY in
    the narrower one-physical-copy-seen-twice case: one side is itself a
    symlink whose target resolves into the OTHER side's scope root (e.g. a
    project `.claude` copy symlinked straight at the user's own `.claude`
    copy, rather than at the project's `.agents` tree) — checked in both
    directions.
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
    """Whether ``copy.path``, if it is itself a symlink, resolves inside
    ``other_root`` — the one-physical-copy-seen-twice case
    `_find_duplicate_families` excludes.

    Fails **closed** like `_same_root`: any `OSError` resolving either side
    is treated as "does not resolve into the other root", so an unresolvable
    link keeps the pair REPORTED rather than silently hidden. Reporting
    carries no removal risk either way here — `_remove_skill_family` only
    ever unlinks a linked family dir, never follows into its target, so a
    false-negative "duplicate" costs nothing more than an informational line.
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


# ----- path/allowlist helpers -------------------------------------------------


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
    """Mirror `install()`'s user-scope dotfiles-symlink allowance exactly."""
    if scope != "user":
        return frozenset()
    return frozenset({base / skills_root_rel(host).parts[0]})


def _remediation_command(scope: str, host: str, *, base: Path) -> str:
    """The exact `dummyindex install` invocation that would repair one copy."""
    platform_flag = "agents" if host == "codex" else host
    if scope == "project":
        return f"dummyindex install --platform {platform_flag} --scope project --dir {base}"
    return f"dummyindex install --platform {platform_flag} --scope user"
