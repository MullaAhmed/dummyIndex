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
from datetime import datetime, timezone
from pathlib import Path

from dummyindex.context.build.reconcile import compute_reconcile_report
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.memory.nudge import is_significant
from dummyindex.context.domains.memory.transcript import read_session_signal
from dummyindex.context.drift import DriftReport, compute_drift
from dummyindex.pipeline.io import submodule_paths

# Paths under these prefixes are never "source" for gate-attribution purposes:
# editing only the index or the tool footprint is not a session that drifted
# code. Kept in sync with reconcile.py's tool-path set (.claude + .claude-design)
# so the gate and the reconcile delta agree on what "tool footprint" means —
# test_gate_non_source_covers_reconcile_tool_paths locks the two together.
_NON_SOURCE_PREFIXES: tuple[str, ...] = (".context", ".claude", ".claude-design")


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
    council and ``reconcile-stamp``.

    The per-category remedy is emitted *only when that category has entries*,
    so an unassigned-only block never instructs council enrichment of features
    that aren't drifted (and a drifted-only block never dangles a placement
    step for files that don't exist)."""
    features = sorted(report.by_feature().keys())
    parts = [
        "dummyindex reconcile gate: `.context/` is stale after a substantial "
        "session. Before this session ends, reconcile the drifted parts so the "
        'index stays a reliable answer to "how does this code work?". Run the '
        "reconcile procedure (council/65-reconcile.md), then `dummyindex "
        "context reconcile-stamp`, then commit the refreshed index as its own "
        'dedicated commit (`git add .context && git commit -m '
        '"docs(context): reconcile"`) so every update is tracked in git. '
        "Do NOT skip silently — this is the per-session reconcile gate.",
    ]
    if features:
        parts.append(
            "For each drifted feature, re-run its council enrichment "
            "(`/dummyindex --recouncil <feature>`). Drifted features: "
            + ", ".join(features)
            + "."
        )
    if report.unassigned_new_files:
        parts.append(
            "Place the new files (assign-files / scaffold-feature), then "
            "reconcile-stamp. New unplaced files: "
            + ", ".join(report.unassigned_new_files)
            + "."
        )
    if report.awaiting_enrichment:
        parts.append(
            "Enrich, then `dummyindex context mark-enriched --feature <id>`. "
            "Awaiting enrichment: "
            + ", ".join(report.awaiting_enrichment)
            + "."
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
        "then run the scoped `reconcile-stamp` shown, then commit that repo's "
        'refreshed `.context/` as its own dedicated commit ("docs(context): '
        'reconcile") so every update is tracked in git. Do NOT skip silently — '
        "this is the per-session reconcile gate.",
    ]
    parts.extend(_render_section(ctx_root, report, base) for ctx_root, report in stale)
    parts.append(
        'To disable for a repo: set "auto_council": false in its '
        ".context/config.json."
    )
    return json.dumps({"decision": "block", "reason": " ".join(parts)})


def _gate_state_path(context_dir: Path) -> Path:
    """Per-session gate memo (gitignored cache) — the block-once-per-session
    record the sibling nudge feature keeps for its own one-shot prompt."""
    return context_dir / "cache" / "reconcile-gate-state.json"


def _load_gate_state(context_dir: Path) -> dict:
    path = _gate_state_path(context_dir)
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return obj if isinstance(obj, dict) else {}


def already_blocked(root: Path, session_id: str) -> bool:
    """True when the gate already blocked once this session (memo present).

    An empty ``session_id`` never persists, so the gate then falls back to the
    ``stop_hook_active`` flag alone (the pre-memo behaviour)."""
    if not session_id:
        return False
    return session_id in _load_gate_state(root.resolve() / ".context")


def mark_blocked(root: Path, session_id: str) -> None:
    """Record that the gate blocked this session. No-op for an empty id."""
    if not session_id:
        return
    context_dir = root.resolve() / ".context"
    state = _load_gate_state(context_dir)
    state[session_id] = {"blocked_at": datetime.now(timezone.utc).isoformat()}
    if len(state) > 100:
        keep = sorted(
            state.items(),
            key=lambda kv: kv[1].get("blocked_at", ""),
            reverse=True,
        )[:100]
        state = dict(keep)
    write_text_atomic(_gate_state_path(context_dir), json.dumps(state, indent=2) + "\n")


