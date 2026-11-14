"""Error type shared by the guard, the project lock and the lesson contract."""

from __future__ import annotations


class EvolveError(Exception):
    """An evolve operation could not safely complete."""
