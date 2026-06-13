"""`dummyindex context check` — diff snapshotted manifest against current state.

``--versions`` is a separate, detection-only mode: it reports version skew
across the layers that drift independently (running CLI, the repo's installed
skill stamp, the ``.context/meta.json`` stamp) plus a PATH-shadowing venv
binary. It never auto-fixes, never touches the network, and always exits 0 —
the remediation is ``/dummyindex-update``.
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path
from .common import (
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
    resolve_doc_paths,
)
from .rebuild import run as run_rebuild


def run(args: list[str]) -> int:
    """Drift detection. Compare current source hashes to the stored manifest."""
    from dummyindex.context.build.manifest import compare
    from dummyindex.pipeline.io.detect import detect

    scope, explicit_root, rest = parse_path_and_root(args)
    doc_values, rest = pull_repeatable_flag(rest, "docs")
    auto_refresh = False
    quiet = False
    versions = False
    leftover: list[str] = []
    for a in rest:
        if a == "--auto-refresh":
            auto_refresh = True
        elif a == "--quiet":
            quiet = True
        elif a == "--versions":
            versions = True
        else:
            leftover.append(a)
    if leftover:
        print(f"error: unknown argument(s) for `check`: {leftover}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)

    if versions:
        return _run_version_check(out_root, quiet=quiet)

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
        for label, paths in (("added", drift.added), ("modified", drift.modified), ("removed", drift.removed)):
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
    rc = run_rebuild(["--changed", str(scope)] + (["--root", str(explicit_root)] if explicit_root else []))
    return rc


# ----- version skew detection (--versions) ----------------------------------
#
# The seams below are tiny so they can be monkeypatched in tests and kept
# import-light. All four are best-effort and never raise — a missing layer is
# reported as "unknown", never an error. Detection only: the remediation is
# always ``/dummyindex-update`` (which owns the latest-vs-installed network
# check). This command MUST always exit 0 so a SessionStart hook can run it
# without ever blocking a session.


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


def _read_skill_stamp(out_root: Path) -> str | None:
    """The repo's installed skill stamp, falling back to the user-scope one."""
    rel = Path(".claude") / "skills" / "dummyindex" / ".dummyindex_version"
    for base in (out_root, Path.home()):
        stamp = base / rel
        try:
            text = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return None


def _read_meta_version(out_root: Path) -> str | None:
    """The ``.context/meta.json`` ``dummyindex_version`` stamp, if present."""
    meta_path = out_root / ".context" / "meta.json"
    try:
        from dummyindex.context.build.meta import read_meta

        return read_meta(meta_path).dummyindex_version
    except Exception:
        return None


def _run_version_check(out_root: Path, *, quiet: bool) -> int:
    """Report version skew across the running CLI, the repo skill stamp, the
    ``.context/meta.json`` stamp, and a PATH-shadowing venv binary.

    Warn-only — always returns 0. Detection, not auto-fix.
    """
    running = _running_version()
    skill = _read_skill_stamp(out_root)
    meta = _read_meta_version(out_root)

    layers = [
        ("running CLI", running),
        ("repo skill", skill),
        (".context stamp", meta),
    ]
    known = [(label, v) for label, v in layers if v is not None]
    distinct = {v for _, v in known}

    lines: list[str] = []
    for label, v in layers:
        lines.append(f"  {label:<16} {v if v is not None else 'unknown'}")

    # PATH-shadow: the running binary differs from what PATH resolves to.
    running_bin = _running_binary()
    global_bin = _global_binary()
    shadowed = (
        running_bin is not None
        and global_bin is not None
        and running_bin != global_bin
    )

    if len(distinct) > 1:
        print("context check: version skew detected across dummyindex layers:")
        for line in lines:
            print(line)
        print(
            "  remediation: run /dummyindex-update to bring every layer to the "
            "latest release."
        )
    elif not quiet:
        coherent = next(iter(distinct), "unknown")
        print(f"context check: dummyindex versions coherent ({coherent}).")

    if shadowed:
        print(
            f"  warning: a repo-local dummyindex ({running_bin}) is shadowing the "
            f"global CLI on PATH ({global_bin}); they may be different versions. "
            "Run /dummyindex-update against the install you actually want."
        )

    return 0

