"""Public surface for the equip eval/benchmark stage.

Re-exports the whole eval package so tests and the CLI import from the package,
not its submodules (the canonical-trio layering rule): the closed
:class:`EvalOutcome` alphabet, the typed error hierarchy, the frozen data shapes,
the pure ``score_run``/``aggregate_benchmark`` scoring, and the pure
parse/serialize helpers. The CLI boundary (``dummyindex/cli/equip/eval.py``)
owns the ``json``/filesystem I/O; this package holds the pure logic.
"""

from __future__ import annotations

from .cases import (
    benchmark_to_dict,
    parse_eval_suite,
    parse_observations,
    result_from_dict,
    result_to_dict,
    suite_to_dict,
)
from .enums import EvalOutcome
from .errors import (
    EvalError,
    EvalSuiteError,
    EvalSuiteNotFoundError,
    MissingObservationError,
    ObservationMismatchError,
    ObservationsError,
)
from .models import (
    BenchmarkReport,
    EvalCase,
    EvalResult,
    TriggerObservation,
)
from .score import aggregate_benchmark, score_run

__all__ = [
    "BenchmarkReport",
    "EvalCase",
    "EvalError",
    "EvalOutcome",
    "EvalResult",
    "EvalSuiteError",
    "EvalSuiteNotFoundError",
    "MissingObservationError",
    "ObservationMismatchError",
    "ObservationsError",
    "TriggerObservation",
    "aggregate_benchmark",
    "benchmark_to_dict",
    "parse_eval_suite",
    "parse_observations",
    "result_from_dict",
    "result_to_dict",
    "score_run",
    "suite_to_dict",
]
