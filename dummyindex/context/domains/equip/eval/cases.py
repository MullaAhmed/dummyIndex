"""Pure parse/serialize for the equip eval stage — the single serialize surface.

No filesystem, no ``json`` import, no network. The parse functions take an
ALREADY-PARSED ``data`` object (the result of ``json.loads`` at the CLI
boundary), validate its SHAPE fail-fast, and raise the typed eval errors. The
CLI layer (``cli/equip/eval.py``) owns the ``json.loads`` and catches
``json.JSONDecodeError``/``OSError``; this module owns shape validation only.
That split is what makes the ``dict -> parse -> to_dict`` round-trip hold.

Wire shapes (produced by the ``*_to_dict`` helpers, consumed by the parsers):

- suite:        ``{"cases": [{"case_id", "prompt", "expects_trigger"}, ...]}``
- observations: ``{"observations": [{"case_id", "fired"}, ...]}``

``expects_trigger`` / ``fired`` are validated with strict ``isinstance(x, bool)``
so a JSON ``1``/``0`` (which ``json`` never emits for a Python ``bool`` but a
hand-authored file might) is rejected rather than silently coerced.
"""

from __future__ import annotations

from typing import Any

from .enums import EvalOutcome
from .errors import EvalError, EvalSuiteError, ObservationsError
from .models import BenchmarkReport, EvalCase, EvalResult, TriggerObservation

__all__ = [
    "benchmark_to_dict",
    "parse_eval_suite",
    "parse_observations",
    "result_from_dict",
    "result_to_dict",
    "suite_to_dict",
]


def _require_str(
    item: dict[str, Any],
    key: str,
    *,
    error: type[EvalSuiteError | ObservationsError],
    where: str,
) -> str:
    """Return ``item[key]`` as a ``str`` or raise ``error`` fail-fast."""
    if key not in item:
        raise error(f"{where} is missing required field {key!r}")
    value = item[key]
    if not isinstance(value, str):
        raise error(
            f"{where} field {key!r} must be a string, got {type(value).__name__}"
        )
    return value


def _require_bool(
    item: dict[str, Any],
    key: str,
    *,
    error: type[EvalSuiteError | ObservationsError],
    where: str,
) -> bool:
    """Return ``item[key]`` as a strict ``bool`` or raise ``error`` fail-fast.

    Uses ``isinstance(value, bool)`` deliberately — an ``int`` such as ``1`` is
    rejected (``isinstance(1, bool)`` is ``False``), so a malformed suite never
    slips a truthy int through as a trigger label.
    """
    if key not in item:
        raise error(f"{where} is missing required field {key!r}")
    value = item[key]
    if not isinstance(value, bool):
        raise error(
            f"{where} field {key!r} must be a boolean, got {type(value).__name__}"
        )
    return value


def parse_eval_suite(data: Any) -> tuple[EvalCase, ...]:
    """Validate an already-parsed suite object into ``tuple[EvalCase, ...]``.

    Fail-fast, raising :class:`EvalSuiteError` on any malformed input: ``data``
    not a dict, ``data["cases"]`` missing / not a list, a case item not a dict or
    missing/ill-typed fields, or a **duplicate** ``case_id`` (it is the join key
    into observations and the flaky key across benchmark runs). Order preserved.
    """
    if not isinstance(data, dict):
        raise EvalSuiteError(f"suite must be a JSON object, got {type(data).__name__}")
    if "cases" not in data or not isinstance(data["cases"], list):
        raise EvalSuiteError("suite must contain a 'cases' array")

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(data["cases"]):
        where = f"suite case #{index}"
        if not isinstance(raw, dict):
            raise EvalSuiteError(f"{where} must be an object, got {type(raw).__name__}")
        case_id = _require_str(raw, "case_id", error=EvalSuiteError, where=where)
        prompt = _require_str(raw, "prompt", error=EvalSuiteError, where=where)
        expects_trigger = _require_bool(
            raw, "expects_trigger", error=EvalSuiteError, where=where
        )
        if case_id in seen:
            raise EvalSuiteError(f"duplicate case_id {case_id!r} in suite")
        seen.add(case_id)
        cases.append(
            EvalCase(
                case_id=case_id,
                prompt=prompt,
                expects_trigger=expects_trigger,
            )
        )
    return tuple(cases)


