"""Frozen data carriers for the failure-miner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .enums import LoopKind, SkillDirectiveKind


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool_use/tool_result pair extracted from a transcript.

    ``signature`` is the canonical form (see ``signatures.py``) that groups
    re-fetch/retry variants. No output excerpt is kept: the report is
    git-tracked, and an excerpt could publish another repo's source, a token,
    or a credential. Only the measured size survives.
    """

    tool_name: str
    signature: str
    is_error: bool
    output_bytes: int


@dataclass(frozen=True)
class RepeatedSignature:
    """A canonical signature that recurred at least the threshold count
    within a single transcript."""

    tool_name: str
    signature: str
    kind: LoopKind
    occurrences: int
    estimated_wasted_tokens: int


@dataclass(frozen=True)
class MinerReport:
    """The deterministic result of one scan over a transcript store.

    ``scanned_sessions`` counts transcripts that parsed; ``unreadable_sessions``
    those yielding nothing usable, kept separate so coverage isn't overstated.
    """

    signatures: tuple[RepeatedSignature, ...] = ()
    scanned_sessions: int = 0
    unreadable_sessions: int = 0


@dataclass(frozen=True)
class SkillDirective:
    """One normalized directive extracted from a human prompt."""

    skill: str
    kind: SkillDirectiveKind


@dataclass(frozen=True)
class SkillDirectiveEvent:
    """One privacy-minimized correction or revocation event.

    Prompt text is deliberately absent. ``event_key`` is a one-way digest used
    to collapse copied rows across resumed/forked transcripts.
    """

    skill: str
    kind: SkillDirectiveKind
    event_key: str
    session_id: str
    occurred_at: datetime | None
    fallback_order: tuple[int, ...]


@dataclass(frozen=True)
class RecurringSkillCorrection:
    """A skill whose post-revocation positive corrections meet the threshold."""

    skill: str
    corrections: int
    sessions: int
