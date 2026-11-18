"""Closed alphabets for the probation lifecycle."""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    """Lifecycle state of one chat-derived rule."""

    OBSERVED = "observed"
    PROPOSED = "proposed"
    PROBATION = "probation"
    PROMOTED = "promoted"
    SUSPENDED = "suspended"
    DEMOTED = "demoted"
    EXPIRED = "expired"
    QUARANTINED = "quarantined"


class Route(str, Enum):
    """Blast-radius tier an attributed item falls into."""

    COUNT = "count"
    CONVENTION = "convention"
    RECONCILE = "reconcile"
    EXPLICIT = "explicit"


class Followed(str, Enum):
    """Result of the followed-check for one exposed session."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


LIVE = frozenset({State.PROBATION, State.SUSPENDED})
