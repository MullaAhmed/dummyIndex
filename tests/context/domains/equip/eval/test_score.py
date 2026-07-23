"""Unit tests for the pure equip-eval scorer (``eval/score.py``).

Covers the two pure entry points and their pinned numeric contract:

- :func:`score_run` — confusion matrix → precision / recall / accuracy on
  all-positive, all-negative, mixed, and empty suites; the "no LLM / no I/O in
  code" spine (works with ``open``/``Path.read_text`` monkeypatched off); and
  bidirectional coverage errors.
- :func:`aggregate_benchmark` — mean + **population** variance of accuracy,
  flaky-iff-differs, single-run degenerate case, and the same-``case_id``-set
  requirement across runs.

Every number here is pinned by ``spec.md`` / the conductor's shape doc and
asserted exactly. These are pure, in-process tests → ``@pytest.mark.unit``
(matching the sibling equip suites).
"""

from __future__ import annotations

import builtins
import pathlib

import pytest

from dummyindex.context.domains.equip.eval import (
    EvalCase,
    EvalError,
    EvalOutcome,
    EvalResult,
    MissingObservationError,
    ObservationMismatchError,
    ObservationsError,
    TriggerObservation,
    aggregate_benchmark,
    score_run,
)

# --------------------------------------------------------------------------- #
# fixture helpers
# --------------------------------------------------------------------------- #


def _case(case_id: str, *, expects: bool) -> EvalCase:
    """A labelled suite case (prompt content is irrelevant to scoring)."""
    return EvalCase(
        case_id=case_id, prompt=f"prompt for {case_id}", expects_trigger=expects
    )


def _obs(case_id: str, *, fired: bool) -> TriggerObservation:
    return TriggerObservation(case_id=case_id, fired=fired)


def _counts_dict(result: EvalResult) -> dict[EvalOutcome, int]:
    """The ``counts`` tuple-of-pairs as an ``{EvalOutcome: int}`` dict."""
    return dict(result.counts)


def _misfire_ids(result: EvalResult) -> set[str]:
    return {c.case_id for c in result.misfires}


# --------------------------------------------------------------------------- #
# confusion matrix — mixed 1TP / 1FP / 1TN / 1FN
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_mixed_suite_confusion_matrix_and_metrics() -> None:
    cases = (
        _case("tp", expects=True),  # expects trigger, fires -> TP
        _case("fp", expects=False),  # no trigger expected, fires -> FP
        _case("tn", expects=False),  # no trigger expected, silent -> TN
        _case("fn", expects=True),  # expects trigger, silent -> FN
    )
    observations = (
        _obs("tp", fired=True),
        _obs("fp", fired=True),
        _obs("tn", fired=False),
        _obs("fn", fired=False),
    )

    result = score_run(cases, observations)

    # counts via the dataclass field (tuple-of-pairs) — all four cells == 1.
    assert _counts_dict(result) == {
        EvalOutcome.TRUE_POSITIVE: 1,
        EvalOutcome.FALSE_POSITIVE: 1,
        EvalOutcome.TRUE_NEGATIVE: 1,
        EvalOutcome.FALSE_NEGATIVE: 1,
    }
    # ... and via to_dict()["counts"] (string-keyed, all four keys always).
    assert result.to_dict()["counts"] == {
        "true-positive": 1,
        "false-positive": 1,
        "true-negative": 1,
        "false-negative": 1,
    }

    # precision = TP/(TP+FP) = 1/2; recall = TP/(TP+FN) = 1/2; acc = (TP+TN)/4 = 1/2.
    assert result.precision == pytest.approx(0.5)
    assert result.recall == pytest.approx(0.5)
    assert result.accuracy == pytest.approx(0.5)

    # misfires are exactly the FP + FN cases.
    assert _misfire_ids(result) == {"fp", "fn"}


@pytest.mark.unit
def test_mixed_suite_records_per_case_outcomes_in_suite_order() -> None:
    cases = (
        _case("tp", expects=True),
        _case("fp", expects=False),
        _case("tn", expects=False),
        _case("fn", expects=True),
    )
    observations = (
        _obs("fn", fired=False),  # deliberately out of order — score by case_id
        _obs("tn", fired=False),
        _obs("fp", fired=True),
        _obs("tp", fired=True),
    )

    result = score_run(cases, observations)

    # ``cases`` records (case_id, outcome) in SUITE order regardless of obs order.
    assert result.cases == (
        ("tp", EvalOutcome.TRUE_POSITIVE),
        ("fp", EvalOutcome.FALSE_POSITIVE),
        ("tn", EvalOutcome.TRUE_NEGATIVE),
        ("fn", EvalOutcome.FALSE_NEGATIVE),
    )


