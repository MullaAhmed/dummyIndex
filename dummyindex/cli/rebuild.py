"""`dummyindex context rebuild` — re-run the backbone (use --changed for incremental)."""
from __future__ import annotations
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .common import (
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
    resolve_doc_paths,
)

if TYPE_CHECKING:
    from dummyindex.context.build.incremental import IncrementalResult


def run(args: list[str]) -> int:
    scope, explicit_root, rest = parse_path_and_root(args)
    doc_values, rest = pull_repeatable_flag(rest, "docs")
    changed_only = "--changed" in rest
    full = "--full" in rest
    rest = [a for a in rest if a not in ("--changed", "--full")]
    if rest:
        print(f"error: unknown argument(s) for `rebuild`: {rest}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    extra_doc_roots = resolve_doc_paths(doc_values, base=Path.cwd())

    try:
        from importlib.metadata import version

        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    if full:
        print(
            "warning: --full forces a full re-cluster. This DISCARDS any "
            "curated feature taxonomy and LLM enrichment (renamed features, "
            "INFERRED specs, enriched tree abstracts) and replaces them with "
            "fresh deterministic community-N stubs.",
            file=sys.stderr,
        )

    if changed_only:
        from dummyindex.context.build.incremental import rebuild_changed

        result = rebuild_changed(
            out_root,
            dummyindex_version=di_version,
            extra_doc_roots=extra_doc_roots,
            full=full,
        )
        if result.skipped:
            print("context rebuild: no source files changed; .context/ unchanged.")
            return 0
        if result.preserved_enriched:
            _print_enriched_summary(result)
            return 0
        ch = result.changes
        print(
            f"context rebuild: {len(ch.added)} added, {len(ch.modified)} modified, "
            f"{len(ch.removed)} removed → rebuilt {result.build_result.context_dir}"
            if result.build_result
            else "rebuild ran"
        )
        return 0

    # Bare `rebuild` (no --changed / --full) is a full re-cluster. On a
    # curated index that DISCARDS the council taxonomy + enrichment, so we
    # REFUSE rather than auto-route — refusing is safer for scripts and hooks
    # that may invoke `rebuild` expecting a cheap refresh. `--full` is the
    # explicit escape hatch; `--changed` takes the non-destructive path.
    if not full:
        from dummyindex.context.build import is_enriched_index

        if is_enriched_index(out_root / ".context"):
            print(
                "error: curated index detected — refusing a full re-cluster. "
                "Pass --full to discard the curated taxonomy + enrichment, or "
                "--changed to refresh deterministic artefacts non-destructively.",
                file=sys.stderr,
            )
            return 2

    from dummyindex.context.build.runner import build_all

    result = build_all(
        scope,
        out_root=out_root,
        dummyindex_version=di_version,
        extra_doc_roots=extra_doc_roots,
    )
    print(
        f"context rebuild: wrote {len(result.written)} files to {result.context_dir}"
    )
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    return 0


def _print_enriched_summary(result: IncrementalResult) -> None:
    """Report the non-destructive enriched-index refresh + reconcile drift."""
    refresh = result.refresh_result
    written = len(refresh.written) if refresh is not None else 0
    print(
        f"context rebuild: enriched index preserved; refreshed {written} "
        "deterministic artefact(s) (no re-cluster)."
    )
    if result.index_desync:
        print(
            "  warning: features/INDEX.json does not list the curated feature "
            "dirs on disk — index desync. Run `dummyindex context refresh-indexes` "
            "or restore INDEX.json from git."
        )
    report = result.reconcile
    if report is not None and report.has_drift:
        if report.drifted_features:
            print(f"  drifted features: {', '.join(report.drifted_features)}")
        if report.removed_files:
            print(f"  removed files:    {', '.join(report.removed_files)}")
        if report.unassigned_new_files:
            print(
                f"  unassigned new files: {', '.join(report.unassigned_new_files)}"
            )
        if report.awaiting_enrichment:
            print(
                f"  awaiting enrichment:  {', '.join(report.awaiting_enrichment)}"
            )
        print(
            "  enriched index preserved; run `/dummyindex --recouncil` to "
            "reconcile enrichment for the drift above."
        )
    else:
        print("  no feature drift detected.")

