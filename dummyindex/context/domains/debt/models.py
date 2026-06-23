"""Frozen dataclasses for the technical-debt ledger.

The harvester (``harvest.py``) walks the repo's Python source for ``# TODO:`` /
``# FIXME:`` / ``# HACK:`` / ``# DEBT:`` comment markers and returns a
``DebtLedger`` — a deterministic, repo-relative view of where debt lives and
which entries declare an upgrade *trigger* versus none (``no_trigger``).

These are pure data: no I/O here. Every path on a ``DebtRow`` is already
repo-relative POSIX (the harvester relativizes it), so ``to_dict`` output is
reproducible across machines and never leaks a home directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DebtRow:
    """One debt marker found on a true comment line of a Python source file.

    ``marker`` is the bare token (``TODO``/``FIXME``/``HACK``/``DEBT``).
    ``ceiling`` is the human text after the marker (the current
    good-enough bound). ``trigger`` is the upgrade condition parsed from the
    structured ``# DEBT: <ceiling>; upgrade: <trigger>`` form, or ``None`` when
    the marker declares none. ``no_trigger`` is ``True`` exactly when
    ``trigger is None`` — it is the flag the ledger tallies.
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