# --------------------------------------------------------------------------- #
# all-positive suite
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_all_positive_suite_all_fired_is_perfect() -> None:
    cases = (_case("a", expects=True), _case("b", expects=True))
    observations = (_obs("a", fired=True), _obs("b", fired=True))

    result = score_run(cases, observations)

    assert _counts_dict(result) == {
        EvalOutcome.TRUE_POSITIVE: 2,
        EvalOutcome.FALSE_POSITIVE: 0,
        EvalOutcome.TRUE_NEGATIVE: 0,
        EvalOutcome.FALSE_NEGATIVE: 0,
    }
    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(1.0)
    assert result.accuracy == pytest.approx(1.0)
    assert result.misfires == ()


# --------------------------------------------------------------------------- #
# pinned edges: all-negative + empty suite
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_all_negative_suite_silent_is_zero_precision_recall_full_accuracy() -> None:
    # Every case expects NO trigger and the tool stays silent (all correct TNs).
    cases = (_case("n1", expects=False), _case("n2", expects=False))
    observations = (_obs("n1", fired=False), _obs("n2", fired=False))

    result = score_run(cases, observations)

    assert _counts_dict(result) == {
        EvalOutcome.TRUE_POSITIVE: 0,
        EvalOutcome.FALSE_POSITIVE: 0,
        EvalOutcome.TRUE_NEGATIVE: 2,
        EvalOutcome.FALSE_NEGATIVE: 0,
    }
    # No positive predictions -> precision 0.0; no actual positives -> recall 0.0.
    assert result.precision == 0.0
    assert result.recall == 0.0
    # Every case correct -> accuracy 1.0.
    assert result.accuracy == 1.0
    assert result.misfires == ()


@pytest.mark.unit
def test_empty_suite_scores_zero_accuracy() -> None:
    result = score_run((), ())

    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.accuracy == 0.0
    assert result.cases == ()
    assert result.misfires == ()
    assert _counts_dict(result) == {
        EvalOutcome.TRUE_POSITIVE: 0,
        EvalOutcome.FALSE_POSITIVE: 0,
        EvalOutcome.TRUE_NEGATIVE: 0,
        EvalOutcome.FALSE_NEGATIVE: 0,
    }


# --------------------------------------------------------------------------- #
# purity: no filesystem / LLM in code — decisions arrive only as data
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_score_run_is_pure_with_filesystem_access_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If the scorer ever reached to disk (or an LLM behind a file), these would
    # explode. Trigger decisions must arrive ONLY as in-memory data.
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("score_run must not touch the filesystem")

    monkeypatch.setattr(builtins, "open", _boom)
    monkeypatch.setattr(pathlib.Path, "read_text", _boom)

    cases = (_case("a", expects=True), _case("b", expects=False))
    observations = (_obs("a", fired=True), _obs("b", fired=False))

    result = score_run(cases, observations)

    assert result.accuracy == pytest.approx(1.0)
    assert result.misfires == ()


# --------------------------------------------------------------------------- #
# bidirectional coverage errors
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_observation_for_unknown_case_raises_mismatch() -> None:
    cases = (_case("known", expects=True),)
    observations = (
        _obs("known", fired=True),
        _obs("ghost", fired=True),  # case_id absent from the suite
    )
    with pytest.raises(ObservationMismatchError):
        score_run(cases, observations)


@pytest.mark.unit
def test_unobserved_case_raises_missing_and_lists_the_id() -> None:
    cases = (_case("observed", expects=True), _case("orphan", expects=False))
    observations = (_obs("observed", fired=True),)  # "orphan" has no observation

    with pytest.raises(MissingObservationError) as excinfo:
        score_run(cases, observations)

    # the raised message must name the unobserved case_id
    assert "orphan" in str(excinfo.value)


