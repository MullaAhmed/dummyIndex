"""Closed alphabet for the equip eval stage."""

from __future__ import annotations

from enum import Enum


class EvalOutcome(str, Enum):
    """The per-case confusion-matrix outcome of a trigger-description eval.

    Each labelled :class:`EvalCase` is scored against its observed firing
    decision into exactly one of these four cells — the confusion matrix that
    ``score_run`` reduces to precision / recall / accuracy. ``(str, Enum)`` so
    the value round-trips cleanly through the result/benchmark JSON on disk.
    """

    TRUE_POSITIVE = "true-positive"  # expected trigger, tool fired
    FALSE_POSITIVE = "false-positive"  # no trigger expected, tool fired
    TRUE_NEGATIVE = "true-negative"  # no trigger expected, tool silent
    FALSE_NEGATIVE = "false-negative"  # expected trigger, tool silent
