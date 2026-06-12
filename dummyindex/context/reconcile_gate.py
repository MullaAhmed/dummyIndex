"""Stop-hook reconcile gate: block session exit once when a `.context/` is stale.

Covers the session root *and* every git submodule beneath it that carries its
own `.context/` index — a session run from a mono-repo root would otherwise
never see a stale submodule index, since that index lives below the
`$CLAUDE_PROJECT_DIR` the hook is handed.

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
from collections.abc import Sequence
from pathlib import Path

from dummyindex.context.drift import DriftReport, compute_drift
from dummyindex.context.domains.memory.nudge import is_significant
from dummyindex.context.domains.memory.transcript import read_session_signal
from dummyindex.pipeline.io import submodule_paths


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


def discover_context_roots(root: Path) -> tuple[Path, ...]:
    """Every ``.context/`` index to gate for a session rooted at ``root``.

    The session's own ``root`` always comes first (preserving single-repo
    behaviour), followed by each git submodule under ``root`` that carries
    its own ``.context/`` index. A session run from a mono-repo root would
    otherwise never see a stale submodule index — that index lives below the
    ``$CLAUDE_PROJECT_DIR`` the hook is handed.
    """
    root = root.resolve()
    roots = [root]
    for sub in submodule_paths(root):
        try:
            sub.relative_to(root)   # skip a `path = ../x` that escapes the root
        except ValueError:
            continue
        if sub != root and sub not in roots and (sub / ".context").is_dir():
            roots.append(sub)
    return tuple(roots)


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


def _root_label(ctx_root: Path, base: Path) -> str:
    """``"(root)"`` for the session root, else the submodule path relative
    to it (falling back to the absolute path if it isn't under ``base``)."""
    try:
        rel = ctx_root.resolve().relative_to(base.resolve())
    except ValueError:
        return str(ctx_root)
    return "(session root)" if str(rel) == "." else str(rel)


def _render_section(ctx_root: Path, report: DriftReport, base: Path) -> str:
    """One per-root clause of a multi-index block: what drifted there and the
    ``reconcile-stamp`` command scoped to that root."""
    is_base = ctx_root.resolve() == base.resolve()
    label = _root_label(ctx_root, base)
    arg = f'"{label}"' if " " in label else label   # keep the command copy-pasteable
    stamp = (
        "dummyindex context reconcile-stamp"
        if is_base
        else f"dummyindex context reconcile-stamp --root {arg}"
    )
    bits = [f"In {label}:"]
    features = sorted(report.by_feature().keys())
    if features:
        bits.append("drifted features " + ", ".join(features) + ";")
    if report.unassigned_new_files:
        bits.append("new unplaced files " + ", ".join(report.unassigned_new_files) + ";")
    if report.awaiting_enrichment:
        bits.append("awaiting enrichment " + ", ".join(report.awaiting_enrichment) + ";")
    bits.append(f"reconcile there, then `{stamp}`.")
    return " ".join(bits)


def render_multi_block(
    stale: Sequence[tuple[Path, DriftReport]], *, base: Path
) -> str:
    """Build a Stop ``decision: block`` covering several stale ``.context/``
    indexes (the session root and/or its submodules). Each gets its own
    scoped section so the agent knows where to reconcile and stamp."""
    parts = [
        "dummyindex reconcile gate: one or more `.context/` indexes are stale "
        "after a substantial session. Before this session ends, reconcile each "
        'so every index stays a reliable answer to "how does this code work?" '
        "(council/65-reconcile.md): for each drifted feature, re-run its council "
        "enrichment (`/dummyindex --recouncil <feature>`), place any new files, "
        "then run the scoped `reconcile-stamp` shown. Do NOT skip silently — this "
        "is the per-session reconcile gate.",
    ]
    parts.extend(_render_section(ctx_root, report, base) for ctx_root, report in stale)
    parts.append(
        'To disable for a repo: set "auto_council": false in its '
        ".context/config.json."
    )
    return json.dumps({"decision": "block", "reason": " ".join(parts)})


def decide_block(
    *,
    root: Path,
    main_transcript: Path | None,
    stop_hook_active: bool,
) -> str | None:
    """Return the Stop block JSON to print, or ``None`` to allow the stop.

    Cheap gates first. Blocks at most once per stop (``stop_hook_active``),
    only when some index is stale AND the session did real work. Covers the
    session root *and* each submodule index beneath it, so a session run from
    a mono-repo root still sees a stale submodule's ``.context/``.
    """
    if stop_hook_active:            # block-once: never trap the session
        return None
    if not auto_council_enabled(root):   # master opt-out at the session root
        return None
    base = root.resolve()
    stale: list[tuple[Path, DriftReport]] = []
    for ctx_root in discover_context_roots(base):
        # Each submodule honours its own opt-out; the root was checked above.
        if ctx_root != base and not auto_council_enabled(ctx_root):
            continue
        report = compute_drift(ctx_root)
        if report.has_drift:
            stale.append((ctx_root, report))
    if not stale:                   # nothing stale → allow stop
        return None
    if main_transcript is None or not main_transcript.exists():
        return None                 # no proof of substantive work
    signal = read_session_signal(main_transcript)
    if not is_significant(signal.output_tokens, signal.subagent_file_count):
        return None                 # trivial session → don't trap
    # Single stale index at the session root → keep the original message
    # byte-for-byte (no behaviour change for the common single-repo case).
    if len(stale) == 1 and stale[0][0] == base:
        return render_block(stale[0][1])
    return render_multi_block(stale, base=base)