@pytest.mark.unit
def test_duplicate_observation_case_id_raises_observations_error() -> None:
    """Two observations for one case_id fail loud (never silent last-wins).

    A duplicated parallel-subagent judgment would otherwise make the score depend
    on observation order — the spec's coverage rationale demands failing loud.
    """
    cases = (_case("c1", expects=True),)
    observations = (_obs("c1", fired=False), _obs("c1", fired=True))
    with pytest.raises(ObservationsError) as excinfo:
        score_run(cases, observations)
    assert "c1" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# aggregate_benchmark — mean + POPULATION variance (÷N)
# --------------------------------------------------------------------------- #


def _run_from_outcomes(
    outcomes: dict[str, tuple[bool, bool]],
    *,
    tool_name: str = "tool",
) -> EvalResult:
    """Build one scored run from ``{case_id: (expects_trigger, fired)}``."""
    cases = tuple(
        _case(cid, expects=expects) for cid, (expects, _fired) in outcomes.items()
    )
    observations = tuple(
        _obs(cid, fired=fired) for cid, (_expects, fired) in outcomes.items()
    )
    return score_run(cases, observations, tool_name=tool_name)


@pytest.mark.unit
def test_benchmark_mean_and_population_variance_of_two_runs() -> None:
    # Run A is perfect on {x} (acc 1.0); run B is wrong on {x} (acc 0.0)? No —
    # we want accuracies [1.0, 0.5] over a SHARED case_id set {x, y}.
    #   run A: x correct, y correct        -> acc 1.0
    #   run B: x correct, y wrong          -> acc 0.5
    run_a = _run_from_outcomes({"x": (True, True), "y": (False, False)})
    run_b = _run_from_outcomes({"x": (True, True), "y": (False, True)})

    assert run_a.accuracy == pytest.approx(1.0)
    assert run_b.accuracy == pytest.approx(0.5)

    report = aggregate_benchmark((run_a, run_b))

    assert report.mean_accuracy == pytest.approx(0.75)
    # POPULATION variance (÷N) of [1.0, 0.5] about mean 0.75:
    #   ((1.0-0.75)^2 + (0.5-0.75)^2) / 2 = (0.0625 + 0.0625) / 2 = 0.0625.
    # (spec's illustrative 0.015625 is an arithmetic typo; ÷N gives 0.0625.)
    assert report.accuracy_variance == pytest.approx(0.0625)


# --------------------------------------------------------------------------- #
# aggregate_benchmark — flakiness
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_benchmark_flags_flaky_case_but_not_stable_case() -> None:
    # case "steady" has the SAME outcome across both runs; case "shaky" flips.
    #   run A: steady=TP (expects,fired),  shaky=TP (expects,fired)
    #   run B: steady=TP (expects,fired),  shaky=FN (expects,silent)
    run_a = _run_from_outcomes({"steady": (True, True), "shaky": (True, True)})
    run_b = _run_from_outcomes({"steady": (True, True), "shaky": (True, False)})

    report = aggregate_benchmark((run_a, run_b))

    assert "shaky" in report.flaky_case_ids
    assert "steady" not in report.flaky_case_ids
    assert report.flaky_case_ids == ("shaky",)


@pytest.mark.unit
def test_benchmark_identical_runs_have_zero_variance_and_no_flaky() -> None:
    run_a = _run_from_outcomes({"a": (True, True), "b": (False, False)})
    run_b = _run_from_outcomes({"a": (True, True), "b": (False, False)})

    report = aggregate_benchmark((run_a, run_b))

    assert report.accuracy_variance == 0.0
    assert report.flaky_case_ids == ()
    assert report.mean_accuracy == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# aggregate_benchmark — degenerate + mismatch
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_benchmark_single_run_is_trivially_non_flaky() -> None:
    run = _run_from_outcomes({"a": (True, True), "b": (True, False)})

    report = aggregate_benchmark((run,))

    assert report.accuracy_variance == 0.0
    assert report.flaky_case_ids == ()
    # single run's accuracy carries straight through as the mean
    assert report.mean_accuracy == pytest.approx(run.accuracy)


@pytest.mark.unit
def test_benchmark_mismatched_case_id_sets_raises_eval_error() -> None:
    # A suite edited mid-benchmark: run B carries a case run A never had.
    run_a = _run_from_outcomes({"a": (True, True), "b": (False, False)})
    run_b = _run_from_outcomes({"a": (True, True), "c": (False, False)})

    with pytest.raises(EvalError):
        aggregate_benchmark((run_a, run_b))
