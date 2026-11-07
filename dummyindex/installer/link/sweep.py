"""The dangling-link sweep, shared by uninstall + dedupe.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

from pathlib import Path

import dummyindex.installer.link as _link_pkg

from ..common import skills_root_rel
from .families import _family_names
from .models import FamilyLinkState

# `classify_family_link` is called via `_link_pkg`, not a bare name, so a test that
# patches it on the package (`tests/test_install_link_primitives.py`) is seen here.
# The self-import during package init is safe: it binds the in-progress package
# from `sys.modules`, and the attribute is read only at call time.


def remove_dangling_family_links(
    scope_root: Path,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> tuple[Path, ...]:
    """Unlink each `OURS_DANGLING` family link at ``scope_root``; leave all others.

    Run by ``uninstall`` and ``dedupe`` after removing a codex family, so owned
    links never dangle. Each family is re-classified right before its unlink, so a
    filesystem change mid-sweep is never missed. ``allowed_symlinks``: fail-closed
    parent-chain allowlist (package invariant, see ``link/__init__.py``).
    """
    claude_skills_root = scope_root / skills_root_rel("claude")
    removed: list[Path] = []
    for family in _family_names():
        family_dir = claude_skills_root / family
        classification = _link_pkg.classify_family_link(
            family_dir, scope_root, allowed_symlinks=allowed_symlinks
        )
        if classification.state is not FamilyLinkState.OURS_DANGLING:
            continue
        # Re-check right before unlinking: the filesystem may have changed.
        recheck = _link_pkg.classify_family_link(
            family_dir, scope_root, allowed_symlinks=allowed_symlinks
        )
        if recheck.state is not FamilyLinkState.OURS_DANGLING:
            continue
        try:
            family_dir.unlink()
        except OSError:
            continue
        removed.append(family_dir)
    return tuple(removed)
