"""Frozen, data-only dataclasses for the context-hygiene GC domain."""

from __future__ import annotations

from dataclasses import dataclass

from .enums import CandidateKind


@dataclass(frozen=True)
class Candidate:
    """One generated-doc workspace surfaced by the sweep, with its signals.

    ``signals`` are deterministic tags only (``status:<v>``, ``untracked``,
    ``age-<n>d``, ...). ``recommendation`` and ``reason`` are the pre-council
    hint ``scan`` fills; the council assigns the ``Disposition``.
    """

    kind: CandidateKind
    slug: str
    rel_path: str
    status: str | None = None
    signals: tuple[str, ...] = ()
    tracked: bool = True
    age_days: int | None = None
    recommendation: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class SweepReport:
    """The read-only ``gc status`` payload: candidates + commit-throttle state."""

    candidates: tuple[Candidate, ...] = ()
    anchor: str | None = None
    commits_since: int | None = None
    threshold: int = 0
    should_signal: bool = False
    anchor_orphaned: bool = False


@dataclass(frozen=True)
class DeleteResult:
    """The outcome of a bounded ``delete_workspace`` call.

    Either ``deleted`` (the dir was removed) or ``refused`` (a guard blocked
    it, with the human-readable ``reason``). ``untracked`` records whether the
    target was outside git — i.e. its removal was unrecoverable. In dry-run,
    ``would_delete`` is True when every guard passes.
    """

    deleted: bool = False
    refused: bool = False
    reason: str | None = None
    untracked: bool = False
    would_delete: bool = False
