"""`dummyindex context equip` CLI: verb dispatcher + per-verb handlers.

``dispatch`` (`run`, `apply`, `add-specialist`), ``verbs`` (status / refresh / reset /
remove / uninstall / patch), ``discover`` and ``install`` (plugin-manager verbs),
``plugin_state`` (local plugin-state readers + `verify`), ``common`` (shared helpers).
"""

from __future__ import annotations

from .common import project_slug
from .dispatch import run

__all__ = ["project_slug", "run"]
