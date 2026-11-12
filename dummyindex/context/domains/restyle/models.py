"""Frozen dataclasses for the restyle (ASD-STE100 rewrite) domain — data only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenDiff:
    """Protected tokens that a rewrite lost (fails) or gained (warns)."""

    lost: tuple[str, ...]
    added: tuple[str, ...]
