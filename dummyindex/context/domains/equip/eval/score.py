"""Pure scoring for the equip eval stage — confusion matrix + benchmark stats.

No I/O, no ``json``, no ``subprocess``, no network, no filesystem, no LLM. Trigger
decisions arrive **only** as in-memory :class:`TriggerObservation` data (produced
by the ``dummyindex-equip`` skill's LLM judgment and fed in here as data) — the
"never an LLM judge in code" spine holds. A Wave-4 AST import-scan asserts this
module imports no ``subprocess``/network module.

Two entry points:

- :func:`score_run` — reduce a labelled suite + its observed firing decisions to a
  frozen :class:`EvalResult` (confusion matrix → precision / recall / accuracy).
- :func:`aggregate_benchmark` — fold K :class:`EvalResult` runs of the same suite
  into a :class:`BenchmarkReport` (mean + population variance of accuracy, flaky
  case ids).

All numeric conventions are pinned by ``spec.md`` and asserted downstream:
zero-denominator precision/recall ⇒ ``0.0`` (sklearn ``zero_division=0``); accuracy
always defined (empty suite ⇒ ``0.0``); population variance (÷N); ``<2`` runs ⇒
``0.0`` variance + empty flaky list.
"""

from __future__ import annotations

from .enums import EvalOutcome
from .errors import (
    EvalError,
    MissingObservationError,
    ObservationMismatchError,
    ObservationsError,
)
from .models import BenchmarkReport, EvalCase, EvalResult, TriggerObservation

__all__ = [
    "aggregate_benchmark",
    "score_run",
]

# Canonical outcome order for the ``counts`` tuple — always all four, even zeros.
# Derived from the enum definition order so this module and ``cases.py`` (which
# rebuilds ``counts`` by iterating ``EvalOutcome`` in :func:`result_from_dict`)
# share ONE source of truth: reordering the enum can never desync the two.
_CANONICAL_OUTCOMES: tuple[EvalOutcome, ...] = tuple(EvalOutcome)


def _classify(*, expects_trigger: bool, fired: bool) -> EvalOutcome:
    """Reduce one (expected, observed) pair to its confusion-matrix cell."""
    if expects_trigger:
        return EvalOutcome.TRUE_POSITIVE if fired else EvalOutcome.FALSE_NEGATIVE
    return EvalOutcome.FALSE_POSITIVE if fired else EvalOutcome.TRUE_NEGATIVE


def _ratio(numerator: int, denominator: int) -> float:
    """Guarded ratio: zero denominator ⇒ ``0.0`` (sklearn ``zero_division=0``)."""
    return numerator / denominator if denominator > 0 else 0.0


