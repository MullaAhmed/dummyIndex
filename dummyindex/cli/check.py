"""`dummyindex context check` — diff snapshotted manifest against current state."""
from __future__ import annotations
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
    leftover: list[str] = []
    for a in rest:
        if a == "--auto-refresh":
            auto_refresh = True
        elif a == "--quiet":
            quiet = True
        else:
            leftover.append(a)
    if leftover:
        print(f"error: unknown argument(s) for `check`: {leftover}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
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

