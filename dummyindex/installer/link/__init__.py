"""Family links: each ``.claude/skills/<family>`` symlinks to the real ``.agents`` tree.

Import law: modules here import only stdlib, ``..common`` and siblings, never
``install``/``repair``/``uninstall`` (they import this package, so a back-import
is a cycle); hoist shared helpers into ``common.py``.

Security invariant: every entry point that walks a parent chain takes a
keyword-only ``allowed_symlinks`` defaulting to empty (fail closed). Each entry is
``scope_root / ".claude"`` or ``scope_root / ".claude" / "skills"``, never deeper
or outside ``scope_root``, and never derived from an environment variable: a
spoofed ``HOME`` could admit a symlinked project ``.claude``. The caller, which
knows the scope, passes it.
"""

from __future__ import annotations

from .classify import (
    _readlink_parts,  # re-exported: tests/test_install_link_primitives.py imports it
    classify_family_link,
    family_link_target,
    relative_link_value,
    verify_family_links,
)
from .create import create_family_links
from .models import (
    FamilyLinkClassification,
    FamilyLinkState,
    LinkCapabilityError,
    LinkInstallResult,
    LinkResult,
)
from .orchestrate import run_link_install
from .sweep import remove_dangling_family_links

__all__ = [
    "FamilyLinkClassification",
    "FamilyLinkState",
    "LinkCapabilityError",
    "LinkInstallResult",
    "LinkResult",
    "_readlink_parts",
    "classify_family_link",
    "create_family_links",
    "family_link_target",
    "relative_link_value",
    "remove_dangling_family_links",
    "run_link_install",
    "verify_family_links",
]
