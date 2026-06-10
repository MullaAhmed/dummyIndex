"""`dummyindex context build` CLI — drive a proposal's checklist.

Split by concern:

- ``_dispatch.py`` — `_cmd_build` flag parsing + status/done verbs
- ``_next.py``     — `--next` / `--next-wave` dispatch (wave grouping)
"""

from __future__ import annotations

from ._dispatch import _cmd_build

__all__ = ["_cmd_build"]
