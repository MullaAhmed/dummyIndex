"""One bounded native-host observe/author/execute/grade continuation, never a driver."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .atomic_io import write_text_atomic
from .evidence import digest, expose_case
from .evolve import MAX_CANDIDATES, validate_candidate
from .evolve_experiments import (
    MAX_RAW_BYTES,
    _captured_guidance_bytes,
    _comparison_reason,
    _finite,
    _guidance,
    _measurement,
    _utility,
    _write,
)
from .evolve_gate import EvolveError, safe_file
from .evolve_native_response import _charge, _preflight
from .evolve_native_snapshot import (
    _artifact,
    _controller,
    _hashes,
    _inputs,
    _materialize,
    _modes,
    _runtime,
    _tree,
)
from .evolve_promotion import project_lock


def _save(path, state):
    state["receipt_sha256"] = digest(
        {k: v for k, v in state.items() if k != "receipt_sha256"}
    )
    _write(path, state)


def _view(state):
    return {
        k: state[k]
        for k in (
            "state",
            "identity",
            "pending",
            "current",
            "best",
            "stop_reason",
            "actions",
            "deadline",
            "tokens",
            "cost_usd",
            "known_tokens",
            "known_cost_usd",
        )
    } | {"candidate_index": state["candidates"].get(state["current"], {}).get("index")}


def _initialize(context, run, spec):
    root = context.parent
    cases, guidance = spec.get("cases"), spec.get("guidance")
    if not all(isinstance(spec.get(k), str) and spec[k] for k in ("model", "rubric")):
        raise EvolveError("native replay requires pinned model and rubric identities")
    if (
        not isinstance(cases, list)
        or not 2 <= len(cases) <= 16
        or any(
            not isinstance(c, dict)
            or not isinstance(c.get("id"), str)
            or not c["id"]
            or not isinstance(c.get("path"), str)
            or c.get("split") not in {"train", "validation", "heldout"}
            for c in cases
        )
        or len({c["id"] for c in cases}) != len(cases)
        or len({c["path"] for c in cases}) != len(cases)
    ):
        raise EvolveError(
            "native replay needs 2–16 uniquely named/path-bound development and heldout cases"
        )
    dev = [c for c in cases if c["split"] != "heldout"]
    held = [c for c in cases if c["split"] == "heldout"]
    if not dev or not held:
        raise EvolveError("native replay requires development and heldout cases")
    if (
        not isinstance(guidance, list)
        or not 1 <= len(guidance) <= 5
        or any(
            not isinstance(g, dict) or not isinstance(g.get("path"), str)
            for g in guidance
        )
        or len({g["path"] for g in guidance}) != len(guidance)
    ):
        raise EvolveError("declare 1–5 distinct guidance paths before native replay")
    for key in ("seed", "repetition"):
        if (
            not isinstance(spec.get(key, 0), int)
            or isinstance(spec.get(key, 0), bool)
            or spec.get(key, 0) < 0
        ):
            raise EvolveError("seed/repetition must be nonnegative integers")
    if not isinstance(spec.get("budget", {}), dict):
        raise EvolveError("native budget must be an object")
    budget = {
        "actions": 3 + 2 * (4 * len(dev) + 2 * len(held)),
        "seconds": 1800,
        **spec.get("budget", {}),
    }
    if (
        set(budget) - {"actions", "seconds", "tokens", "cost_usd"}
        or any(not _finite(v) or v <= 0 for v in budget.values())
        or not 1 <= budget["actions"] <= 128
        or int(budget["actions"]) != budget["actions"]
        or budget["seconds"] > 1800
    ):
        raise EvolveError("invalid native action/deadline/resource budget")
    inputs = _inputs(root)
    for row in cases + guidance:
        safe_file(root, row["path"])
        if row["path"] not in inputs:
            raise EvolveError("case/guidance must be a captured project input")
    grading_paths = spec.get("grading_paths", [])
    if (
        not isinstance(grading_paths, list)
        or any(not isinstance(p, str) or p not in inputs for p in grading_paths)
        or set(grading_paths) & {g["path"] for g in guidance + cases}
    ):
        raise EvolveError(
            "grading_paths must name captured non-guidance evaluator files"
        )
    contract = {
        "specification": spec,
        "inputs": _hashes(inputs),
        "modes": _modes(root, inputs),
        "environment": _runtime(),
        "controller": _controller(),
    }
    identity = digest(contract)
    cache = f".context/cache/native/{identity[:16]}"
    _materialize(root, cache + "/baseline", inputs, contract["modes"])
    for case in cases:
        expose_case(
            context,
            case["id"],
            split=case["split"],
            derived_from=tuple(case.get("derived_from", [])),
            content_sha256=contract["inputs"][case["path"]],
        )
    state = {
        "schema_version": 1,
        "identity": identity,
        "contract": contract,
        "cache": cache,
        "budget": budget,
        "deadline": time.time() + budget["seconds"],
        "actions": 0,
        "state": "ready",
        "pending": None,
        "current": "incumbent",
        "best": "incumbent",
        "stop_reason": "",
        "tokens": 0,
        "cost_usd": 0,
        "known_tokens": 0,
        "known_cost_usd": 0,
        "responses": {},
        "actors": [],
        "candidates": {},
        "measurements": {},
        "feedback": [],
        "trial": None,
    }
    _begin_trial(state, "incumbent", "development")
    return state


def _begin_trial(state, label, phase):
    cases = state["contract"]["specification"]["cases"]
    selected = [c for c in cases if (c["split"] == "heldout") == (phase == "heldout")]
    state["trial"] = {
        "label": label,
        "phase": phase,
        "cases": selected,
        "rows": [],
        "execution": None,
    }
    state["next"] = "execute"


def _finish(state, reason):
    state.update(state="complete", pending=None, stop_reason=reason)


def _overlay(root, run, state, label):
    candidate = state["candidates"].get(label)
    if not candidate:
        return {}
    if (
        _hashes(
            {candidate["feedback"]: safe_file(run, candidate["feedback"]).read_bytes()}
        )
        != candidate["feedback_hashes"]
    ):
        raise EvolveError("accepted native feedback changed")
    result = {
        p: safe_file(run, f"staged/{candidate['index']}/{p}").read_bytes()
        for p in candidate["hashes"]
    }
    if _hashes(result) != candidate["hashes"]:
        raise EvolveError("accepted native candidate bytes changed")
    return result


def _issue(root, run, state):
    if state["state"] == "complete" or state["pending"]:
        return
    if (
        time.time() >= state["deadline"]
        or state["actions"] >= state["budget"]["actions"]
    ):
        _finish(state, "deadline_or_action_cap")
        return
    if any(k in state["budget"] and state[k] is None for k in ("tokens", "cost_usd")):
        state["current"] = "incumbent"
        _finish(state, "resource_cap_unaccounted")
        return
    if any(
        state["known_" + k] >= state["budget"].get(k, float("inf"))
        for k in ("tokens", "cost_usd")
    ):
        _finish(state, "known_resource_budget_exhausted")
        return
    action = state["next"]
    trial = state["trial"]
    label, phase = (
        (state["author"], "development")
        if action == "author"
        else (trial["label"], trial["phase"])
    )
    spec = state["contract"]["specification"]
    identifier = digest([state["identity"], state["actions"], action, label, phase])
    relative = state["cache"] + "/actions/" + str(state["actions"])
    baseline = _tree(
        safe_file(root, state["cache"] + "/baseline/.check", exists=False).parent
    )
    if _hashes(baseline) != state["contract"]["inputs"]:
        raise EvolveError("native baseline snapshot changed")
    overlay = _overlay(root, run, state, label)
    modes = state["contract"]["modes"]
    if action == "grade":
        execution = trial["execution"]
        frozen = _tree(
            safe_file(root, execution["snapshot"] + "/.check", exists=False).parent
        )
        if _artifact(root / execution["snapshot"]) != execution["artifact_sha256"]:
            raise EvolveError("executor artifacts changed before independent grading")
        material = frozen | {p: baseline[p] for p in spec.get("grading_paths", [])}
        modes = _modes(root / execution["snapshot"], frozen) | {
            p: modes[p] for p in spec.get("grading_paths", [])
        }
    else:
        hidden = {c["path"] for c in spec["cases"] if c["split"] == "heldout"}
        if phase == "heldout":
            hidden.remove(trial["cases"][len(trial["rows"])]["path"])
        hidden.update(spec.get("grading_paths", []))
        material = {p: b for p, b in (baseline | overlay).items() if p not in hidden}
    _materialize(root, relative, material, modes)
    request = {
        "request_id": identifier,
        "action": action,
        "label": label,
        "phase": phase,
        "workspace": relative,
        "deadline": state["deadline"],
        "dispatch_once": True,
        "model": spec["model"],
        "rubric": spec["rubric"],
        "guidance": _guidance(
            baseline,
            overlay,
            {g["path"] for g in spec["guidance"]},
            {g["path"]: g for g in spec["guidance"]},
        ),
    }
    if action == "author":
        request["feedback"] = list(state["feedback"])
        request["candidate_changes"] = {
            name: {
                p: b.decode("utf-8")
                for p, b in _overlay(root, run, state, name).items()
            }
            for name in state["candidates"]
        }
    else:
        request["case"] = trial["cases"][len(trial["rows"])]
        if action == "grade":
            request["execution"] = trial["execution"]
            request["input_sha256"] = _artifact(root / relative)
    state.update(
        pending=request, state="awaiting_" + action, actions=state["actions"] + 1
    )


def _select(state):
    rows = state["measurements"]
    best = "incumbent"
    for label in ("general", "domain", "composition"):
        if label in rows and _comparison_reason(rows[label], rows[best]):
            best = label
    state["best"] = best
    if best == "incumbent":
        _finish(state, "incumbent_retained")
    else:
        _begin_trial(state, "incumbent", "heldout")


def _after_trial(context, state, measurement):
    trial = state["trial"]
    label, phase = trial["label"], trial["phase"]
    key = label if phase == "development" else "heldout:" + label
    state["measurements"][key] = measurement
    with project_lock(context.parent):
        _utility(context, key, measurement, state["identity"])
    if phase == "heldout":
        if label == "incumbent":
            _begin_trial(state, state["best"], "heldout")
        else:
            if _comparison_reason(
                measurement, state["measurements"]["heldout:incumbent"]
            ):
                state["current"] = label
            _finish(
                state,
                "heldout_qualified"
                if state["current"] != "incumbent"
                else "heldout_regression_or_unmeasured",
            )
        return
    state["feedback"].append({"label": label, **measurement})
    if label in {"incumbent", "general"}:
        state.update(
            next="author", author="general" if label == "incumbent" else "domain"
        )
    elif label == "domain" and all(
        _comparison_reason(
            state["measurements"].get(lens, {}), state["measurements"]["incumbent"]
        )
        for lens in ("general", "domain")
    ):
        state.update(next="author", author="composition")
    else:
        _select(state)


def _accept(context, run, state, result):
    root, request = context.parent, state["pending"]
    action, label = request["action"], request["label"]
    _charge(state, result)
    if action == "author":
        if result.get("decline") is True:
            if label == "general":
                state.update(next="author", author="domain")
            else:
                _select(state)
            return
        edits = result.get("edits")
        allowed = {g["path"] for g in state["contract"]["specification"]["guidance"]}
        if (
            not isinstance(edits, dict)
            or not edits
            or not set(edits) <= allowed
            or any(not isinstance(v, str) for v in edits.values())
        ):
            raise EvolveError(
                "author edits must map declared guidance paths to UTF-8 text"
            )
        feedback = run / "native-feedback" / (request["request_id"][:16] + ".json")
        _write(
            feedback,
            {"request_id": request["request_id"], "observations": request["feedback"]},
        )
        raw = {
            "target_file": list(edits),
            "diagnosis": result.get("diagnosis"),
            "prediction": result.get("prediction"),
            "change_sketch": "Native " + label + " proposal after observed feedback",
            "evidence": [feedback.relative_to(root).as_posix()],
        }
        errors = validate_candidate(raw, context)
        if errors:
            raise EvolveError("; ".join(errors))
        path = run / "candidates.jsonl"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        index = len([line for line in existing.splitlines() if line.strip()])
        if index >= MAX_CANDIDATES:
            raise EvolveError("native run exceeds existing candidate limit")
        for name, body in edits.items():
            target = safe_file(run, f"staged/{index}/{name}", exists=False)
            write_text_atomic(target, body)
        write_text_atomic(path, existing + json.dumps(raw, sort_keys=True) + "\n")
        state["candidates"][label] = {
            "index": index,
            "hashes": _hashes({p: v.encode() for p, v in edits.items()}),
            "candidate": raw,
            "feedback": feedback.relative_to(run).as_posix(),
            "feedback_hashes": _hashes(
                {feedback.relative_to(run).as_posix(): feedback.read_bytes()}
            ),
        }
        _begin_trial(state, label, "development")
    elif action == "execute":
        if result.get("status") != "completed":
            _finish(state, "execution_unmeasured")
            return
        workspace = safe_file(
            root, request["workspace"] + "/.check", exists=False
        ).parent
        artifacts = _tree(workspace)
        if any(
            _hashes(artifacts).get(row["path"]) != row["sha256"]
            for row in request["guidance"]
        ):
            raise EvolveError("executor changed pinned guidance")
        snapshot = state["cache"] + "/artifacts/" + request["request_id"][:16]
        _materialize(root, snapshot, artifacts, _modes(workspace, artifacts))
        state["trial"]["execution"] = {
            "actor_id": result["actor_id"],
            "snapshot": snapshot,
            "artifact_sha256": _artifact(root / snapshot),
            "loaded": result.get("loaded"),
            "tokens": result.get("tokens"),
            "cost_usd": result.get("cost_usd"),
        }
        state["next"] = "grade"
    else:
        if _artifact(root / request["workspace"]) != request["input_sha256"]:
            raise EvolveError("independent grader modified its immutable inputs")
        execution = state["trial"]["execution"]
        if _artifact(root / execution["snapshot"]) != execution["artifact_sha256"]:
            raise EvolveError("frozen executor artifact tampering")
        values = dict(result, loaded=execution["loaded"])
        for key in ("tokens", "cost_usd"):
            values[key] = (
                execution[key] + result[key]
                if execution[key] is not None and result.get(key) is not None
                else None
            )
        measurement = _measurement(
            values,
            {"cases": [request["case"]], "guidance": request["guidance"]},
            native=True,
        )
        if measurement["status"] != "measured":
            _finish(state, "grade_unmeasured")
            return
        trial = state["trial"]
        trial["rows"].append(measurement)
        if len(trial["rows"]) < len(trial["cases"]):
            state["next"] = "execute"
            return
        rows = trial["rows"]
        combined = dict(
            rows[-1],
            cases=[c for r in rows for c in r["cases"]],
            evidence="\n".join(r["evidence"] for r in rows),
        )
        for key in ("tokens", "cost_usd"):
            combined[key] = (
                sum(r[key] for r in rows)
                if all(r[key] is not None for r in rows)
                else None
            )
        combined = _measurement(
            combined,
            {"cases": trial["cases"], "guidance": request["guidance"]},
            native=True,
        )
        baseline = _tree(
            safe_file(root, state["cache"] + "/baseline/.check", exists=False).parent
        )
        combined["guidance_bytes"] = _captured_guidance_bytes(
            baseline,
            _overlay(root, run, state, label),
            {g["path"] for g in state["contract"]["specification"]["guidance"]},
        )
        _after_trial(context, state, combined)


def run_native(context: Path, run: Path, submission: dict) -> dict:
    """Issue once or ingest one host response; caller owns the replay lock."""
    root, path = context.parent, run / "native.json"
    if len(json.dumps(submission).encode()) > MAX_RAW_BYTES:
        raise EvolveError("native submission exceeds bounded receipt size")
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("receipt_sha256") != digest(
            {k: v for k, v in state.items() if k != "receipt_sha256"}
        ):
            raise EvolveError("native checkpoint tampering")
        if state.get("inflight"):
            raise EvolveError(
                "interrupted native response; inspect before starting a new run"
            )
        if (
            _hashes(_inputs(root)) != state["contract"]["inputs"]
            or _modes(root, state["contract"]["inputs"]) != state["contract"]["modes"]
            or _runtime() != state["contract"]["environment"]
            or _controller() != state["contract"]["controller"]
        ):
            raise EvolveError("pinned native baseline/environment changed")
        for label in state["candidates"]:
            _overlay(root, run, state, label)
        catalog = (
            [
                json.loads(line)
                for line in (run / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            if state["candidates"]
            else []
        )
        if any(
            c["index"] >= len(catalog) or catalog[c["index"]] != c["candidate"]
            for c in state["candidates"].values()
        ):
            raise EvolveError("accepted native candidate metadata changed")
        if state["state"] != "complete" and time.time() >= state["deadline"]:
            state.update(current="incumbent", tokens=None, cost_usd=None)
            _finish(state, "deadline_exceeded_pending_usage_unknown")
            _save(path, state)
            if (
                "request_id" in submission
                and submission["request_id"] not in state["responses"]
            ):
                raise EvolveError("native response arrived after the fixed deadline")
        if "request_id" not in submission:
            if submission != state["contract"]["specification"]:
                raise EvolveError("native specification changed; start a new run")
            return _view(state)
        response_id, fingerprint = submission["request_id"], digest(submission)
        if response_id in state["responses"]:
            if state["responses"][response_id] != fingerprint:
                raise EvolveError("conflicting native response")
            return _view(state)
        if state["pending"] is None or response_id != state["pending"]["request_id"]:
            raise EvolveError("out-of-order native response")
        if time.time() >= state["deadline"]:
            raise EvolveError("native response arrived after the fixed deadline")
        if not isinstance(submission.get("result"), dict):
            raise EvolveError("native response requires a result object")
        _preflight(context, state, submission["result"])
        original = json.loads(json.dumps(state))
        state["inflight"] = fingerprint
        _save(path, state)
        try:
            _accept(context, run, state, submission["result"])
        except (EvolveError, OSError, ValueError, TypeError) as exc:
            # Never retry possibly committed author writes or artifact snapshots silently.
            raise EvolveError(
                f"native response rejected; preserved interruption marker: {exc}"
            ) from exc
        state.pop("inflight")
        state["responses"][response_id] = fingerprint
        state["pending"] = None
        _save(path, state)
        if (
            original["pending"]["action"] == "grade"
            and state["current"] != "incumbent"
            and any(
                state["known_" + k] > state["budget"].get(k, float("inf"))
                for k in ("tokens", "cost_usd")
            )
        ):
            state.update(
                current="incumbent", stop_reason="known_resource_budget_exhausted"
            )
    else:
        if submission.get("execution") != "native":
            raise EvolveError("native run has not been initialized")
        state = _initialize(context, run, submission)
    if any(k in state["budget"] and state[k] is None for k in ("tokens", "cost_usd")):
        state["current"] = "incumbent"
        _finish(state, "resource_cap_unaccounted")
    _issue(root, run, state)
    _save(path, state)
    return _view(state)
