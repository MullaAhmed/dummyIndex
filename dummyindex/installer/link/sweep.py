"""The dangling-link sweep, shared by uninstall + dedupe.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

from pathlib import Path

import dummyindex.installer.link as _link_pkg

from ..common import skills_root_rel
from .families import _family_names
from .models import FamilyLinkState

# Module-identity note: `classify_family_link` below is called through
# `_link_pkg` (this package's own `__init__.py`), not as a bare name imported
# from `.classify`. `tests/test_install_link_primitives.py::
# test_remove_dangling_family_links_rechecks_immediately_before_unlink`
# monkeypatches `classify_family_link` on `dummyindex.installer.link` (the
# package object) and expects THIS function's own scan-then-recheck calls to
# see the patch — a bare-name call resolved via `sweep.py`'s own globals
# would not observe an attribute set on a *different* module object. The
# `import dummyindex.installer.link as _link_pkg` self-import is safe despite
# executing while this very package is still initializing: it binds via
# `sys.modules`, which already holds the (in-progress) package object, and
# the attribute is only ever read later, at call time, once `link/__init__.py`
# has finished and `classify_family_link` is a real attribute on it.


def remove_dangling_family_links(
    scope_root: Path,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> tuple[Path, ...]:
    """Unlink every `OURS_DANGLING` family link at ``scope_root``; `FOREIGN`
    and every other state are left untouched.

    Shared by ``uninstall`` (after removing the codex family) and ``dedupe``
    (after removing a codex family duplicate) so dummyindex-owned links
    never dangle after either operation. Re-classifies immediately before
    each unlink (mirrors `execute_repairs`'s re-preflight) rather than acting
    on a pre-computed plan, so a filesystem change between families in the
    same sweep is never missed.

    ``allowed_symlinks`` is the fail-closed parent-chain allowlist forwarded
    to `classify_family_link` — see its docstring (including the host-root
    invariant). Defaults to the empty frozenset.
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
        # Re-run the identical check immediately before unlinking (mirrors
        # `execute_repairs`'s re-preflight, `repair.py:339`) in case the
        # filesystem changed between the scan above and now.
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
