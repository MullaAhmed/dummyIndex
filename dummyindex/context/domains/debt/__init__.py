"""Technical-debt ledger: deterministic harvest of Python ``#`` debt markers.

``harvest_debt(project_root)`` walks the repo's Python source for ``# TODO:`` /
``# FIXME:`` / ``# HACK:`` / ``# DEBT:`` comments and returns a repo-relative,
path-then-line-sorted :class:`DebtLedger`. Pure (read-only over source); the CLI
that renders and optionally persists the ledger is a separate module.

Public surface (the CLI + test import target):

- ``DebtRow``, ``DebtLedger`` — frozen dataclasses
- ``harvest_debt`` — the harvester
"""
from __future__ import annotations

from .harvest import harvest_debt
from .models import DebtLedger, DebtRow

__all__ = [
    "DebtLedger",
    "DebtRow",
    "harvest_debt",
]
