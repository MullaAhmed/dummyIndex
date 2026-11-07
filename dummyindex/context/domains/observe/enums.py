"""Closed alphabets for the evolution evidence plane."""

from __future__ import annotations

from enum import Enum


class CorrectionStatus(str, Enum):
    """Lifecycle of one recorded human correction."""

    OPEN = "open"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class Verdict(str, Enum):
    """Attribution of a correction to one exposed item."""

    ATTRIBUTED = "attributed"
    UNRELATED = "unrelated"
    UNKNOWN = "unknown"


class ExposureVia(str, Enum):
    """How an item reached the agent's context."""

    READ = "read"
    SKILL = "skill"
    INJECT = "inject"
