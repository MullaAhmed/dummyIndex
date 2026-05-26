"""`dummyindex context plan-update` — drift report for Claude Code's SessionStart hook.

Prints a markdown summary of features whose source files have changed
since the matching `.context/features/<id>/` docs were last touched.
The SessionStart hook captures this stdout and Claude Code appends it
to the running session's system prompt, so the agent sees which feature
docs are stale and can update them in-session.

Output contract:

- Stdout: markdown body when drift exists; empty when nothing is stale.
- Exit code: always 0 — drift is a signal, not an error.
- No JSON envelope needed: Claude Code's SessionStart hook also accepts
  plain stdout as ``additionalContext`` automatically.
"""
from __future__ import annotations

import sys

from dummyindex.context.drift import compute_drift, render_drift_summary

from ._common import _parse_path_and_root, _resolve_context_root


def _cmd_plan_update(args: list[str]) -> int:
    scope, explicit_root, rest = _parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `plan-update`: {rest}", file=sys.stderr)
        return 2

    project_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"
    if not context_dir.is_dir():
        # Not a .context project — silently no-op so the SessionStart
        # hook doesn't spam unrelated repos.
        return 0

    report = compute_drift(project_root)
    summary = render_drift_summary(report)
    if summary:
        print(summary)
    return 0
