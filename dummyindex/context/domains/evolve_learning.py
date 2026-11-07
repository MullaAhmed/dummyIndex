"""One bounded, idempotent post-task reflection through the existing evolve gate."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from pathlib import Path

from .atomic_io import write_text_atomic
from .evidence import digest
from .evolve import CANDIDATES_NAME, HARVEST_NAME, record_event, validate_candidate
from .evolve_gate import EvolveError, check_receipt, run_gate, safe_file
from .evolve_promotion import project_lock, promote_files
from .lesson import lesson_to_delta, validate_lesson
from .lesson.enums import LearningStatus
from .living_rules import durable_evidence, plan_rule

_BASE = ".context/gc/learning"


def _path(context_dir: Path, event_id: str) -> Path:
    return safe_file(
        context_dir.parent, f"{_BASE}/{digest(event_id)}.json", exists=False
    )


def learning_status(event: Mapping) -> str:
    """Closed alphabet: applied|evaluated|blocked|no_entry|pending|ignored|failed."""
    S = LearningStatus
    if event.get("status") == S.FAILED:
        return S.FAILED.value
    state = event.get("state")
    if state == "evaluated":
        blocked = event.get("verdict") == "blocked"
        return (S.BLOCKED if blocked else S.EVALUATED).value
    if state in {S.APPLIED, S.NO_ENTRY, S.IGNORED}:
        return S(state).value
    return S.PENDING.value


def read_event(context_dir: Path, event_id: str) -> dict | None:
    """The persisted learning event, or None when none was ever created."""
    path = _path(context_dir, event_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def mark_failed(context_dir: Path, event_id: str, error: str) -> dict | None:
    """Persist ``failed`` on an existing event; its state stays so a retry resumes."""
    with project_lock(context_dir.parent):
        event = read_event(context_dir, event_id)
        if event is None:
            return None
        event.update(status=LearningStatus.FAILED.value, error=error)
        write_text_atomic(
            _path(context_dir, event_id),
            json.dumps(event, sort_keys=True, indent=2) + "\n",
        )
        return event


def _write(path: Path, data: dict) -> None:
    write_text_atomic(path, json.dumps(data, sort_keys=True, indent=2) + "\n")


def _write_event(path: Path, data: dict) -> None:
    """Persist a learning event file only: refresh ``status``, clear stale ``error``."""
    data.pop("error", None)
    data["status"] = learning_status({**data, "status": None})
    write_text_atomic(path, json.dumps(data, sort_keys=True, indent=2) + "\n")


def enqueue_learning(
    context_dir: Path,
    *,
    event_id: str,
    origin: str,
    evidence: list[str],
    cue: str = "",
    lesson: str = "",
    target: str = "",
    expected_sha256: str = "",
    replacement: str = "",
    verified: bool = False,
) -> dict:
    """Queue one reflection; accepted evidence never authorizes ungated adoption."""
    if origin in {"learning", "evolve", "experiment"}:
        return {
            "state": "ignored",
            "reason": "learning cannot recursively trigger itself",
            "status": "ignored",
        }
    if origin not in {"closeout", "runtime", "human"} or not event_id:
        raise EvolveError(
            "learning requires a stable event ID and closeout/runtime/human origin"
        )
    if not evidence:
        return {
            "state": "ignored",
            "status": "ignored",
            "reason": "no accepted evidence",
        }
    if max(map(len, (cue, lesson, replacement)), default=0) > 4000:
        raise EvolveError("reflection fields are limited to 4000 characters")
    snapshots = durable_evidence(context_dir, tuple(evidence))
    payload = {
        "event_id": event_id,
        "origin": origin,
        "evidence": snapshots,
        "cue": cue,
        "lesson": lesson,
        "target": target,
        "expected_sha256": expected_sha256,
        "replacement": replacement,
        "verified": verified,
    }
    identity = digest(payload)
    with project_lock(context_dir.parent):
        path = _path(context_dir, event_id)
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if previous.get("identity") != identity:
                raise EvolveError(
                    "learning event ID was reused for different evidence or content"
                )
            return previous
        result = {
            "schema_version": 1,
            "identity": identity,
            "state": "pending",
            "budget": {"candidates": 1, "target_files": 1, "reflection_rounds": 1},
            **payload,
        }
        _write_event(path, result)
    return result


def pending_learning(context_dir: Path) -> list[dict]:
    """Oldest deterministic pending events; callers dispatch at most one per task."""
    rows = []
    directory = safe_file(context_dir.parent, f"{_BASE}/.check", exists=False).parent
    for path in sorted(directory.glob("*.json")):
        safe_file(context_dir.parent, path.relative_to(context_dir.parent).as_posix())
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("state") == "pending":
            rows.append(value)
    return rows


def _verify_evidence(context_dir: Path, event: dict) -> None:
    expected = event.get("evidence")
    if (
        not isinstance(expected, dict)
        or not expected
        or durable_evidence(context_dir, tuple(expected)) != expected
    ):
        raise EvolveError("accepted learning evidence changed; review a new event")


def _target_text(context_dir: Path, target: str) -> str:
    return safe_file(context_dir.parent, target).read_text(encoding="utf-8")


def prepare_learning(context_dir: Path, event_id: str, reflection: dict | None) -> dict:
    """Consume one host reflection into a run, or record an explicit NO_ENTRY.

    The caller is the active host at task closeout, not a background paid daemon.
    apply/promote remain the normal exact-content test and recovery operations.
    """
    with project_lock(context_dir.parent):
        path = _path(context_dir, event_id)
        if not path.exists():
            raise EvolveError("unknown learning event")
        event = json.loads(path.read_text(encoding="utf-8"))
        if event.get("state") not in {"pending", "prepared"}:
            return event
        _verify_evidence(context_dir, event)
        if event["state"] == "prepared":
            return event
        if reflection is None:
            event.update(state="no_entry", reason="No supported narrow rule change")
            _write_event(path, event)
            return event
        if not isinstance(reflection, dict) or reflection.get("verified") is not True:
            raise EvolveError(
                "reflection needs a verified actual outcome or accepted human correction"
            )
        # Exactly one narrow authoritative rule, not another growing lessons doc.
        check = validate_lesson(reflection)
        required = {"target", "rule_id", "expected_sha256", "sources"}
        if check.lesson is None:
            required.add("body")
        if not required <= reflection.keys():
            raise EvolveError(
                "reflection needs target, rule_id, "
                + ("body, " if check.lesson is None else "")
                + "expected_sha256 and sources"
            )
        evidence = tuple(event["evidence"])
        supersedes = tuple(reflection.get("supersedes", []))
        if check.lesson is None:
            kwargs: Mapping = {
                "target": reflection["target"],
                "rule_id": reflection["rule_id"],
                "body": reflection["body"],
                "expected_sha256": reflection["expected_sha256"],
                "sources": tuple(reflection["sources"]),
                "evidence": evidence,
                "supersedes": supersedes,
            }
        else:
            kwargs = lesson_to_delta(
                check.lesson,
                reflection["rule_id"],
                target=reflection["target"],
                current_text=_target_text(context_dir, reflection["target"]),
                expected_sha256=reflection["expected_sha256"],
                sources=tuple(reflection["sources"]),
                evidence=evidence,
                supersedes=supersedes,
            ).plan_kwargs
        planned = plan_rule(context_dir, **kwargs)
        errors = validate_candidate(planned["candidate"], context_dir)
        if errors:
            raise EvolveError("; ".join(errors))
        name = "learning-" + digest(event_id)[:20]
        run = safe_file(
            context_dir.parent, f".context/gc/evolve/{name}/.check", exists=False
        ).parent
        if run.exists():
            # An interrupted queue write may have left a complete deterministic run.
            existing = (run / CANDIDATES_NAME).read_text(encoding="utf-8")
            expected = json.dumps(planned["candidate"], sort_keys=True) + "\n"
            if existing != expected:
                raise EvolveError("learning run already contains a different candidate")
        else:
            run.mkdir(parents=True)
            _write(
                run / HARVEST_NAME,
                {
                    "since": None,
                    "items": [
                        {
                            "kind": "accepted_learning",
                            "source": event_id,
                            "citation": c,
                            "summary": event["cue"],
                        }
                        for c in event["evidence"]
                    ],
                },
            )
            write_text_atomic(
                run / CANDIDATES_NAME,
                json.dumps(planned["candidate"], sort_keys=True) + "\n",
            )
        staged = safe_file(run, "staged/0/" + reflection["target"], exists=False)
        write_text_atomic(staged, planned["content"])
        event.update(
            state="prepared", run=name, candidate=0, rule_id=reflection["rule_id"]
        )
        if check.legacy_shape:
            event["legacy_shape"] = True
            warnings.warn(
                "learning reflection uses the pre-change shape (no cue/lesson/"
                "evidence/confidence); accepted as legacy_shape",
                stacklevel=2,
            )
        _write_event(path, event)
        return event


def finish_learning(
    context_dir: Path,
    event_id: str,
    reflection: dict | None,
    *,
    tests: tuple[str, ...] = (),
) -> dict:
    """One automatic closeout pass: qualify exact bytes and apply if checks pass.

    Missing checks remain evaluated/blocked. A failed candidate is never adopted.
    Recoverable promotion owns writes and version/ownership maintenance.
    """
    prepared = prepare_learning(context_dir, event_id, reflection)
    if prepared["state"] != "prepared":
        return prepared
    root = context_dir.parent
    run = safe_file(
        root, f".context/gc/evolve/{prepared['run']}/.check", exists=False
    ).parent
    candidate = json.loads((run / CANDIDATES_NAME).read_text(encoding="utf-8"))
    targets = (candidate["target_file"],)
    with project_lock(root):
        event = json.loads(_path(context_dir, event_id).read_text(encoding="utf-8"))
        if event["state"] != "prepared":
            return event
        _verify_evidence(context_dir, event)
        errors = validate_candidate(candidate, context_dir)
        if errors:
            raise EvolveError("; ".join(errors))
        if (
            durable_evidence(context_dir, tuple(candidate["evidence"]))
            != event["evidence"]
        ):
            raise EvolveError(
                "candidate evidence differs from the accepted learning event"
            )
        result = run_gate(
            targets,
            run,
            context_dir,
            root,
            candidate_payload=candidate,
            test_paths=tests,
        )
        gate = {"candidate": 0, **result.to_dict()}
        _write(run / "gate-0.json", gate)
        event.update(
            state="evaluated",
            verdict=result.verdict,
            qualification="project tests; model improvement unmeasured",
        )
        record_event(
            context_dir,
            {
                "kind": "gate",
                "run": prepared["run"],
                "candidate": 0,
                "target": list(targets),
                "evidence": list(prepared["evidence"]),
                "gate": gate,
            },
        )
        if result.verdict == "pass":
            _verify_evidence(context_dir, event)
            check_receipt(gate, targets, run, 0, root, candidate)
            applied = promote_files(targets, run, 0, root, gate["receipt"])
            event.update(state="applied", applied=list(applied))
            record_event(
                context_dir,
                {
                    "kind": "promote",
                    "run": prepared["run"],
                    "candidate": 0,
                    "target": list(applied),
                    "prediction": candidate["prediction"],
                    "evidence": list(prepared["evidence"]),
                    "outcome": {
                        "qualification": "project_tests",
                        "automatic_learning": event_id,
                    },
                },
            )
        _write_event(_path(context_dir, event_id), event)
        return event


def run_learning(
    context_dir: Path,
    *,
    event_id: str,
    evidence: list[str],
    cue: str = "",
    reflection: dict | None = None,
    tests: tuple[str, ...] = (),
    origin: str = "closeout",
) -> dict:
    """Default closeout learner: queue the event, then finish it if a reflection came."""
    queued = enqueue_learning(
        context_dir, event_id=event_id, origin=origin, evidence=evidence, cue=cue
    )
    if reflection and queued.get("state") != "ignored":
        return finish_learning(context_dir, event_id, reflection, tests=tests)
    return queued
