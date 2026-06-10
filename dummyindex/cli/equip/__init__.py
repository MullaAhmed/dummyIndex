"""`dummyindex context equip` CLI — verb dispatcher + per-verb handlers.

Split by concern:

- ``_dispatch.py`` — `_cmd_equip` verb dispatcher + the `apply` path
- ``_verbs.py``    — lifecycle verbs (status / refresh / reset / uninstall / patch)
- ``_discover.py`` — plugin-manager verbs (discover / install)
- ``_common.py``   — flag pulling + root/slug helpers shared by the verbs
"""

from __future__ import annotations

from ._common import _project_slug
from ._dispatch import _cmd_equip

__all__ = ["_cmd_equip", "_project_slug"]
