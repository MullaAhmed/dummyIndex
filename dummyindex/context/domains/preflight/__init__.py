"""Preflight inventory of a repo's existing Claude Code setup.

Public surface: build a read-only :class:`PreflightReport` and render it for
the user before dummyindex writes anything.
"""
from __future__ import annotations

from .inventory import build_preflight_report
from .models import PreflightReport, SettingsState
from .render import render_preflight_md

__all__ = [
    "PreflightReport",
    "SettingsState",
    "build_preflight_report",
    "render_preflight_md",
]
