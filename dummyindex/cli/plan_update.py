"""`dummyindex context plan-update` — drift report for Claude Code's SessionStart hook.

Prints a markdown summary of features whose source files have changed
since the matching `.context/features/<id>/` docs were last touched.
The SessionStart hook captures this stdout and Claude Code appends it
to the running session's system prompt, so the agent sees which feature
docs are stale and can update them in-session.

Output contract:

- Stdout: markdown body when drift exists; empty when nothing is stale.
  ``--json`` swaps the body for a stable machine envelope (below) — exit
  code stays 0 and plain mode is byte-identical to before.
- Exit code: always 0 — drift is a signal, not an error.
- No JSON envelope needed by the hook itself: Claude Code's SessionStart
  hook also accepts plain stdout as ``additionalContext`` automatically;
  ``--json`` exists for scripts that must act per-row instead of prose.

The ``--json`` envelope (stable keys, spec §Contracts)::

    {"edited": [...], "anchored": {"unassigned_new_files": [...],
     "awaiting_enrichment": [...], "drifted_features": [...]},
     "suppressed": N, "acked": N}

where ``edited`` lists distinct source paths with renderable rows,
``suppressed`` counts doc-basis-matched files held back from the report,
and ``acked`` counts rows dropped by still-valid ``drift-ack`` entries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.drift import compute_badge, compute_drift, render_drift_summary

from .common import parse_path_and_root, resolve_context_root

# Gitignored scratch file under ``.context/cache/`` holding the pre-computed
# freshness badge (e.g. ``[ctx ✓]`` / ``[ctx: 2 edited · 1 anchored]``). The
# statusline command reads this directly off the per-prompt hot path instead
# of re-running the drift scan, so both modules resolve the path through
# :func:`badge_cache_path` rather than hard-coding the name twice.
BADGE_CACHE_NAME = "freshness-badge"


def badge_cache_path(context_dir: Path) -> Path:
    """Path to the freshness-badge cache file under ``.context/cache/``."""
    return context_dir / "cache" / BADGE_CACHE_NAME


def _write_badge(context_dir: Path, report) -> None:
    """Best-effort: cache ``compute_badge(report)`` under ``.context/cache/``.

    Wrapped by the caller in a single ``try/except`` that swallows every
    error — a missing or unwritable cache must never fail ``plan-update`` or
    perturb the drift report that prints to stdout (spec §5). The write is
    atomic (tmp + rename) so a concurrent statusline reader never sees a
    half-written badge.
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

    # Cache the statusline badge — best-effort and fully isolated from the
    # drift report below. Any failure here (unwritable cache dir, etc.) is
    # swallowed so it never fails the hook or touches stdout.
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
