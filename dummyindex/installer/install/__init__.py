"""`dummyindex install` — copy the skill tree + auto-init the project.

Modules: ``orchestrate`` (`install()`), ``family_write`` (one family's real-tree
write), ``link_dispatch`` (AUTO/LINK/COPY helpers and report lines),
``project_init`` (``.context/`` build, guidance, hooks, default plugins).
`run_link_install` and `_install_project_hooks` are called through this package
object, so tests that monkeypatch either name here see the patch.
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
