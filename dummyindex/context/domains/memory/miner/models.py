"""Frozen data carriers for the failure-miner."""

from __future__ import annotations

from dataclasses import dataclass

from .enums import LoopKind


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool_use/tool_result pair extracted from a transcript.

    ``signature`` is the canonicalized form (see ``signatures.py``) used to
    group re-fetch/retry variants of the same call together.

    No excerpt of the tool's output is retained. An earlier cut kept a
    200-character `sample_output` and rendered it into a git-tracked file,
    which would publish whatever happened to be in that output — another
    repo's source, a token, a credential. Only the measured size survives.
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
    counts those opened but yielding nothing usable. Reporting them separately
    keeps the coverage claim honest — a single number would silently overstate
    how much of the store was actually read.
    """

    signatures: tuple[RepeatedSignature, ...] = ()
    scanned_sessions: int = 0
    unreadable_sessions: int = 0
