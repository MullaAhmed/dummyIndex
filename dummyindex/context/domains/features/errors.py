"""Typed exception for `context.features` operations."""

from __future__ import annotations


class FeatureRenameError(ValueError):
    """Raised when `rename_feature` / `merge_feature` / `remove_flow` /
    `write_section` can't safely complete."""
