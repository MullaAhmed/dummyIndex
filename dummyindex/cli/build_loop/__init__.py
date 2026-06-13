"""`dummyindex context build` CLI — drive a proposal's checklist.

Split by concern:

- ``dispatch.py`` — `run` flag parsing + `--check`/`--skip`/`--status` verbs
- ``waves.py``    — `--next` / `--next-wave` dispatch (wave grouping)
"""

from __future__ import annotations

from .dispatch import run

__all__ = ["run"]
