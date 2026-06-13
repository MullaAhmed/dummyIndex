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
from typing import TYPE_CHECKING, Optional, TextIO

from .common import parse_path_and_root, resolve_context_root

if TYPE_CHECKING:
    from dummyindex.context.build.reconcile import ReconcileReport, StampResult


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
    to_commit, rest = _pull_to_flag(rest)
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

    result = stamp_reconciled(
        context_dir, out_root, force=force, to_commit=to_commit
    )

    if result.invalid_to:
        print(
            f"error: --to {to_commit!r} is not a commit in this repo; nothing "
            "stamped. Pass a sha that exists here (e.g. the last genuinely "
            "reconciled commit).",
            file=sys.stderr,
        )
        return 2

    if result.refused:
        return _render_stamp_refusal(result)

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
    if result.bootstrapped:
        print(
            "  NOTE: started commit-anchored tracking at this commit. Staleness "
            "predating this point will NOT appear in commit-anchored signals — "
            "review the SessionStart drift report for any pre-existing stale "
            "features."
        )
    if force and (
        result.report.unassigned_new_files or result.report.awaiting_enrichment
    ):
        print(
            "  WARNING: --force advanced the anchor past un-reconciled work, "
            "but did NOT resolve it. Committed files now sit BEHIND the new "
            "anchor and will not re-report; only UNTRACKED files and "
            "`.pending-enrichment` markers persist and WILL re-report next "
            "reconcile until you place/enrich them (or add a matching glob to "
            "`reconcile_exclude` in .context/config.json to stop tracking "
            "repo-specific noise):",
        )
        _print_blockers(result.report, stream=sys.stdout)
    if result.dirty_source:
        print(
            "  WARNING: uncommitted source changes remain outside .context/. "
            "Since the anchor is now HEAD, that source will re-surface as "
            "drift next reconcile — commit it to settle.",
        )
    return 0


def _pull_to_flag(rest: list[str]) -> tuple[Optional[str], list[str]]:
    """Pull a ``--to <sha>`` / ``--to=<sha>`` re-baseline target out of ``rest``."""
    out: list[str] = []
    to_commit: Optional[str] = None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--to" and i + 1 < len(rest):
            to_commit = rest[i + 1]
            i += 2
        elif a.startswith("--to="):
            to_commit = a.split("=", 1)[1]
            i += 1
        else:
            out.append(a)
            i += 1
    return to_commit, out


def _render_stamp_refusal(result: "StampResult") -> int:
    """Print the stamp-refusal guidance to stderr and return exit 1.

    Names the resolving verb per blocker category (so an agent that's stuck
    isn't left guessing), and treats an orphaned anchor as its own remedy
    (re-baseline with ``--to``), not a generic "place/enrich" instruction.
    """
    if result.report.anchor_broken:
        anchor = result.report.indexed_commit or "?"
        print(
            "context reconcile-stamp: REFUSED — the recorded anchor "
            f"{anchor[:12]} is unknown to this repo (history was rewritten by a "
            "rebase/squash, or it was never fetched). Advancing blindly to HEAD "
            "would paper over the rewrite. Re-baseline with `dummyindex context "
            "reconcile-stamp --to <commit>` at the last genuinely-reconciled "
            "commit, or pass --force to anchor at HEAD anyway.",
            file=sys.stderr,
        )
        return 1

    print(
        "context reconcile-stamp: REFUSED — un-reconciled work remains "
        "(advancing the anchor would silently forget it):",
        file=sys.stderr,
    )
    _print_blockers(result.report, stream=sys.stderr)
    if result.report.unassigned_new_files:
        print(
            "  → place unassigned files: `dummyindex context assign-files` "
            "(to an existing feature) or `scaffold-feature` (for a new one).",
            file=sys.stderr,
        )
    if result.report.awaiting_enrichment:
        print(
            "  → finish awaiting features: enrich each, then `dummyindex "
            "context mark-enriched --feature <id>`.",
            file=sys.stderr,
        )
    print(
        "  Then re-run reconcile-stamp, or re-run with --force to anchor anyway.",
        file=sys.stderr,
    )
    return 1


def _report_to_dict(report: "ReconcileReport") -> dict[str, object]:
    return {
        "indexed_commit": report.indexed_commit,
        "anchor_status": report.anchor_status.value,
        "anchor_broken": report.anchor_broken,
        "drifted_features": list(report.drifted_features),
        "removed_files": list(report.removed_files),
        "unassigned_new_files": list(report.unassigned_new_files),
        "awaiting_enrichment": list(report.awaiting_enrichment),
        "has_drift": report.has_drift,
    }


def _print_report(report: "ReconcileReport") -> None:
    from dummyindex.context.build.reconcile import AnchorStatus

    if report.indexed_commit is None:
        # Bootstrap path: never the destructive "fresh ingest" advice (that
        # re-clusters and wipes the curated taxonomy). Stamping starts tracking
        # non-destructively. No "in sync" — we can't assess a state with no anchor.
        print(
            "context reconcile: no anchor commit recorded (non-git repo, or an "
            "index built before commit-anchoring). Commit-anchored signals "
            "unavailable. Run `dummyindex context reconcile-stamp` to start "
            "commit-anchored tracking (non-destructive; never re-clusters)."
        )
        return

    print(f"context reconcile: anchor {report.indexed_commit[:12]}")

    if report.anchor_broken:
        # Orphaned anchor: do NOT print "in sync" — drift is not computable.
        print(
            f"  WARNING: anchor {report.indexed_commit[:12]} is unknown to this "
            "repo — history was rewritten (rebase/squash) or never fetched; "
            "cannot compute drift. Re-anchor with `dummyindex context "
            "reconcile-stamp --to <commit>` at the last genuinely-reconciled "
            "commit, or `reconcile-stamp` after reconciling against HEAD."
        )
        return

    if report.anchor_status == AnchorStatus.NOT_ANCESTOR:
        print(
            "  CAUTION: anchor is not an ancestor of HEAD — the delta may "
            "include other branches' work."
        )

    if not report.has_drift:
        print("  in sync — nothing to reconcile.")
        return
    _print_blockers(report, stream=sys.stdout)
    if report.drifted_features:
        print(f"  drifted features:     {', '.join(report.drifted_features)}")
    if report.removed_files:
        print(f"  removed files:        {', '.join(report.removed_files)}")
    print(
        "  Run the council reconcile procedure "
        "(`/dummyindex --recouncil <feature-id>` per drifted feature; see "
        "`council/65-reconcile.md`)."
    )


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