def _has_live_anchor(root: Path) -> bool:
    """True when this repo carries a usable commit anchor (present and not
    orphaned). mtime drift alone is downgraded to silence when an anchor exists
    — the commit-anchored signals are authoritative and the SessionStart report
    already surfaces mtime nudges. Anchor-less repos keep mtime-blocking, since
    it's the only staleness signal they have."""
    report = compute_reconcile_report(root / ".context", root)
    if report.indexed_commit is None or report.anchor_broken:
        return False
    return True


def _session_drifted_source(
    signal_edited: tuple[str, ...], base: Path, *, subagent_file_count: int = 0
) -> bool:
    """True when the session plausibly caused source drift. A planning-only /
    git-only / tool-update session never gets trapped; inherited drift surfaces
    via the SessionStart report instead.

    Two ways a session counts as source-drifting:

    1. It dispatched file-working subagents (``subagent_file_count > 0``). A
       ``/dummyindex-build``-style run does its edits *inside* subagents, whose
       writes never appear in the main transcript's ``edited_paths`` — so the
       main-thread path-check alone would let exactly the highest-drift
       workflows escape. Subagent activity is the proxy for "real work landed".
    2. It edited at least one file on the main thread OUTSIDE ``.context/`` and
       ``.claude/`` (the index + tool wiring are not source)."""
    if subagent_file_count > 0:
        return True
    base = base.resolve()
    for raw in signal_edited:
        rel = _rel_under_base(raw, base)
        if rel is None:
            # An edit outside the project tree — not this repo's source.
            continue
        if not any(
            rel == prefix or rel.startswith(prefix + "/")
            for prefix in _NON_SOURCE_PREFIXES
        ):
            return True
    return False


def _rel_under_base(raw: str, base: Path) -> str | None:
    """Repo-relative POSIX path for ``raw`` if it's under ``base``, else None."""
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    try:
        return p.resolve().relative_to(base).as_posix()
    except (ValueError, OSError):
        return None


def _gate_relevant(report: DriftReport, ctx_root: Path) -> bool:
    """Whether ``report`` should trap the stop for ``ctx_root``.

    Commit-anchored signals (unassigned / awaiting) always count. mtime rows
    count only when the repo has no live anchor — with an anchor, the
    commit-anchored view is authoritative and mtime is a SessionStart-only
    advisory (the three-oracle reconciliation)."""
    if report.unassigned_new_files or report.awaiting_enrichment:
        return True
    if report.rows and not _has_live_anchor(ctx_root):
        return True
    return False


def decide_block(
    *,
    root: Path,
    main_transcript: Path | None,
    stop_hook_active: bool,
    session_id: str = "",
) -> str | None:
    """Return the Stop block JSON to print, or ``None`` to allow the stop.

    Cheap gates first. Blocks at most once per session — via the persisted
    per-session memo (``mark_blocked``) and, as a fast first check, the Stop
    hook's ``stop_hook_active`` flag. Blocks only when some index is stale in a
    *gate-relevant* way (commit-anchored signal, or mtime drift in an
    anchor-less repo) AND the session both did real work and plausibly edited
    source outside ``.context/`` / ``.claude/``. Covers the session root *and*
    each submodule index beneath it.
    """
    if stop_hook_active:            # block-once fast path: never trap the session
        return None
    if already_blocked(root, session_id):   # block-once across user turns
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
        if _gate_relevant(report, ctx_root):
            stale.append((ctx_root, report))
    if not stale:                   # nothing gate-relevant → allow stop
        return None
    if main_transcript is None or not main_transcript.exists():
        return None                 # no proof of substantive work
    signal = read_session_signal(main_transcript)
    if not is_significant(signal.output_tokens, signal.subagent_file_count):
        return None                 # trivial session → don't trap
    if not _session_drifted_source(
        signal.edited_paths, base, subagent_file_count=signal.subagent_file_count
    ):
        return None                 # planning-only / git-only → inherited drift
    mark_blocked(root, session_id)
    # Single stale index at the session root → keep the original message
    # shape (no behaviour change for the common single-repo case).
    if len(stale) == 1 and stale[0][0] == base:
        return render_block(stale[0][1])
    return render_multi_block(stale, base=base)
