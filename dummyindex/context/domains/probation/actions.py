"""Enter, promote and demote probation rules through the existing evolve gate."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..atomic_io import write_text_atomic
from ..evolve import CANDIDATES_NAME, record_event, validate_candidate
from ..evolve_gate import CommandRunner, EvolveError, check_receipt, run_gate, safe_file
from ..evolve_promotion import project_lock, promote_files
from ..living_rules import plan_rule, rules_in, sha256
from ..observe import corrections, exposures
from . import rules, store
from .constants import MAX_LIVE_PER_TARGET, MAX_LIVE_TOTAL
from .enums import LIVE, State
from .models import Item
from .rules import PROBATION_PREFIX
from .sync import eligible_ids, sync

CHAT_PREFIX = "chat:"
TERMINAL = frozenset({State.DEMOTED, State.EXPIRED, State.QUARANTINED})
REVIEW_LINE = "review and commit .context/conventions/ yourself"


def _dump(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _run_name(item_id: str, suffix: str = "") -> str:
    return f"probation-{item_id}{suffix}"


def _fresh_run(root: Path, name: str) -> Path:
    """Recreate the run dir; a promotion journal means a prior run committed, so refuse."""
    run = safe_file(root, f".context/gc/evolve/{name}/.check", exists=False).parent
    if (run / "backup" / "0" / "transaction.json").exists():
        raise EvolveError(f"{name} already has a promotion journal; roll back first")
    if run.exists():
        shutil.rmtree(run)
    return run


def _keep(context_dir: Path, item: Item, reason: str, now: datetime) -> dict:
    store.save_item(context_dir, item.note(reason, now))
    return {"id": item.id, "state": State.PROBATION.value, "reason": reason}


def _demoted(item_id: str, reason: str) -> dict:
    return {"id": item_id, "state": State.DEMOTED.value, "reason": reason}


def enter(
    context_dir: Path,
    *,
    event: dict,
    run: Path,
    candidate: dict,
    tests: tuple[str, ...],
    now: datetime | None = None,
) -> dict:
    """Record a gate-passed rule as a PROBATION item, or return why it was blocked."""
    now = now or datetime.now(timezone.utc)
    with store.locked(context_dir):
        side = json.loads((run / "probation.json").read_text(encoding="utf-8"))
        body, applies_when = side["body"], side["applies_when"]
        if rules.content_reasons(body) or rules.content_reasons(applies_when):
            return {"verdict": "blocked", "reason": rules.HIGH_IMPACT}
        probe = rules.compile_probe(side.get("probe"))
        target = candidate["target_file"]
        items = store.load_items(context_dir)
        live = [item for item in items if item.state in LIVE]
        if (
            sum(item.target == target for item in live) >= MAX_LIVE_PER_TARGET
            or len(live) >= MAX_LIVE_TOTAL
        ):
            return {"verdict": "blocked", "reason": rules.CAP_REASON}
        rule_id = event["rule_id"]
        history: tuple[dict[str, str], ...] = ()
        existing = store.load_item(context_dir, rule_id)
        if existing is not None:
            if existing.state not in TERMINAL:
                return {"verdict": "blocked", "reason": "probation id in use"}
            history = existing.history
        text = safe_file(run, f"staged/0/{target}").read_text(encoding="utf-8")
        meta = next((r for r in rules_in(text) if r["id"] == rule_id), None)
        if meta is None:
            raise EvolveError("staged rule is missing from the candidate")
        cid = event["event_id"].removeprefix(CHAT_PREFIX)
        origin = next(
            (rec["session"] for rec in corrections(context_dir) if rec["id"] == cid),
            None,
        )
        item = Item(
            id=rule_id,
            target=target,
            body=body,
            applies_when=applies_when,
            prediction=candidate["prediction"],
            probe=probe,
            sources=dict(meta["sources"]),
            tests=tuple(tests),
            evidence=tuple(event["evidence"]),
            origin_session=origin,
            learning_event=event["event_id"],
            created=now.isoformat(timespec="seconds"),
            state=State.PROPOSED,
            harm=(),
            history=history,
        ).with_state(State.PROBATION, "gate pass", now)
        store.save_item(context_dir, item)
        return {"probation": rule_id}


def promote(
    context_dir: Path,
    ids: list[str] | None = None,
    *,
    now: datetime | None = None,
    runner: CommandRunner | None = None,
) -> list[dict]:
    """Gate each eligible probation item and promote the ones that pass."""
    now = now or datetime.now(timezone.utc)
    wanted = None if ids is None else set(ids)
    results: list[dict] = []
    with store.locked(context_dir):
        # Sync first so drift and pending probes are settled before eligibility is computed.
        sync(context_dir, now=now, probes=True)
        items = {item.id: item for item in store.load_items(context_dir)}
        for item_id in eligible_ids(context_dir, items.values(), probes=True):
            if wanted is not None and item_id not in wanted:
                continue
            results.append(_promote_one(context_dir, items[item_id], now, runner))
    return results


def _promote_one(
    context_dir: Path, item: Item, now: datetime, runner: CommandRunner | None
) -> dict:
    reasons = rules.content_reasons(item.body)
    if reasons:
        reason = "content scan: " + ", ".join(reasons)
        store.save_item(context_dir, item.with_state(State.QUARANTINED, reason, now))
        return {"id": item.id, "state": State.QUARANTINED.value, "reason": reason}
    try:
        return _gate_and_promote(context_dir, item, now, runner)
    except (EvolveError, OSError) as exc:
        return _keep(context_dir, item, f"blocked: {exc}", now)


def _gate_and_promote(
    context_dir: Path, item: Item, now: datetime, runner: CommandRunner | None
) -> dict:
    root = context_dir.parent
    target = item.target
    targets = (target,)
    with project_lock(root):
        # Plan against the current bytes so owner edits since enter are kept.
        current = safe_file(root, target).read_bytes()
        planned = plan_rule(
            context_dir,
            target=target,
            rule_id=item.id,
            body=item.body,
            expected_sha256=sha256(current),
            sources=tuple(item.sources),
            evidence=item.evidence,
        )
        candidate = planned["candidate"]
        errors = validate_candidate(candidate, context_dir)
        if errors:
            raise EvolveError("; ".join(errors))
        name = _run_name(item.id)
        run = _fresh_run(root, name)
        write_text_atomic(
            run / CANDIDATES_NAME, json.dumps(candidate, sort_keys=True) + "\n"
        )
        write_text_atomic(
            safe_file(run, f"staged/0/{target}", exists=False), planned["content"]
        )
        result = run_gate(
            targets,
            run,
            context_dir,
            root,
            candidate_payload=candidate,
            test_paths=item.tests,
            runner=runner,
        )
        gate = {"candidate": 0, **result.to_dict()}
        write_text_atomic(run / "gate-0.json", _dump(gate))
        record_event(
            context_dir,
            {
                "kind": "gate",
                "run": name,
                "candidate": 0,
                "target": list(targets),
                "evidence": list(item.evidence),
                "gate": gate,
            },
        )
        if result.verdict != "pass":
            return _keep(
                context_dir, item, f"gate {result.verdict}: kept on probation", now
            )
        check_receipt(gate, targets, run, 0, root, candidate)
        applied = promote_files(targets, run, 0, root, gate["receipt"])
        store.save_item(context_dir, item.with_state(State.PROMOTED, "promoted", now))
        exposed = rules.exposed_sessions(
            item, exposures(context_dir, f"{PROBATION_PREFIX}{item.id}")
        )
        bound = rules.upper_bound(exposed)
        record_event(
            context_dir,
            {
                "kind": "promote",
                "run": name,
                "candidate": 0,
                "target": list(applied),
                "prediction": candidate["prediction"],
                "evidence": list(item.evidence),
                "outcome": {
                    "qualification": "no harm detected",
                    "exposed_sessions": exposed,
                    "upper_bound_95": bound,
                },
            },
        )
    return {
        "id": item.id,
        "state": State.PROMOTED.value,
        "reason": "no harm detected",
        "exposed_sessions": exposed,
        "upper_bound_95": bound,
    }


def format_promote(results: list[dict]) -> str:
    """Render promote results as plain lines; the review line always ends the output."""
    lines = []
    for row in results:
        if row["state"] == State.PROMOTED.value:
            lines.append(
                f"promoted {row['id']}: no harm detected in {row['exposed_sessions']} "
                "exposed sessions; observed-correction bound "
                f"(detector-limited, 95%): {row['upper_bound_95'] * 100:.1f}%"
            )
        else:
            lines.append(f"{row['id']}: {row['state']} ({row['reason']})")
    lines.append(REVIEW_LINE)
    return "\n".join(lines)


def _without_block(text: str, block: dict) -> str:
    """Undo plan_rule's append: one newline after the block and one before it."""
    head, tail = text[: block["start"]], text[block["end"] :]
    if tail.startswith("\n"):
        tail = tail[1:]
    if head.endswith("\n\n"):
        head = head[:-1]
    return head + tail


