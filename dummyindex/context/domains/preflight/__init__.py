"""Preflight inventory of a repo's existing Claude Code setup.

Public surface: build a read-only :class:`PreflightReport`, render it for the
user before dummyindex writes anything, and probe whether an existing
``.context/`` is dummyindex's to manage (:func:`context_ownership`).
"""

from __future__ import annotations

from .inventory import build_preflight_report
from .models import PreflightReport, SettingsState
from .ownership import ContextOwnership, context_ownership
from .render import render_preflight_md

__all__ = [
    "ContextOwnership",
    "PreflightReport",
    "SettingsState",
    "build_preflight_report",
    "context_ownership",
    "render_preflight_md",
]
