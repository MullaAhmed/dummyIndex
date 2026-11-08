"""`dummyindex context plan-update`: drift report for Claude Code's SessionStart hook.

Prints markdown naming features whose sources changed since their docs were touched (empty
when nothing is stale); the hook appends it to the session prompt. Drift still exits 0: it
is a signal, not an error. ``--json`` prints ``edited`` (source paths), ``anchored``
(``unassigned_new_files``, ``awaiting_enrichment``, ``drifted_features``), ``suppressed``
(doc-basis-matched files held back) and ``acked`` (rows dropped by valid ``drift-ack``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.drift import compute_badge, compute_drift, render_drift_summary

from .common import parse_path_and_root, resolve_context_root

# Gitignored badge cache under ``.context/cache/`` (e.g. ``[ctx ✓]``). statusline
# reads it on the per-prompt hot path instead of re-scanning drift; both modules
# resolve it through :func:`badge_cache_path`.
BADGE_CACHE_NAME = "freshness-badge"


def badge_cache_path(context_dir: Path) -> Path:
    """Path to the freshness-badge cache file under ``.context/cache/``."""
    return context_dir / "cache" / BADGE_CACHE_NAME


def _write_badge(context_dir: Path, report) -> None:
    """Best-effort: cache ``compute_badge(report)`` under ``.context/cache/``.

    The caller swallows every error, so a bad cache must never fail ``plan-update``
    or perturb stdout. The write is atomic (tmp + rename) so a concurrent
    statusline reader never sees a half-written badge.
    """
    cache_path = badge_cache_path(context_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(cache_path, compute_badge(report))


def run(args: list[str]) -> int:
    scope, explicit_root, rest = parse_path_and_root(args)
    want_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if rest:
        print(f"error: unknown argument(s) for `plan-update`: {rest}", file=sys.stderr)
        return 2

    project_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"
    if not context_dir.is_dir():
        # Not a .context project — silently no-op so the SessionStart
        # hook doesn't spam unrelated repos.
        return 0

    report = compute_drift(project_root)

    # Best-effort badge cache, isolated from the report: any failure is swallowed.
    try:
        _write_badge(context_dir, report)
    except Exception:
        pass

    if want_json:
        print(json.dumps(_json_envelope(report), indent=2))
        return 0

    summary = render_drift_summary(report)
    if summary:
        print(summary)
    return 0


def _json_envelope(report) -> dict[str, object]:
    """The stable ``--json`` payload — exactly the documented keys."""
    return {
        "edited": sorted({r.rel_path for r in report.rows}),
        "anchored": {
            "unassigned_new_files": list(report.unassigned_new_files),
            "awaiting_enrichment": list(report.awaiting_enrichment),
            "drifted_features": list(report.drifted_features),
        },
        "suppressed": report.suppressed_count,
        "acked": report.acked_count,
    }
