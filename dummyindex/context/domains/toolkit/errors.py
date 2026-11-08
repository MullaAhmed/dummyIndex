"""Typed failure for the toolkit facade.

Every failure carries a snake_case ``code`` and a human ``message``. The CLI turns
it into the ``{"error": {"code", "message"}}`` envelope.
"""

from __future__ import annotations


class ToolkitError(Exception):
    """A toolkit operation that the caller must see as an error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_envelope(self) -> dict[str, dict[str, str]]:
        return {"error": {"code": self.code, "message": self.message}}
