"""dummyindex skill installer — the `dummyindex install` / `uninstall` surface.

Extracted from ``dummyindex/__main__.py`` so the entrypoint stays a thin
dispatcher. Split by concern:

- ``_common.py``  — package version, skill paths, slash-command copy/remove
- ``install.py``  — skill-tree copy + git-repo auto-init
- ``uninstall.py`` — remove everything ``install`` wrote
- ``_args.py``    — flag parsing shared by both verbs
"""

from __future__ import annotations

from .args import parse_install_args
from .common import COMMANDS_REL, PACKAGE_VERSION, SKILL_REL
from .install import install
from .uninstall import uninstall

__all__ = [
    "COMMANDS_REL",
    "PACKAGE_VERSION",
    "SKILL_REL",
    "parse_install_args",
    "install",
    "uninstall",
]
