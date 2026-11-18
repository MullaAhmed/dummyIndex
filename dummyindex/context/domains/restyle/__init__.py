"""restyle: snapshot protected tokens so an ASD-STE100 rewrite cannot drop facts.

Only the snapshot check lives here; the run loop is a later step.
"""

from __future__ import annotations

from .errors import RestyleError, TokenLossError
from .models import TokenDiff
from .snapshot import assert_tokens_kept, diff_tokens, protected_tokens

__all__ = [
    "RestyleError",
    "TokenDiff",
    "TokenLossError",
    "assert_tokens_kept",
    "diff_tokens",
    "protected_tokens",
]
