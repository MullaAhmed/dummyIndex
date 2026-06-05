"""Typed errors for the templates-first equip flow."""
from __future__ import annotations


class EquipError(Exception):
    """Base for every equip failure the CLI maps to an exit code."""


class TemplateError(EquipError):
    """A template file is missing or unreadable from the shipped skill package."""
