"""Side-effect-free native response validation and accounting."""

import json

from .evolve import validate_candidate
from .evolve_experiments import _finite, _measurement
from .evolve_gate import EvolveError


def _charge(state, result):
    actor = result.get("actor_id")
    if not isinstance(actor, str) or not actor or actor in state["actors"]:
        raise EvolveError("each native action requires a fresh, distinct actor_id")
    for key in ("tokens", "cost_usd"):
        value = result.get(key)
        if value is not None and (
            not _finite(value) or value < 0 or (key == "tokens" and int(value) != value)
        ):
            raise EvolveError("native telemetry must be nonnegative or null")
        state["known_" + key] += value or 0
        state[key] = (
            state[key] + value if state[key] is not None and value is not None else None
        )
    state["actors"].append(actor)


def _preflight(context, state, result):
    """Reject transport/schema errors before any receipt or artifact can be committed."""
    _charge(json.loads(json.dumps(state)), result)
    request = state["pending"]
    if request["action"] == "author":
        if result.get("decline") is True:
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
        errors = validate_candidate(
            {
                "target_file": list(edits),
                "diagnosis": result.get("diagnosis"),
                "prediction": result.get("prediction"),
                "change_sketch": "Native proposal",
                "evidence": [next(iter(allowed))],
            },
            context,
        )
        if errors:
            raise EvolveError("; ".join(errors))
    else:
        if result.get("status") not in (
            {"completed", "infra_error"}
            if request["action"] == "execute"
            else {"measured", "infra_error"}
        ):
            raise EvolveError("native response has invalid action status")
        if result["status"] == "infra_error":
            return
        values = dict(result)
        if request["action"] == "execute":
            values.update(
                status="measured",
                cases=[{"id": request["case"]["id"], "status": "pass"}],
                evidence="Transport validation only",
            )
        else:
            values["loaded"] = state["trial"]["execution"]["loaded"]
        _measurement(
            values,
            {"cases": [request["case"]], "guidance": request["guidance"]},
            native=True,
        )
