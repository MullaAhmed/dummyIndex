"""Stop-hook reconcile gate: block session exit once when `.context/` is stale.

Deterministic decision logic. The hook NEVER writes or stamps `.context/` —
it computes drift and, when a substantive session leaves the index stale,
emits a Stop ``decision: block`` whose ``reason`` directs the live agent to
run the council/reconcile and ``reconcile-stamp``. Mirrors ``memory/nudge.py``:
the CLI wrapper reads stdin and prints; this module only decides *whether* to
block and renders the directive.

Block-once is keyed on the Stop hook's ``stop_hook_active`` flag (true on the
re-entrant stop), so the gate is a strong prompt, never a trap. Honours the
commit-anchor invariant: only the agent advances the anchor (via
``reconcile-stamp`` / ``mark-enriched``) — the hook stamps nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dummyindex.context.drift import DriftReport, compute_drift
from dummyindex.context.domains.memory.nudge import is_significant
from dummyindex.context.domains.memory.transcript import read_session_signal


def auto_council_enabled(root: Path) -> bool:
    """Opt-out check: ``False`` only when ``.context/config.json`` sets
    ``"auto_council": false``. Absent file / key / malformed JSON → enabled
    (opt-out, not opt-in)."""
    cfg = root / ".context" / "config.json"
    if not cfg.is_file():
        return True
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return True
    if not isinstance(data, dict):
        return True
    return data.get("auto_council") is not False


def render_block(report: DriftReport) -> str:
    """Build the Stop ``decision: block`` JSON. ``reason`` is the agent-facing,
    scoped reconcile directive. The hook stamps nothing — the agent runs the
    council and ``reconcile-stamp``."""
    features = sorted(report.by_feature().keys())
    parts = [
        "dummyindex reconcile gate: `.context/` is stale after a substantial "
        "session. Before this session ends, reconcile the drifted parts so the "
        'index stays a reliable answer to "how does this code work?". Run the '
        "reconcile procedure (council/65-reconcile.md): for each drifted feature "
        "below, re-run its council enrichment (`/dummyindex --recouncil "
        "<feature>`); place any new files; then `dummyindex context "
        "reconcile-stamp`. Do NOT skip silently — this is the per-session "
        "reconcile gate.",
    ]
    if features:
        parts.append("Drifted features: " + ", ".join(features) + ".")
    if report.unassigned_new_files:
        parts.append(
            "New unplaced files: " + ", ".join(report.unassigned_new_files) + "."
        )
    if report.awaiting_enrichment:
        parts.append(
            "Awaiting enrichment: " + ", ".join(report.awaiting_enrichment) + "."
        )
    parts.append(
        'To disable for this repo: set "auto_council": false in '
        ".context/config.json."
    )
    return json.dumps({"decision": "block", "reason": " ".join(parts)})


def decide_block(
    *,
    root: Path,
    main_transcript: Optional[Path],
    stop_hook_active: bool,
) -> Optional[str]:
    """Return the Stop block JSON to print, or ``None`` to allow the stop.

    Cheap gates first. Blocks at most once per stop (``stop_hook_active``),
    only when the index is stale AND the session did real work.
    """
    if stop_hook_active:            # block-once: never trap the session
        return None
    if not auto_council_enabled(root):   # per-repo opt-out
        return None
    report = compute_drift(root)
    if not report.has_drift:        # nothing stale → allow stop
        return None
    if main_transcript is None or not main_transcript.exists():
        return None                 # no proof of substantive work
    signal = read_session_signal(main_transcript)
    if not is_significant(signal.output_tokens, signal.subagent_file_count):
        return None                 # trivial session → don't trap
    return render_block(report)