def parse_observations(data: Any) -> tuple[TriggerObservation, ...]:
    """Validate an already-parsed observations object into ``tuple[TriggerObservation, ...]``.

    Fail-fast, raising :class:`ObservationsError` on any malformed input: ``data``
    not a dict, ``data["observations"]`` missing / not a list, an item not a dict
    or missing/ill-typed fields. Order preserved. Duplicate observation
    ``case_id``s are **not** an error here — coverage is the scorer's concern.
    """
    if not isinstance(data, dict):
        raise ObservationsError(
            f"observations must be a JSON object, got {type(data).__name__}"
        )
    if "observations" not in data or not isinstance(data["observations"], list):
        raise ObservationsError("observations must contain an 'observations' array")

    observations: list[TriggerObservation] = []
    for index, raw in enumerate(data["observations"]):
        where = f"observation #{index}"
        if not isinstance(raw, dict):
            raise ObservationsError(
                f"{where} must be an object, got {type(raw).__name__}"
            )
        case_id = _require_str(raw, "case_id", error=ObservationsError, where=where)
        fired = _require_bool(raw, "fired", error=ObservationsError, where=where)
        observations.append(TriggerObservation(case_id=case_id, fired=fired))
    return tuple(observations)


def result_from_dict(data: Any) -> EvalResult:
    """Reconstruct an :class:`EvalResult` from its :func:`result_to_dict` form.

    The inverse of :func:`result_to_dict`, so a ``<tool>.run-*.result.json`` file
    can be read back into an :class:`EvalResult` for ``aggregate_benchmark``.
    Fail-fast: any malformed result — missing field, unknown ``EvalOutcome``
    value, wrong shape — raises :class:`EvalError`. A corrupt run file must fail
    the benchmark loud, never be silently skipped (which would deflate variance).
    ``counts`` is rebuilt in the canonical ``EvalOutcome`` definition order so the
    round-trip ``result_from_dict(result_to_dict(r)) == r`` holds.
    """
    if not isinstance(data, dict):
        raise EvalError(f"result must be a JSON object, got {type(data).__name__}")
    try:
        cases = tuple(
            (str(c["case_id"]), EvalOutcome(c["outcome"])) for c in data["cases"]
        )
        counts_map = data["counts"]
        counts = tuple(
            (outcome, int(counts_map[outcome.value])) for outcome in EvalOutcome
        )
        misfires = tuple(
            EvalCase(
                case_id=str(m["case_id"]),
                prompt=str(m["prompt"]),
                expects_trigger=bool(m["expects_trigger"]),
            )
            for m in data["misfires"]
        )
        return EvalResult(
            tool_name=str(data["tool_name"]),
            cases=cases,
            counts=counts,
            precision=float(data["precision"]),
            recall=float(data["recall"]),
            accuracy=float(data["accuracy"]),
            misfires=misfires,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EvalError(f"malformed eval result: {exc}") from exc


def suite_to_dict(cases: tuple[EvalCase, ...]) -> dict[str, Any]:
    """Serialize a suite to its wire shape ``{"cases": [...]}``."""
    return {"cases": [c.to_dict() for c in cases]}


def result_to_dict(result: EvalResult) -> dict[str, Any]:
    """Serialize an :class:`EvalResult` (delegates to its ``to_dict()``)."""
    return result.to_dict()


def benchmark_to_dict(report: BenchmarkReport) -> dict[str, Any]:
    """Serialize a :class:`BenchmarkReport` (delegates to its ``to_dict()``)."""
    return report.to_dict()
