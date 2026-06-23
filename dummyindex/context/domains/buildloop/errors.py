"""Typed exception for `context.buildloop` operations."""

from __future__ import annotations


class BuildLoopError(Exception):
    """Raised when checklist parsing / flipping or task→equipment mapping
    can't safely complete (missing checklist, ambiguous item key, etc.)."""
