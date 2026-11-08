"""Frozen dataclasses for the technical-debt ledger.

Pure data built by ``harvest.py`` from ``# TODO:`` / ``# FIXME:`` / ``# HACK:`` /
``# DEBT:`` markers. ``DebtRow`` paths are already repo-relative POSIX, so
``to_dict`` output is reproducible across machines and never leaks a home dir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DebtRow:
    """One debt marker found on a true comment line of a Python source file.

    ``marker`` is the bare token (``TODO``/``FIXME``/``HACK``/``DEBT``);
    ``ceiling`` the text after it (the current good-enough bound); ``trigger``
    the condition from ``# DEBT: <ceiling>; upgrade: <trigger>``, else ``None``.
    ``no_trigger`` (the flag the ledger tallies) is ``trigger is None``.
    """

    rel_path: str
    line: int
    marker: str
    ceiling: str
    trigger: str | None
    no_trigger: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel_path": self.rel_path,
            "line": self.line,
            "marker": self.marker,
            "ceiling": self.ceiling,
            "trigger": self.trigger,
            "no_trigger": self.no_trigger,
        }


@dataclass(frozen=True)
class DebtLedger:
    """The harvested debt for a repo: rows in deterministic (path, line) order."""

    rows: tuple[DebtRow, ...]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def no_trigger_count(self) -> int:
        return sum(1 for row in self.rows if row.no_trigger)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "no_trigger_count": self.no_trigger_count,
            "rows": [row.to_dict() for row in self.rows],
        }
