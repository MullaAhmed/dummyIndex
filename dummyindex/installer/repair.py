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

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dummyindex.codex_guidance import codex_home

from .common import (
    _SIBLING_SKILLS,
    PACKAGE_VERSION,
    _skill_src,
    skill_rel,
    skills_root_rel,
)
from .install import _install_skill_family, _symlinked_skill_install_directory
from .uninstall import _remove_skill_family

_VERSION_STAMP_NAME = ".dummyindex_version"
_LEGACY_CODEX_HEADING_RE = re.compile(r"(?m)^## Codex host compatibility\b")


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
    """A detected copy left untouched, with why and the exact fix command."""

    scope: str
    host: str
    path: Path
    reason: str
    remediation: str


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


def _read_stamp(stamp_path: Path) -> str | None:
    try:
        value = stamp_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


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
        unsafe = _symlinked_skill_install_directory(
            base,
            copy.host,
            allowed_symlinks=_host_root_allowlist(base, copy.host, scope),
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
        lines.append(
            f"  repair report    ->  {report.scope} {report.host} {report.path}: "
            f"{report.reason} — fix with: {report.remediation}"
        )
    for dup in plan.duplicates:
        lines.append(
            f"  duplicate        ->  {dup.host} installed at both "
            f"{dup.user_copy.path} (user) and {dup.project_copy.path} (project); "
            "remove one with --dedupe <user|project>"
        )
    return tuple(lines)


# ----- ownership evidence + staleness ----------------------------------------


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


def _parse_version(value: str | None) -> tuple[int, ...] | None:
    """Parse a plain dotted-integer version (e.g. "0.33.0"); ``None`` otherwise.

    dummyindex has no runtime dependency on `packaging`, and every version
    this project has ever cut is dotted integers, so a tiny local parser —
    not a new dependency — is the right-sized fix. A stray `v` prefix, a
    pre-release suffix, `"unknown"`, empty, or missing all parse to `None`;
    callers treat that as unresolvable, never as "older".
    """
    if not value:
        return None
    try:
        return tuple(int(part) for part in value.strip().split("."))
    except ValueError:
        return None


def _compare_stamp(stamp: str, package_version: str) -> str:
    """Return "older" | "equal" | "newer" | "unknown" for one stamp."""
    parsed_stamp = _parse_version(stamp)
    parsed_package = _parse_version(package_version)
    if parsed_stamp is None or parsed_package is None:
        return "unknown"
    if parsed_stamp < parsed_package:
        return "older"
    if parsed_stamp > parsed_package:
        return "newer"
    return "equal"


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
    """
    if _same_root(project_root, user_home):
        return ()
    by_host: dict[str, dict[str, InstalledCopy]] = {}
    for copy in copies:
        if not copy.path.is_dir() or not _is_proven(copy):
            continue
        by_host.setdefault(copy.host, {})[copy.scope] = copy
    return tuple(
        DuplicateFamily(
            host=host, user_copy=scopes["user"], project_copy=scopes["project"]
        )
        for host, scopes in sorted(by_host.items())
        if "user" in scopes and "project" in scopes
    )


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
