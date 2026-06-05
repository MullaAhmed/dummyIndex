"""Typed errors for the templates-first equip flow."""
from __future__ import annotations


class EquipError(Exception):
    """Base for every equip failure the CLI maps to an exit code."""


class TemplateError(EquipError):
    """A template file is missing or unreadable from the shipped skill package."""


class ResetError(EquipError):
    """:func:`lifecycle.reset` was asked for an item it cannot restore."""


class PatchError(EquipError):
    """A patch could not be applied: unknown item, or ``old`` not matched once."""
