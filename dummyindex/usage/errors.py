"""Typed exceptions for the usage area.

The CLI boundary (`__main__._run_usage`) catches `UsageError` and maps it to
a stderr line + exit code; inner code raises, the CLI translates.
"""

from __future__ import annotations


class UsageError(Exception):
    """A usage report could not be produced.

    Carries the offending path (if any) so the CLI can render a helpful line.
    """

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path
