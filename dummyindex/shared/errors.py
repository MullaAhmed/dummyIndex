"""Error type shared by the guard, the project lock and the lesson contract."""


class EvolveError(Exception):
    """An evolve operation could not safely complete."""
