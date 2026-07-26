"""`dummyindex install` — copy the skill tree + auto-init the project.

Extracted from ``dummyindex/__main__.py`` (and, in a later wave, split out of
a single ``install.py`` module) so the entrypoint stays a thin dispatcher.
Split by concern:

- ``orchestrate.py``    — the `install()` function itself
- ``family_write.py``   — the unconditional real-tree write path for one
  skill family (`_install_skill_family`, `_symlinked_skill_install_directory`)
- ``link_dispatch.py``  — the AUTO/LINK/COPY link-mode dispatch helpers
  `install()` calls into (stamp comparison, sibling backfill, report lines)
- ``project_init.py``   — the auto-init / project-init helpers (`.context/`
  build, Claude/Codex guidance, hooks, default-plugins)

Public surface (kept stable for ``installer/__init__.py``, ``repair.py``, and
tests — every name below is imported by at least one of those):

``run_link_install`` is re-exported here (not merely used internally) for a
second reason beyond the usual public surface: `orchestrate.py`'s `install()`
calls it through this very module object (``import
dummyindex.installer.install as _install_pkg`` + ``_install_pkg.
run_link_install(...)``), not as a bare name, so a test that monkeypatches
``dummyindex.installer.install.run_link_install`` observes the patch. See
`orchestrate.py`'s module docstring for the full explanation. The same
applies to `_install_project_hooks`, called the same way from
`project_init.py`.
"""

from __future__ import annotations

from ..link import run_link_install
from .family_write import _install_skill_family, _symlinked_skill_install_directory
from .link_dispatch import (
    _agents_family_stamp_state,
    _backfill_sibling_stamps,
    _claude_narrowing_link_gate,
    _link_state_report_line,
)
from .orchestrate import install
from .project_init import (
    _auto_init_project,
    _install_project_hooks,
    _refresh_equipment_step,
    _write_default_config,
)

__all__ = [
    "_agents_family_stamp_state",
    "_auto_init_project",
    "_backfill_sibling_stamps",
    "_claude_narrowing_link_gate",
    "_install_project_hooks",
    "_install_skill_family",
    "_link_state_report_line",
    "_refresh_equipment_step",
    "_symlinked_skill_install_directory",
    "_write_default_config",
    "install",
    "run_link_install",
]
