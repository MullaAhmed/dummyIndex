"""Stop-hook reconcile gate: block session exit once when a `.context/` is stale.

Covers the session root and each submodule with its own `.context/`. A stale index
after a substantive session yields a Stop ``decision: block`` telling the agent to
reconcile and ``reconcile-stamp``. Invariant: it never stamps (only the agent moves
the anchor) and writes only its gitignored block-once memo; ``stop_hook_active`` +
that memo keep it a prompt, never a trap. The CLI wrapper does stdin and printing.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from dummyindex.context.build.reconcile import (
    compute_reconcile_report,
    is_non_source_path,
)
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.memory.nudge import is_significant
from dummyindex.context.domains.memory.transcript import read_session_signal
from dummyindex.context.drift import DriftReport, compute_drift
from dummyindex.context.reconcile_scope import (
    partition_session_drift,
    unrelated_summary,
)
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

    ``root`` first, then each git submodule under it with its own ``.context/``:
    a session at a mono-repo root would otherwise never see a stale submodule
    index below the ``$CLAUDE_PROJECT_DIR`` the hook is handed.
    """
    root = root.resolve()
    roots = [root]
    for sub in submodule_paths(root):
        try:
            sub.relative_to(root)  # skip a `path = ../x` that escapes the root
        except ValueError:
            continue
        if sub != root and sub not in roots and (sub / ".context").is_dir():
            roots.append(sub)
    return tuple(roots)


def _merged_features(report: DriftReport) -> list[str]:
    """Sorted union of the mtime ``by_feature()`` keys and the commit-anchored
    ``drifted_features``, de-duplicated so a feature surfaced by both signals is
    named once in the reconcile directive."""
    return sorted(set(report.by_feature()) | set(report.drifted_features))


def render_block(report: DriftReport) -> str:
    """Build the Stop ``decision: block`` JSON; ``reason`` is the agent-facing,
    scoped reconcile directive.

    Each category's remedy is emitted only when it has entries, so the agent is
    never told to enrich undrifted features or place files that don't exist.
    Features come from :func:`_merged_features`."""
    features = _merged_features(report)
    parts = [
        "dummyindex reconcile gate: `.context/` is stale after a substantial "
        "session. Before this session ends, reconcile the drifted parts so the "
        'index stays a reliable answer to "how does this code work?". Run the '
        "installed `/dummyindex` skill's reconcile procedure, then `dummyindex "
        "context reconcile-stamp`, then commit the refreshed index as its own "
        "dedicated commit (`git add .context && git commit -m "
        '"docs(context): reconcile"`) so every update is tracked in git. '
        "If you already reconciled this session, just run `dummyindex context "
        "reconcile-stamp` and commit — don't redo the work. "
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
            "Awaiting enrichment: " + ", ".join(report.awaiting_enrichment) + "."
        )
    parts.append(
        'To disable for this repo: set "auto_council": false in .context/config.json.'
    )
    return json.dumps({"decision": "block", "reason": " ".join(parts)})


def _root_label(ctx_root: Path, base: Path) -> str:
    """``"(root)"`` for the session root, else the submodule path relative
    to it (falling back to the absolute path if it isn't under ``base``)."""
    try:
        rel = ctx_root.resolve().relative_to(base.resolve())
    except ValueError:
        return ctx_root.as_posix()
    return "(session root)" if str(rel) == "." else rel.as_posix()


def _render_section(ctx_root: Path, report: DriftReport, base: Path) -> str:
    """One per-root clause of a multi-index block: what drifted there and the
    ``reconcile-stamp`` command scoped to that root."""
    is_base = ctx_root.resolve() == base.resolve()
    label = _root_label(ctx_root, base)
    arg = f'"{label}"' if " " in label else label  # keep the command copy-pasteable
    stamp = (
        "dummyindex context reconcile-stamp"
        if is_base
        else f"dummyindex context reconcile-stamp --root {arg}"
    )
    bits = [f"In {label}:"]
    features = _merged_features(report)
    if features:
        bits.append("drifted features " + ", ".join(features) + ";")
    if report.unassigned_new_files:
        bits.append(
            "new unplaced files " + ", ".join(report.unassigned_new_files) + ";"
        )
    if report.awaiting_enrichment:
        bits.append(
            "awaiting enrichment " + ", ".join(report.awaiting_enrichment) + ";"
        )
    bits.append(f"reconcile there, then `{stamp}`.")
    return " ".join(bits)


def render_multi_block(stale: Sequence[tuple[Path, DriftReport]], *, base: Path) -> str:
    """Build a Stop ``decision: block`` covering several stale ``.context/``
    indexes (the session root and/or its submodules). Each gets its own
    scoped section so the agent knows where to reconcile and stamp."""
    parts = [
        "dummyindex reconcile gate: one or more `.context/` indexes are stale "
        "after a substantial session. Before this session ends, reconcile each "
        'so every index stays a reliable answer to "how does this code work?" '
        "with the installed `/dummyindex` skill: for each drifted feature, "
        "re-run its council "
        "enrichment (`/dummyindex --recouncil <feature>`), place any new files, "
        "then run the scoped `reconcile-stamp` shown, then commit that repo's "
        'refreshed `.context/` as its own dedicated commit ("docs(context): '
        'reconcile") so every update is tracked in git. If you already '
        "reconciled an index this session, just run its scoped `reconcile-stamp` "
        "and commit — don't redo the work. Do NOT skip silently — "
        "this is the per-session reconcile gate.",
    ]
    parts.extend(_render_section(ctx_root, report, base) for ctx_root, report in stale)
    parts.append(
        'To disable for a repo: set "auto_council": false in its .context/config.json.'
    )
    return json.dumps({"decision": "block", "reason": " ".join(parts)})