def demote(
    context_dir: Path,
    item_id: str,
    *,
    now: datetime | None = None,
    runner: CommandRunner | None = None,
) -> dict:
    """Remove a rule's managed block (or mark it demoted) and record the rollback."""
    now = now or datetime.now(timezone.utc)
    with store.locked(context_dir):
        item = store.load_item(context_dir, item_id)
        if item is None:
            raise EvolveError(f"unknown probation item: {item_id}")
        if item.state is State.DEMOTED:
            return _demoted(item_id, "already demoted")
        if item.state is not State.PROMOTED:
            store.save_item(
                context_dir, item.with_state(State.DEMOTED, "demoted by user", now)
            )
            return _demoted(item_id, "demoted by user")
        with project_lock(context_dir.parent):
            return _demote_promoted(context_dir, item, now, runner)


def _demote_promoted(
    context_dir: Path, item: Item, now: datetime, runner: CommandRunner | None
) -> dict:
    root = context_dir.parent
    target = item.target
    targets = (target,)
    # Bytes, not read_text: text mode would turn CRLF owner files into LF.
    text = safe_file(root, target).read_bytes().decode("utf-8")
    block = next((r for r in rules_in(text) if r["id"] == item.id), None)
    if block is None:
        gone = replace(item, demote_pending=False).with_state(
            State.DEMOTED, "block already gone", now
        )
        store.save_item(context_dir, gone)
        return _demoted(item.id, "block already gone")
    name = _run_name(item.id, "-demote")
    run = _fresh_run(root, name)
    candidate = {
        "target_file": target,
        "diagnosis": f"Remove managed rule {item.id} after reported harm",
        "evidence": list(item.evidence),
        "change_sketch": f"Remove block {item.id}",
        "prediction": f"Removing {item.id} leaves project tests green",
    }
    write_text_atomic(
        run / CANDIDATES_NAME, json.dumps(candidate, sort_keys=True) + "\n"
    )
    write_text_atomic(
        safe_file(run, f"staged/0/{target}", exists=False),
        _without_block(text, block),
    )
    result = run_gate(
        targets,
        run,
        context_dir,
        root,
        candidate_payload=candidate,
        test_paths=item.tests,
        runner=runner,
    )
    gate = {"candidate": 0, **result.to_dict()}
    write_text_atomic(run / "gate-0.json", _dump(gate))
    if result.verdict != "pass":
        store.save_item(
            context_dir, item.note(f"gate {result.verdict}: kept promoted", now)
        )
        return {
            "id": item.id,
            "state": State.PROMOTED.value,
            "reason": f"gate {result.verdict}: kept promoted",
        }
    check_receipt(gate, targets, run, 0, root, candidate)
    applied = promote_files(targets, run, 0, root, gate["receipt"])
    # Same run as the promote event so check_predictions closes that prediction.
    record_event(
        context_dir,
        {
            "kind": "rollback",
            "run": _run_name(item.id),
            "candidate": 0,
            "target": list(applied),
            "evidence": list(item.evidence),
            "outcome": {"demoted": item.id, "staged_run": name},
        },
    )
    done = replace(item, demote_pending=False).with_state(
        State.DEMOTED, "demoted by user", now
    )
    store.save_item(context_dir, done)
    return _demoted(item.id, "demoted by user")
