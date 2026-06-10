"""`dummyindex context equip` CLI — verb dispatcher + per-verb handlers.

Split by concern:

- ``dispatch.py`` — `run` verb dispatcher + the `apply` / `add-specialist` paths
- ``verbs.py``    — lifecycle verbs (status / refresh / reset / uninstall / patch)
- ``discover.py`` — plugin-manager verbs (discover / install)
- ``common.py``   — flag pulling + root/slug helpers shared by the verbs
"""

from __future__ import annotations

from .common import project_slug
from .dispatch import run

__all__ = ["project_slug", "run"]