def render_advisory_block(
    stale: Sequence[tuple[Path, DriftReport]], *, base: Path
) -> str:
    """Soft Stop block for an unreadable transcript: the gate can't confirm the
    session edited source, so it asks to reconcile only if code changed."""
    parts = [
        "dummyindex reconcile gate (advisory): one or more `.context/` indexes "
        "look stale, but this session's transcript was unreadable so the gate "
        "could not confirm whether this session edited source. If this session "
        "changed code, run the installed `/dummyindex` skill's reconcile "
        "procedure, "
        "then `dummyindex context reconcile-stamp`, then commit the refreshed "
        "index. If you already reconciled, just run `dummyindex context "
        "reconcile-stamp` and commit — don't redo the work. If this session "
        "changed no code, you can let it stop.",
    ]
    parts.extend(_render_section(ctx_root, report, base) for ctx_root, report in stale)
    parts.append(
        'To disable for a repo: set "auto_council": false in its .context/config.json.'
    )
    return json.dumps({"decision": "block", "reason": " ".join(parts)})


def _gate_state_path(context_dir: Path) -> Path:
    """Per-session block-once memo (gitignored cache), like the memory nudge's."""
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

    An empty ``session_id`` never persists, so the gate then relies on the
    ``stop_hook_active`` flag alone."""
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
    orphaned). See :func:`_gate_relevant` for why mtime-only drift then doesn't
    block."""
    report = compute_reconcile_report(root / ".context", root)
    if report.indexed_commit is None or report.anchor_broken:
        return False
    return True


def _session_drifted_source(
    signal_edited: tuple[str, ...], base: Path, *, subagent_edit_count: int = 0
) -> bool:
    """True when the session plausibly caused source drift; planning-only,
    git-only or read-only sessions are never trapped (inherited drift surfaces at
    SessionStart). True on any subagent edit, since subagent Edit/Write never shows
    in the main ``edited_paths`` (counting edits, not subagent transcripts, spares
    read-only fan-outs), or on a main-thread edit outside the non-source paths."""
    if subagent_edit_count > 0:
        return True
    base = base.resolve()
    for raw in signal_edited:
        rel = _rel_under_base(raw, base)
        if rel is None:
            # An edit outside the project tree — not this repo's source.
            continue
        if not is_non_source_path(rel, project_root=base):
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

    Commit-anchored signals (unassigned / awaiting / drifted_features) always
    count. mtime rows count only without a live anchor: with one, the anchored
    view is authoritative and mtime is a SessionStart-only advisory; anchor-less
    repos have no other staleness signal."""
    if (
        report.unassigned_new_files
        or report.awaiting_enrichment
        or report.drifted_features
    ):
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

    Cheap gates first; blocks at most once per session (``stop_hook_active``, then
    the ``mark_blocked`` memo). Blocks only when an index is gate-relevantly stale
    (:func:`_gate_relevant`), the session did real work and edited source, and the
    drift is attributable to its edits; other drift goes in an advisory summary.
    """
    if stop_hook_active:  # block-once fast path: never trap the session
        return None
    if already_blocked(root, session_id):  # block-once across user turns
        return None
    if not auto_council_enabled(root):  # master opt-out at the session root
        return None
    base = root.resolve()
    stale: list[tuple[Path, DriftReport]] = []
    context_roots = discover_context_roots(base)
    for ctx_root in context_roots:
        # Each submodule honours its own opt-out; the root was checked above.
        if ctx_root != base and not auto_council_enabled(ctx_root):
            continue
        report = compute_drift(ctx_root)
        if _gate_relevant(report, ctx_root):
            stale.append((ctx_root, report))
    if not stale:  # nothing gate-relevant → allow stop
        return None
    if main_transcript is None or not main_transcript.exists():
        # No transcript to prove work. With a session id, a Claude session did run
        # against a gate-relevant index: emit an advisory, don't silently allow.
        # With none (headless / CI / e2e), never trap: no transcript is expected.
        if session_id:
            mark_blocked(root, session_id)
            return json.dumps(
                {
                    "systemMessage": "Session ownership is unavailable. "
                    + unrelated_summary(stale, base=base)
                }
            )
        return None  # no proof of substantive work
    signal = read_session_signal(main_transcript)
    if not is_significant(signal.output_tokens, signal.subagent_file_count):
        return None  # trivial session → don't trap
    if not _session_drifted_source(
        signal.edited_paths, base, subagent_edit_count=signal.subagent_edit_count
    ):
        return None  # planning-only / git-only → inherited drift
    stale, unrelated = partition_session_drift(
        stale, signal.edited_paths, base=base, context_roots=context_roots
    )
    unrelated.extend(
        (ctx_root, report)
        for ctx_root, report in stale
        if not _gate_relevant(report, ctx_root)
    )
    stale = [
        (ctx_root, report)
        for ctx_root, report in stale
        if _gate_relevant(report, ctx_root)
    ]
    if not stale:
        return (
            json.dumps({"systemMessage": unrelated_summary(unrelated, base=base)})
            if unrelated
            else None
        )
    mark_blocked(root, session_id)
    # A lone stale session root keeps the single-repo message shape.
    if len(stale) == 1 and stale[0][0] == base:
        output = render_block(stale[0][1])
    else:
        output = render_multi_block(stale, base=base)
    if unrelated:
        payload = json.loads(output)
        payload["reason"] += "\n\n" + unrelated_summary(unrelated, base=base)
        output = json.dumps(payload)
    return output