def score_run(
    cases: tuple[EvalCase, ...],
    observations: tuple[TriggerObservation, ...],
    *,
    tool_name: str = "",
) -> EvalResult:
    """Score a labelled suite against its observed firing decisions.

    Coverage is checked **bidirectionally and first** (fail loud — a dropped
    parallel-subagent judgment must never score a partial suite): every
    observation must match a suite case (:class:`ObservationMismatchError`) and
    every suite case must have an observation (:class:`MissingObservationError`).

    Args:
        cases: The labelled suite, in the order results should be recorded.
        observations: The observed firing decisions (one per case, any order).
        tool_name: Recorded on the result (keyword-only so the plan's
            ``score_run(cases, observations)`` call form stays valid and the CLI
            can still pass the tool name).

    Returns:
        A frozen :class:`EvalResult`.

    Raises:
        ObservationsError: Two observations share a ``case_id`` (a duplicated
            judgment — silently keeping the last would make the score depend on
            observation order).
        ObservationMismatchError: An observation's ``case_id`` is not in the suite.
        MissingObservationError: A suite case has no matching observation.
    """
    # 1. Bidirectional coverage FIRST (fail loud — a dropped OR duplicated
    #    parallel-subagent judgment must never be scored silently).
    seen_obs: set[str] = set()
    duplicates: list[str] = []
    for obs in observations:
        if obs.case_id in seen_obs:
            duplicates.append(obs.case_id)
        seen_obs.add(obs.case_id)
    if duplicates:
        raise ObservationsError(
            "duplicate observation(s) for case_id(s): "
            + ", ".join(sorted(set(duplicates)))
        )

    by_case = {obs.case_id: obs for obs in observations}
    case_ids = {c.case_id for c in cases}

    extra = [obs.case_id for obs in observations if obs.case_id not in case_ids]
    if extra:
        raise ObservationMismatchError(
            "observation case_id(s) not present in the suite: "
            + ", ".join(sorted(set(extra)))
        )

    missing = [c.case_id for c in cases if c.case_id not in by_case]
    if missing:
        raise MissingObservationError(
            "suite case(s) have no observation: " + ", ".join(missing)
        )

    # 2. Confusion matrix, in suite order.
    tally: dict[EvalOutcome, int] = {outcome: 0 for outcome in _CANONICAL_OUTCOMES}
    scored_cases: list[tuple[str, EvalOutcome]] = []
    misfires: list[EvalCase] = []
    for case in cases:
        outcome = _classify(
            expects_trigger=case.expects_trigger,
            fired=by_case[case.case_id].fired,
        )
        scored_cases.append((case.case_id, outcome))
        tally[outcome] += 1
        if outcome in (EvalOutcome.FALSE_POSITIVE, EvalOutcome.FALSE_NEGATIVE):
            misfires.append(case)

    tp = tally[EvalOutcome.TRUE_POSITIVE]
    fp = tally[EvalOutcome.FALSE_POSITIVE]
    tn = tally[EvalOutcome.TRUE_NEGATIVE]
    fn = tally[EvalOutcome.FALSE_NEGATIVE]

    # 3. Metrics — zero denominator ⇒ 0.0; accuracy always defined.
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    total = len(cases)
    accuracy = _ratio(tp + tn, total)

    # 4. Canonical counts tuple — always all four outcomes, even zeros.
    counts = tuple((outcome, tally[outcome]) for outcome in _CANONICAL_OUTCOMES)

    # 5. Assemble the frozen result.
    return EvalResult(
        tool_name=tool_name,
        cases=tuple(scored_cases),
        counts=counts,
        precision=precision,
        recall=recall,
        accuracy=accuracy,
        misfires=tuple(misfires),
    )


def _outcome_by_case(result: EvalResult) -> dict[str, EvalOutcome]:
    """Map ``case_id`` → outcome for one run (from its ``(case_id, outcome)`` pairs)."""
    return {case_id: outcome for case_id, outcome in result.cases}


def aggregate_benchmark(results: tuple[EvalResult, ...]) -> BenchmarkReport:
    """Fold K eval runs of the same suite into a stability/flakiness report.

    All runs MUST cover the same ``case_id`` set (derived from each run's
    ``(case_id, outcome)`` pairs); a mismatch ⇒ :class:`EvalError` (a suite was
    edited mid-benchmark). Variance is **population** (÷N); ``<2`` runs ⇒ ``0.0``
    variance and an empty flaky list (a single run is trivially non-flaky). A case
    is flaky **iff** its outcome is not identical across every run.

    Args:
        results: The eval runs to aggregate (may be empty).

    Returns:
        A frozen :class:`BenchmarkReport`.

    Raises:
        EvalError: Two runs cover different ``case_id`` sets.
    """
    tool_name = results[0].tool_name if results else ""

    # Same-case_id-set requirement across every run.
    per_run: list[dict[str, EvalOutcome]] = [_outcome_by_case(r) for r in results]
    if per_run:
        shared = set(per_run[0])
        for run_outcomes in per_run[1:]:
            if set(run_outcomes) != shared:
                raise EvalError(
                    "benchmark runs cover different case_id sets "
                    "(a suite was edited mid-benchmark)"
                )
    else:
        shared = set()

    accs = [r.accuracy for r in results]
    mean_accuracy = sum(accs) / len(accs) if accs else 0.0

    # Population variance (÷N); < 2 runs ⇒ 0.0.
    if len(accs) < 2:
        accuracy_variance = 0.0
    else:
        accuracy_variance = sum((a - mean_accuracy) ** 2 for a in accs) / len(accs)

    # A case is flaky iff its outcome is not identical across all runs.
    flaky = [
        case_id
        for case_id in shared
        if len({run_outcomes[case_id] for run_outcomes in per_run}) > 1
    ]

    return BenchmarkReport(
        tool_name=tool_name,
        runs=results,
        mean_accuracy=mean_accuracy,
        accuracy_variance=accuracy_variance,
        flaky_case_ids=tuple(sorted(flaky)),
    )
