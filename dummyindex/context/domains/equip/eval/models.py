"""Frozen dataclasses for the equip eval stage + their hand-written ``to_dict()``.

Four data shapes, data only (scoring lives in the sibling ``score`` module,
parse/serialize in ``cases``), following the repo convention: every model is
``@dataclass(frozen=True)``, collection fields are ``tuple[...]`` so the freeze
is real, and serialization is a hand-written ``to_dict()`` that re-inflates
tuples to JSON lists (``conventions/coding-practices.md``).

- :class:`EvalCase` — one labelled trigger-description test case (committed suite).
- :class:`TriggerObservation` — one *observed* firing decision (the skill's LLM
  judgment, fed in as data — never an LLM call from code).
- :class:`EvalResult` — the scored outcome of one eval run over a suite.
- :class:`BenchmarkReport` — the aggregate of K eval runs of the same suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import EvalOutcome

__all__ = [
    "BenchmarkReport",
    "EvalCase",
    "EvalResult",
    "TriggerObservation",
]


@dataclass(frozen=True)
class EvalCase:
    """One labelled trigger-description test case (lives in the committed suite)."""

    case_id: str
    prompt: str
    expects_trigger: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "prompt": self.prompt,
            "expects_trigger": self.expects_trigger,
        }


@dataclass(frozen=True)
class TriggerObservation:
    """One observed firing decision, produced by the skill's LLM judgment and fed in as data."""

    case_id: str
    fired: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "fired": self.fired,
        }


@dataclass(frozen=True)
class EvalResult:
    """The scored outcome of one eval run over a suite."""

    tool_name: str
    # (case_id, outcome) pairs in suite order — NOT EvalCase objects (those are
    # ``misfires``). ``aggregate_benchmark`` compares each case's outcome across
    # runs to decide flakiness, so the per-case outcome must be recorded here.
    cases: tuple[tuple[str, EvalOutcome], ...]
    # (outcome, count) pairs in canonical order TP, FP, TN, FN. A tuple of pairs,
    # not a dict — the repo convention is that frozen dataclasses hold only
    # scalars and tuples (stay hashable/immutable); no dict fields.
    counts: tuple[tuple[EvalOutcome, int], ...]
    precision: float
    recall: float
    accuracy: float
    # The FP + FN cases as full EvalCase objects (distinct from ``cases`` above,
    # which records only (case_id, outcome) pairs).
    misfires: tuple[EvalCase, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "cases": [
                {"case_id": cid, "outcome": outcome.value}
                for cid, outcome in self.cases
            ],
            "counts": {outcome.value: count for outcome, count in self.counts},
            "precision": self.precision,
            "recall": self.recall,
            "accuracy": self.accuracy,
            "misfires": [c.to_dict() for c in self.misfires],
        }


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregate of K eval runs of the same suite: stability + flakiness."""

    tool_name: str
    runs: tuple[EvalResult, ...]
    mean_accuracy: float
    accuracy_variance: float
    flaky_case_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "runs": [r.to_dict() for r in self.runs],
            "mean_accuracy": self.mean_accuracy,
            "accuracy_variance": self.accuracy_variance,
            "flaky_case_ids": list(self.flaky_case_ids),
        }
