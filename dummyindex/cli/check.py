"""`dummyindex context check`: diff the snapshotted manifest against current state.

``--versions`` is a separate detection-only mode: it reports version skew across the
running CLI, the Claude and Codex skill stamps at repo and user scope, and the
``.context/meta.json`` stamp, plus a PATH-shadowing venv binary. It never auto-fixes,
never touches the network and always exits 0; remediation is ``dummyindex-update``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .common import (
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
    resolve_doc_paths,
)
from .rebuild import run as run_rebuild

if TYPE_CHECKING:
    from dummyindex.context.domains.docbudget import BudgetGroup

_Groups = tuple[tuple["BudgetGroup", str], ...]


def run(args: list[str]) -> int:
    """Drift detection. Compare current source hashes to the stored manifest."""
    from dummyindex.context.build.manifest import compare
    from dummyindex.pipeline.io.detect import detect

    scope, explicit_root, rest = parse_path_and_root(args)
    doc_values, rest = pull_repeatable_flag(rest, "docs")
    auto_refresh = False
    quiet = False
    versions = False
    budget = False
    style = False
    update_ratchet = False
    refs = False
    leftover: list[str] = []
    for a in rest:
        if a == "--auto-refresh":
            auto_refresh = True
        elif a == "--quiet":
            quiet = True
        elif a == "--versions":
            versions = True
        elif a == "--budget":
            budget = True
        elif a == "--style":
            style = True
        elif a == "--update-ratchet":
            update_ratchet = True
        elif a == "--refs":
            refs = True
        else:
            leftover.append(a)
    if leftover:
        print(f"error: unknown argument(s) for `check`: {leftover}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)

    if update_ratchet and not (budget or style):
        print("error: --update-ratchet requires --budget or --style", file=sys.stderr)
        return 2
    if versions:
        return _run_version_check(out_root, quiet=quiet)
    if budget or style or refs:
        rc = 0
        if budget:
            rc = _run_ratchet_check(
                out_root, _budget_groups(), update=update_ratchet, flag="--budget"
            )
        if style:
            rc = max(
                rc,
                _run_ratchet_check(
                    out_root, _style_groups(), update=update_ratchet, flag="--style"
                ),
            )
        if refs:
            rc = max(rc, _run_refs_check(out_root))
        return rc

    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        if not quiet:
            print(
                f"error: {context_dir} not found. Run `dummyindex ingest` first.",
                file=sys.stderr,
            )
        return 2

    extra_doc_roots = resolve_doc_paths(doc_values, base=Path.cwd())

    # Detect current source files. Use scope for the scan (matches build_all).
    # We include in-repo docs (document + paper file types) in the drift
    # comparison so doc edits don't show up as "removed" — the manifest
    # tracks them via build_all.
    detection = detect(
        scope.resolve() if scope.is_absolute() else (Path.cwd() / scope).resolve(),
        extra_doc_roots=tuple(extra_doc_roots),
    )
    files_map = detection.get("files", {}) or {}
    current: list[Path] = [Path(p) for p in files_map.get("code", [])]
    for ftype in ("document", "paper"):
        for raw in files_map.get(ftype, []) or []:
            p = Path(raw)
            # Skip external doc roots — those aren't repo-relative, so the
            # manifest never stored them.
            try:
                p.resolve().relative_to(out_root.resolve())
            except ValueError:
                continue
            current.append(p)

    drift = compare(context_dir, root=out_root, current_files=current)

    if drift.is_clean:
        if not quiet:
            print("context check: clean (no drift)")
        return 0

    if not quiet:
        print(
            f"context check: drift detected — "
            f"{len(drift.added)} added, {len(drift.modified)} modified, "
            f"{len(drift.removed)} removed"
        )
        # Don't dump every file when there's a lot — first 5 of each.
        for label, paths in (
            ("added", drift.added),
            ("modified", drift.modified),
            ("removed", drift.removed),
        ):
            if not paths:
                continue
            sample = paths[:5]
            print(f"  {label}:")
            for p in sample:
                print(f"    - {p}")
            if len(paths) > len(sample):
                print(f"    ... +{len(paths) - len(sample)} more")

    if not auto_refresh:
        # Exit code 1 signals drift exists (useful for shell scripts).
        return 1

    # Auto-refresh: run rebuild --changed.
    if not quiet:
        print("context check: auto-refreshing…")
    rc = run_rebuild(
        ["--changed", str(scope)]
        + (["--root", str(explicit_root)] if explicit_root else [])
    )
    return rc


# ----- ratchets (--budget, --style), disposable citations (--refs) -----------


def _budget_groups() -> _Groups:
    from dummyindex.context.domains.docbudget import BudgetGroup
    from dummyindex.context.domains.docbudget.constants import (
        CONTEXT_RATCHET_REL,
        SKILLS_RATCHET_REL,
    )

    return (
        (BudgetGroup.CONTEXT, CONTEXT_RATCHET_REL),
        (BudgetGroup.SKILLS, SKILLS_RATCHET_REL),
    )


def _style_groups() -> _Groups:
    from dummyindex.context.domains.docbudget import BudgetGroup
    from dummyindex.context.domains.docbudget.constants import STYLE_RATCHET_REL

    return ((BudgetGroup.STYLE, STYLE_RATCHET_REL),)


def _print_style_details(root: Path, rel: str) -> None:
    from dummyindex.context.domains.docbudget import lint_text

    for v in lint_text((root / rel).read_text(encoding="utf-8")):
        print(f"{rel}:{v.line}: {v.rule}: {v.excerpt}")


def _run_ratchet_check(
    root: Path,
    groups: _Groups,
    *,
    update: bool,
    flag: str,
) -> int:
    """Check or update each (group, ratchet) pair. rc 1 on growth or refusal."""
    from dummyindex.context.domains.docbudget import (
        BudgetGroup,
        read_ratchet,
        write_ratchet,
    )
    from dummyindex.context.domains.docbudget import (
        check as budget_check,
    )
    from dummyindex.context.domains.docbudget import (
        scan as budget_scan,
    )
    from dummyindex.context.domains.docbudget import (
        update_ratchet as run_update,
    )

    rc = 0
    checked = False
    for group, rel in groups:
        is_style = group is BudgetGroup.STYLE
        unit = "violations" if is_style else "words"
        ratchet_path = root / rel
        if is_style and not update and not ratchet_path.is_file():
            for path, count in budget_scan(root, group).items():
                if count:
                    _print_style_details(root, path)
            print(
                "no style ratchet; seed it with: "
                "dummyindex context check --style --update-ratchet"
            )
            continue
        try:
            ratchet = read_ratchet(ratchet_path)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if update:
            result = run_update(root, ratchet, group)
            write_ratchet(ratchet_path, result.ratchet)
            print(
                f"{rel}: {len(result.ratchet)} entries, {len(result.lowered)} lowered"
            )
            for v in result.refused:
                print(f"  refused: {v.path} grew {v.recorded} -> {v.words} {unit}")
                rc = 1
            continue
        checked = True
        for v in budget_check(root, ratchet, group):
            if v.recorded is None:
                print(f"over budget: {v.path} {v.words} {unit} (ceiling {v.limit})")
            else:
                print(f"grew: {v.path} {v.words} {unit} (recorded {v.recorded})")
            if is_style:
                _print_style_details(root, v.path)
            rc = 1
    if rc == 0 and checked and not update:
        print(f"context check {flag}: ok")
    return rc


def _run_refs_check(root: Path) -> int:
    """List durable docs citing proposals/audits. rc 1 if any."""
    from dummyindex.context.domains.docguard.citations import scan_durable

    hits = scan_durable(root)
    for path, cites in hits:
        print(f"{path}: {', '.join(cites)}")
    if not hits:
        print("context check --refs: clean")
        return 0
    return 1


# ----- version skew detection (--versions) ----------------------------------
#
# The seams below are tiny so they can be monkeypatched in tests and kept
# import-light. All probes are best-effort and never raise — a missing layer is
# reported as "unknown", never an error. Detection only: remediation is the
# installed ``dummyindex-update`` skill (which owns the latest-vs-installed
# network check). This command MUST always exit 0 so a SessionStart hook can
# run it without ever blocking a session.


def _running_version() -> str | None:
    """The version of the dummyindex package currently executing."""
    try:
        from importlib.metadata import version

        return version("dummyindex")
    except Exception:
        return None


def _running_binary() -> Path | None:
    """The resolved path of the binary that launched this process."""
    try:
        return Path(sys.argv[0]).resolve()
    except (OSError, ValueError):
        return None


def _global_binary() -> Path | None:
    """The ``dummyindex`` the user's PATH resolves to (may differ from the
    running binary when a repo venv shadows the global install)."""
    found = shutil.which("dummyindex")
    if not found:
        return None
    try:
        return Path(found).resolve()
    except (OSError, ValueError):
        return None


def _user_home() -> Path:
    """User-home seam kept explicit so scope discovery is testable."""
    return Path.home()


_SCOPE_LABEL = {"project": "repo", "user": "user"}
_HOST_LABEL = {"claude": "Claude skill", "codex": "Codex skill"}


def _read_skill_stamps(out_root: Path) -> tuple[tuple[str, str | None], ...]:
    """Read every Claude/Codex stamp at repo and user scope independently.

    Wraps ``installer.repair``'s four-root scanner so `--versions` and repair agree
    on "installed"; a missing or empty stamp stays ``None`` for that layer. Never
    short-circuit, or a stale second host hides behind the first stamp checked.
    Claude rows also get a ``classify_family_link`` suffix (`` (linked)``, or
    `` (materialized link ...)`` with the `core.symlinks` fix); an error means none.
    """
    from dummyindex.installer.link import FamilyLinkState, classify_family_link
    from dummyindex.installer.repair import scan_installed_copies

    user_home = _user_home()
    copies = scan_installed_copies(out_root, user_home=user_home)
    rows: list[tuple[str, str | None]] = []
    for copy in copies:
        label = f"{_SCOPE_LABEL[copy.scope]} {_HOST_LABEL[copy.host]}"
        if copy.host == "claude":
            scope_root = out_root if copy.scope == "project" else user_home
            # Same allowlist shape as `install.py`'s `claude_link_allowlist`:
            # empty at project scope, the two host-root entries at user
            # scope — never derived from `$HOME`.
            allowed_symlinks = (
                frozenset({scope_root / ".claude", scope_root / ".claude" / "skills"})
                if copy.scope == "user"
                else frozenset()
            )
            try:
                classification = classify_family_link(
                    copy.path, scope_root, allowed_symlinks=allowed_symlinks
                )
            except Exception:
                classification = None
            if classification is not None:
                if classification.state in (
                    FamilyLinkState.OURS_HEALTHY,
                    FamilyLinkState.OURS_DANGLING,
                ):
                    label += " (linked)"
                elif classification.state is FamilyLinkState.MATERIALIZED:
                    label += (
                        " (materialized link — run `git config core.symlinks "
                        "true` and re-checkout)"
                    )
        rows.append((label, copy.stamp))
    return tuple(rows)


def _read_meta_version(out_root: Path) -> str | None:
    """The ``.context/meta.json`` ``dummyindex_version`` stamp, if present."""
    meta_path = out_root / ".context" / "meta.json"
    try:
        from dummyindex.context.build.meta import read_meta

        return read_meta(meta_path).dummyindex_version
    except Exception:
        return None


def _skill_source_warnings(out_root: Path) -> tuple[str, ...]:
    """Keep source identity distinct from package version equality."""
    from dummyindex.installer.install.family_write import (
        expected_families,
        reference_skill,
    )
    from dummyindex.installer.ownership import read_manifest, source_status
    from dummyindex.installer.repair import scan_installed_copies

    warnings: list[str] = []
    for copy in scan_installed_copies(out_root, user_home=_user_home()):
        if copy.path.is_symlink() and not (copy.path / "SKILL.md").is_file():
            warnings.append(
                f"{copy.scope} {copy.host} source: broken shared reference; SKILL.md is missing"
            )
            continue
        if not copy.path.is_dir():
            continue
        platform = (
            "codex" if copy.host == "codex" or copy.path.is_symlink() else "claude"
        )
        expected = expected_families(platform)
        problems: list[str] = []
        for family, files in expected.items():
            directory = copy.path.parent / family
            manifest = read_manifest(directory)
            if manifest is not None and manifest.get("layout") == "reference":
                base = directory.parents[2]
                canonical = expected_families("codex")[family]["SKILL.md"]
                files = {"SKILL.md": reference_skill(base, family, canonical)}
            reason = source_status(directory, files)
            if reason:
                problems.append(f"{family}: {reason}")
        if problems:
            sample = "; ".join(problems[:2])
            extra = f"; +{len(problems) - 2} more" if len(problems) > 2 else ""
            warnings.append(f"{copy.scope} {copy.host} source: {sample}{extra}")
    return tuple(warnings)


def _run_version_check(out_root: Path, *, quiet: bool) -> int:
    """Report version skew across CLI, every host/scope skill, context stamp,
    and a PATH-shadowing venv binary.

    Warn-only — always returns 0. Detection, not auto-fix.
    """
    running = _running_version()
    skills = _read_skill_stamps(out_root)
    meta = _read_meta_version(out_root)

    layers = [
        ("running CLI", running),
        *skills,
        (".context stamp", meta),
    ]
    known = [(label, v) for label, v in layers if v is not None]
    distinct = {v for _, v in known}

    lines: list[str] = []
    for label, v in layers:
        lines.append(f"  {label:<19} {v if v is not None else 'unknown'}")

    # PATH-shadow: the running binary differs from what PATH resolves to.
    running_bin = _running_binary()
    global_bin = _global_binary()
    shadowed = (
        running_bin is not None and global_bin is not None and running_bin != global_bin
    )

    if len(distinct) > 1:
        print("context check: version skew detected across dummyindex layers:")
        for line in lines:
            print(line)
        print(
            "  remediation: invoke the `dummyindex-update` skill for each "
            "installed host/scope pair to bring every layer to one release."
        )
    elif not quiet:
        coherent = next(iter(distinct), "unknown")
        print(f"context check: dummyindex versions coherent ({coherent}).")
        # "Versions agree" alone would hide that the Claude side is a link (or a
        # materialized placeholder needing core.symlinks), so print those rows.
        for line in lines:
            if "(linked)" in line or "(materialized link" in line:
                print(line)

    if shadowed:
        print(
            f"  warning: a repo-local dummyindex ({running_bin}) is shadowing the "
            f"global CLI on PATH ({global_bin}); they may be different versions. "
            "Invoke the `dummyindex-update` skill from the install you intend "
            "to run."
        )

    from dummyindex.installer.ownership import package_source_hash

    try:
        source_warnings = _skill_source_warnings(out_root)
        running_source = package_source_hash()
    except (OSError, ValueError) as exc:
        source_warnings = (f"source verification unavailable: {exc}",)
        running_source = "unavailable"
    if source_warnings or not quiet:
        print(f"  running CLI source: {running_source}")
        for warning in source_warnings:
            print(f"  warning: {warning}")

    return 0
