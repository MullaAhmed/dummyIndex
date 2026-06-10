"""`dummyindex context reconcile` / `reconcile-stamp` — the commit-anchored update.

``reconcile`` is **read-only**: it diffs the persisted anchor
(``meta.indexed_commit``) against HEAD + the working tree and prints what the
council must act on — drifted features, removed files, unassigned new files,
and features still awaiting enrichment. ``--json`` emits the same report for
the council procedure to consume.

``reconcile-stamp`` is the **write boundary**: it advances the anchor to HEAD
once the council has reconciled the report. It refuses (exit 1) while
unassigned files or awaiting-enrichment features remain, unless ``--force``.
The two verbs are split deliberately — the enum is one-verb-per-mutation, so a
read default never hides a write behind a flag.
"""
from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, TextIO

from .common import parse_path_and_root, resolve_context_root

if TYPE_CHECKING:
    from dummyindex.context.build.reconcile import ReconcileReport


def run(args: list[str]) -> int:
    scope, explicit_root, rest = parse_path_and_root(args)
    want_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if rest:
        print(f"error: unknown argument(s) for `reconcile`: {rest}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    from dummyindex.context.build.reconcile import compute_reconcile_report

    report = compute_reconcile_report(context_dir, out_root)
    if want_json:
        print(json.dumps(_report_to_dict(report), indent=2))
        return 0
    _print_report(report)
    return 0


def run_stamp(args: list[str]) -> int:
    scope, explicit_root, rest = parse_path_and_root(args)
    force = "--force" in rest
    rest = [a for a in rest if a != "--force"]
    if rest:
        print(
            f"error: unknown argument(s) for `reconcile-stamp`: {rest}",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    from dummyindex.context.build.reconcile import stamp_reconciled

    result = stamp_reconciled(context_dir, out_root, force=force)

    if result.refused:
        print(
            "context reconcile-stamp: REFUSED — un-reconciled work remains "
            "(advancing the anchor would silently forget it):",
            file=sys.stderr,
        )
        _print_blockers(result.report, stream=sys.stderr)
        print(
            "  Reconcile them (place files, enrich features) or re-run with "
            "--force to anchor anyway.",
            file=sys.stderr,
        )
        return 1

    if result.off_git:
        # A successful no-op (exit 0) → informational, so stdout per §12.
        print(
            "context reconcile-stamp: not a git repo (or unborn HEAD); no "
            "commit to anchor. The index falls back to hash-manifest drift "
            "detection — nothing to stamp."
        )
        return 0

    if result.stamped_commit is None:
        print(
            "error: no readable meta.json to stamp. Run `dummyindex ingest` "
            "first.",
            file=sys.stderr,
        )
        return 1

    print(
        f"context reconcile-stamp: anchor advanced to "
        f"{result.stamped_commit[:12]}"
    )
    if force and (
        result.report.unassigned_new_files or result.report.awaiting_enrichment
    ):
        print(
            "  WARNING: --force advanced the anchor past un-reconciled work, "
            "but did NOT resolve it (markers and untracked files persist). "
            "It WILL be re-reported next reconcile until you place/enrich it "
            "or stop tracking it:",
        )
        _print_blockers(result.report, stream=sys.stdout)
    if result.dirty_source:
        print(
            "  WARNING: uncommitted source changes remain outside .context/. "
            "Since the anchor is now HEAD, that source will re-surface as "
            "drift next reconcile — commit it to settle.",
        )
    return 0


def _report_to_dict(report: "ReconcileReport") -> dict[str, object]:
    return {
        "indexed_commit": report.indexed_commit,
        "drifted_features": list(report.drifted_features),
        "removed_files": list(report.removed_files),
        "unassigned_new_files": list(report.unassigned_new_files),
        "awaiting_enrichment": list(report.awaiting_enrichment),
        "has_drift": report.has_drift,
    }


def _print_report(report: "ReconcileReport") -> None:
    if report.indexed_commit is None:
        print(
            "context reconcile: no anchor commit recorded (non-git repo, or an "
            "index built before commit-anchoring). Commit the repo and re-run "
            "a fresh `dummyindex ingest` to start tracking."
        )
    else:
        print(f"context reconcile: anchor {report.indexed_commit[:12]}")
    if not report.has_drift:
        print("  in sync — nothing to reconcile.")
        return
    _print_blockers(report, stream=sys.stdout)
    if report.drifted_features:
        print(f"  drifted features:     {', '.join(report.drifted_features)}")
    if report.removed_files:
        print(f"  removed files:        {', '.join(report.removed_files)}")
    print("  Run the council reconcile procedure (`/dummyindex --recouncil`).")


def _print_blockers(report: "ReconcileReport", *, stream: TextIO) -> None:
    """Print the two stamp-blocking categories (unassigned + awaiting)."""
    if report.unassigned_new_files:
        print(
            f"  unassigned new files: {', '.join(report.unassigned_new_files)}",
            file=stream,
        )
    if report.awaiting_enrichment:
        print(
            f"  awaiting enrichment:  {', '.join(report.awaiting_enrichment)}",
            file=stream,
        )
