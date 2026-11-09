"""Frozen dataclasses and enums for the docbudget domain. Data only."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BudgetViolation", "UpdateResult"]


@dataclass(frozen=True)
class BudgetViolation:
    """One doc over budget. ``recorded`` is ``None`` for an unrecorded doc."""

    path: str
    words: int
    limit: int
    recorded: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "words": self.words,
            "limit": self.limit,
            "recorded": self.recorded,
        }


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of ``update_ratchet``: the new ratchet plus what was refused."""

    ratchet: dict[str, int]
    lowered: tuple[str, ...]
    refused: tuple[BudgetViolation, ...]
