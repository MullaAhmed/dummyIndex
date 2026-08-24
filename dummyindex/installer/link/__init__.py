"""Symlink-single-source family link primitives.

Wave 2 of the ``symlink-single-source-install`` proposal
(``.context/proposals/symlink-single-source-install/``). This package is the
single place that classifies, creates, verifies, and sweeps the per-family
``.claude/skills/<family>`` symlinks that point at the one real
``.agents/skills/<family>`` tree.

Split by concern:

- ``families.py``    — family enumeration + crash-safe temp-artifact naming
- ``models.py``       — the classification alphabet + result records
- ``classify.py``     — the read-only classify/verify sweep
- ``create.py``       — the safe replacement dance (`create_family_links`)
- ``sweep.py``        — the dangling-link sweep (`remove_dangling_family_links`)
- ``orchestrate.py``  — the capability pre-probe + AUTO/LINK/COPY dispatch

**Import law (acyclic by construction)**: every module in this package
imports **only** ``..common`` (plus stdlib) and its own siblings under
``link/``. It must never import ``install``, ``repair``, or ``uninstall`` —
those modules import *this* package in a later wave, and a back-import here
would create a cycle. If a helper feels like it belongs in
``install``/``repair``, it does not belong here either; hoist the shared
primitive into ``common.py`` instead (as Wave 1 already did for
``is_owned_copy``, ``_remove_owned_tree_no_follow``, and friends).

The 9 skill families are always enumerated from ``_SIBLING_SKILLS``
(``common.py``) — main ``"dummyindex"`` plus its 7 siblings — **never** a
``dummyindex*`` glob, which would also catch the equip-generated
``dummyindex-verify`` skill (not part of this family).

**Security note — explicit allowlist, no scope inference**: every entry
point that walks a parent chain (`classify_family_link`,
`verify_family_links`, `create_family_links`, `remove_dangling_family_links`,
`run_link_install`) takes an ``allowed_symlinks`` keyword-only parameter that
defaults to the empty frozenset — fail closed. This module never infers
"user scope" from `Path.home()` or the `HOME` environment variable (a prior
version did, and a `HOME`-spoofed environment — CI runners, containers,
wrapper scripts — could flip a project-scope symlinked `.claude` from
refused to admitted). The caller (`install`, in a later wave) is the one
place that actually knows whether this run is user-scope and is expected to
pass the dotfiles allowance explicitly.

**Invariant on every ``allowed_symlinks`` entry** (all five public entry
points above): each entry must be a host root directly under ``scope_root``
— either ``scope_root / ".claude"`` or ``scope_root / ".claude" / "skills"``
— never anything deeper, never a path outside ``scope_root`` entirely, and
never derived from an environment variable (`HOME` or otherwise). A caller
that already knows this run is user-scope passes the concrete allowlist
itself; this module never infers it.

Public surface (kept stable for ``installer/install.py``/``repair.py``/
``uninstall.py`` and tests — every name below is imported by at least one
of those, `_readlink_parts` included, which several tests reach directly):
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
