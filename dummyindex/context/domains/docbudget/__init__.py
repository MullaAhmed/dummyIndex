"""docbudget: word-budget ratchet for authored `.context/` docs and packaged skills.

Public surface: ``measure``, ``scan``, ``read_ratchet``, ``format_ratchet``,
``check``, ``update_ratchet``, ``write_ratchet``, ``BudgetGroup``, ``BudgetViolation``,
``UpdateResult``, ``StyleViolation``, ``lint_text``, ``count_violations``.
"""

from __future__ import annotations

from .enums import BudgetGroup
from .models import BudgetViolation, UpdateResult
from .ratchet import (
    check,
    format_ratchet,
    measure,
    read_ratchet,
    scan,
    update_ratchet,
    write_ratchet,
)
from .style import StyleViolation, count_violations, lint_text

__all__ = [
    "BudgetGroup",
    "BudgetViolation",
    "StyleViolation",
    "UpdateResult",
    "count_violations",
    "lint_text",
    "check",
    "format_ratchet",
    "measure",
    "read_ratchet",
    "scan",
    "update_ratchet",
    "write_ratchet",
]
