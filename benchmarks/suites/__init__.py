"""Suite adapters: task sources and prompt builders for both arms."""

from __future__ import annotations


class SuiteDataError(Exception):
    """Raised when dataset access is unavailable or malformed."""
