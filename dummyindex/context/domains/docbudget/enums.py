"""Closed alphabets for the docbudget domain."""

from __future__ import annotations

from enum import Enum

__all__ = ["BudgetGroup"]


class BudgetGroup(str, Enum):
    """Which ratchet a doc belongs to."""

    CONTEXT = "context"
    SKILLS = "skills"
    STYLE = "style"

    __str__ = str.__str__
