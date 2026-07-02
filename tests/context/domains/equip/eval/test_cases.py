"""Parse/serialize + round-trip tests for the equip eval ``cases`` module.

Covers the ``cases.py`` half of the pure eval core (Task 9): suite/observations
parsing fail-fast, the ``dict -> parse -> to_dict`` round-trip both directions,
duplicate-``case_id`` rejection (the join + flaky key), and the JSON-stability +
thin-delegation contract for ``result_to_dict`` / ``benchmark_to_dict``.

All imports come from the eval PACKAGE surface, not its submodules, per the
canonical-trio layering rule.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from dummyindex.context.domains.equip.eval import (
    BenchmarkReport,
    EvalCase,
    EvalError,
    EvalOutcome,
    EvalResult,
    EvalSuiteError,
    ObservationsError,
    TriggerObservation,
    benchmark_to_dict,
    parse_eval_suite,
    parse_observations,
    result_from_dict,
    result_to_dict,
    suite_to_dict,
)

# --------------------------------------------------------------------------- #
# Suite round-trip — both directions
# --------------------------------------------------------------------------- #


def _well_formed_suite_dict() -> dict[str, Any]:
    """A 2-case suite dict with mixed ``expects_trigger``, in wire shape."""
    return {
        "cases": [
            {
                "case_id": "pos-1",
                "prompt": "extract the tables from this PDF",
                "expects_trigger": True,
            },
            {
                "case_id": "neg-1",
                "prompt": "what is the capital of France",
                "expects_trigger": False,
            },
        ]
    }


@pytest.mark.unit
def test_suite_round_trip_dict_to_dict() -> None:
    """``suite_to_dict(parse_eval_suite(d)) == d`` for a well-formed suite dict."""
    d = _well_formed_suite_dict()
    assert suite_to_dict(parse_eval_suite(d)) == d


@pytest.mark.unit
def test_suite_round_trip_cases_to_cases() -> None:
    """``parse_eval_suite(suite_to_dict(cases)) == cases`` for parsed cases."""
    cases = parse_eval_suite(_well_formed_suite_dict())
    assert parse_eval_suite(suite_to_dict(cases)) == cases


@pytest.mark.unit
def test_suite_parse_preserves_order_and_mixed_flags() -> None:
    """The parsed tuple keeps suite order and both bool labels round-trip."""
    cases = parse_eval_suite(_well_formed_suite_dict())
    assert cases == (
        EvalCase(
            case_id="pos-1",
            prompt="extract the tables from this PDF",
            expects_trigger=True,
        ),
        EvalCase(
            case_id="neg-1",
            prompt="what is the capital of France",
            expects_trigger=False,
        ),
    )


# --------------------------------------------------------------------------- #
# Malformed suite ⇒ EvalSuiteError
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "data",
    [
        pytest.param(["not", "a", "dict"], id="data-not-a-dict"),
        pytest.param({}, id="missing-cases-key"),
        pytest.param({"cases": {"case_id": "x"}}, id="cases-not-a-list"),
        pytest.param({"cases": ["not-a-dict"]}, id="case-item-not-a-dict"),
        pytest.param(
            {"cases": [{"prompt": "p", "expects_trigger": True}]},
            id="case-missing-case_id",
        ),
        pytest.param(
            {"cases": [{"case_id": "c", "expects_trigger": True}]},
            id="case-missing-prompt",
        ),
        pytest.param(
            {"cases": [{"case_id": "c", "prompt": "p"}]},
            id="case-missing-expects_trigger",
        ),
        pytest.param(
            {"cases": [{"case_id": 1, "prompt": "p", "expects_trigger": True}]},
            id="case_id-not-a-str",
        ),
        pytest.param(
            {"cases": [{"case_id": "c", "prompt": "p", "expects_trigger": 1}]},
            id="expects_trigger-int-strict-bool",
        ),
    ],
)
def test_parse_eval_suite_rejects_malformed(data: Any) -> None:
    with pytest.raises(EvalSuiteError):
        parse_eval_suite(data)


@pytest.mark.unit
def test_parse_eval_suite_rejects_duplicate_case_id() -> None:
    """Duplicate ``case_id`` ⇒ EvalSuiteError — it is the join + flaky key."""
    data = {
        "cases": [
            {"case_id": "dup", "prompt": "first", "expects_trigger": True},
            {"case_id": "dup", "prompt": "second", "expects_trigger": False},
        ]
    }
    with pytest.raises(EvalSuiteError):
        parse_eval_suite(data)


# --------------------------------------------------------------------------- #
# Observations — parse + malformed
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_parse_observations_well_formed() -> None:
    """A well-formed observations dict parses to the expected tuple, in order."""
    data = {
        "observations": [
            {"case_id": "pos-1", "fired": True},
            {"case_id": "neg-1", "fired": False},
        ]
    }
    assert parse_observations(data) == (
        TriggerObservation(case_id="pos-1", fired=True),
        TriggerObservation(case_id="neg-1", fired=False),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "data",
    [
        pytest.param(["not", "a", "dict"], id="data-not-a-dict"),
        pytest.param({}, id="missing-observations-key"),
        pytest.param({"observations": ["not-a-dict"]}, id="observation-not-a-dict"),
        pytest.param(
            {"observations": [{"fired": True}]},
            id="observation-missing-case_id",
        ),
        pytest.param(
            {"observations": [{"case_id": "c", "fired": 1}]},
            id="fired-int-strict-bool",
        ),
    ],
)
def test_parse_observations_rejects_malformed(data: Any) -> None:
    with pytest.raises(ObservationsError):
        parse_observations(data)


# --------------------------------------------------------------------------- #
# result / benchmark JSON-stability + thin-delegation round-trips
# --------------------------------------------------------------------------- #


def _sample_result() -> EvalResult:
    """An EvalResult with one FP + one FN misfire, all four counts populated."""
    return EvalResult(
        tool_name="pdf-extract",
        cases=(
            ("pos-1", EvalOutcome.TRUE_POSITIVE),
            ("neg-1", EvalOutcome.FALSE_POSITIVE),
            ("pos-2", EvalOutcome.FALSE_NEGATIVE),
            ("neg-2", EvalOutcome.TRUE_NEGATIVE),
        ),
        counts=(
            (EvalOutcome.TRUE_POSITIVE, 1),
            (EvalOutcome.FALSE_POSITIVE, 1),
            (EvalOutcome.TRUE_NEGATIVE, 1),
            (EvalOutcome.FALSE_NEGATIVE, 1),
        ),
        precision=0.5,
        recall=0.5,
        accuracy=0.5,
        misfires=(
            EvalCase(case_id="neg-1", prompt="decoy", expects_trigger=False),
            EvalCase(case_id="pos-2", prompt="missed", expects_trigger=True),
        ),
    )


def _sample_benchmark() -> BenchmarkReport:
    return BenchmarkReport(
        tool_name="pdf-extract",
        runs=(_sample_result(),),
        mean_accuracy=0.5,
        accuracy_variance=0.0,
        flaky_case_ids=("pos-2",),
    )


@pytest.mark.unit
def test_result_to_dict_json_stable_round_trip() -> None:
    """``json.loads(json.dumps(result_to_dict(r))) == result_to_dict(r)``.

    Proves the serialized result shape is JSON-clean (EvalOutcome values are
    plain strings, tuples become lists) and stable across a JSON round-trip.
    """
    r = _sample_result()
    payload = result_to_dict(r)
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.unit
def test_result_to_dict_delegates_to_to_dict() -> None:
    """``result_to_dict(r) == r.to_dict()`` — the thin-delegation contract."""
    r = _sample_result()
    assert result_to_dict(r) == r.to_dict()


@pytest.mark.unit
def test_benchmark_to_dict_json_stable_round_trip() -> None:
    """``json.loads(json.dumps(benchmark_to_dict(b))) == benchmark_to_dict(b)``."""
    b = _sample_benchmark()
    payload = benchmark_to_dict(b)
    assert json.loads(json.dumps(payload)) == payload


@pytest.mark.unit
def test_benchmark_to_dict_delegates_to_to_dict() -> None:
    """``benchmark_to_dict(b) == b.to_dict()`` — the thin-delegation contract."""
    b = _sample_benchmark()
    assert benchmark_to_dict(b) == b.to_dict()


# --------------------------------------------------------------------------- #
# result_from_dict — the real result round-trip + malformed rejection
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_result_round_trip_via_parser() -> None:
    """``result_from_dict(result_to_dict(r)) == r`` — the real result round-trip.

    Unlike the JSON-stability check above, this exercises the parser that the
    benchmark CLI uses to read ``<tool>.run-*.result.json`` files back into
    ``EvalResult`` objects for ``aggregate_benchmark``.
    """
    r = _sample_result()
    assert result_from_dict(result_to_dict(r)) == r


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: ["not", "a", "dict"], id="result-not-a-dict"),
        pytest.param(
            lambda d: {k: v for k, v in d.items() if k != "accuracy"},
            id="missing-accuracy",
        ),
        pytest.param(
            lambda d: {**d, "cases": [{"case_id": "x", "outcome": "bogus"}]},
            id="unknown-outcome-value",
        ),
        pytest.param(
            lambda d: {
                **d,
                "counts": {k: v for k, v in d["counts"].items() if k != "true-positive"},
            },
            id="counts-missing-outcome",
        ),
    ],
)
def test_result_from_dict_rejects_malformed(mutate: Any) -> None:
    """A corrupt run file fails loud (``EvalError``) — never silently skipped."""
    payload = mutate(result_to_dict(_sample_result()))
    with pytest.raises(EvalError):
        result_from_dict(payload)
