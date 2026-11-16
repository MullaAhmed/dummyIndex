"""Closed alphabets for the lesson record."""

from __future__ import annotations

from enum import Enum


class Confidence(str, Enum):
    """How sure the author is that the lesson generalizes."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Verdict(str, Enum):
    """Observed effect of one edit; prefer ``CONFOUNDED`` to invented attribution."""

    HELPED = "helped"
    HURT = "hurt"
    NO_OBSERVED_EFFECT = "no_observed_effect"
    CONFOUNDED = "confounded"


class DeltaOp(str, Enum):
    """The rule operation a lesson amounts to."""

    ADD = "add"
    REVISE = "revise"
    SUPERSEDE = "supersede"


class LearningStatus(str, Enum):
    """Closed alphabet of a persisted learning event status."""

    APPLIED = "applied"
    EVALUATED = "evaluated"
    BLOCKED = "blocked"
    NO_ENTRY = "no_entry"
    PENDING = "pending"
    IGNORED = "ignored"
    FAILED = "failed"
