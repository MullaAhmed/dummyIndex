"""Typed exceptions for the restyle (ASD-STE100 rewrite) domain."""

from __future__ import annotations


class RestyleError(Exception):
    """Base class for every restyle-domain error."""


class TokenLossError(RestyleError):
    """Raised when a rewrite drops or changes a protected token or negation count."""

    def __init__(self, lost: tuple[str, ...]) -> None:
        super().__init__(
            "restyle lost protected token(s): " + ", ".join(repr(t) for t in lost)
        )
        self.lost = lost
