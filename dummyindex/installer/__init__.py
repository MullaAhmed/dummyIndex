"""dummyindex skill installer — the `dummyindex install` / `uninstall` surface.

Split by concern: ``common.py`` (version, skill paths, commands), ``install/``
(skill tree + git-repo auto-init), ``link/`` (Claude-side family links),
``repair.py``, ``ownership.py`` (per-file ownership), ``uninstall.py`` and
``args.py`` (flag parsing for both verbs).
"""

from __future__ import annotations

from .args import parse_install_args, parse_uninstall_args
from .common import CODEX_SKILL_REL, COMMANDS_REL, PACKAGE_VERSION, SKILL_REL, LinkMode
from .install import install
from .uninstall import uninstall

__all__ = [
    "COMMANDS_REL",
    "CODEX_SKILL_REL",
    "LinkMode",
    "PACKAGE_VERSION",
    "SKILL_REL",
    "parse_install_args",
    "parse_uninstall_args",
    "install",
    "uninstall",
]
