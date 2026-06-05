"""Typed errors for the session-memory domain.

Named `SessionMemoryError` (not `MemoryError`) so we never shadow the
builtin `MemoryError`.
"""
from __future__ import annotations


# Area base exception for the session-memory domain.
class SessionMemoryError(Exception):
    """Base for session-memory domain failures."""
