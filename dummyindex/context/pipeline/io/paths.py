# path-confinement primitives — keep filesystem access inside a trusted root
"""Named, tested replacements for inline ``x.resolve().relative_to(root)`` guards.

- ``resolve_under_root`` is pure (``.resolve()`` and compare): is the candidate
  ``root`` or inside it once both are resolved? Catches ``../`` traversal and
  absolute-path joins.
- ``is_safe_read_target`` stats the filesystem to reject symlinks, non-regular
  files and oversize files before a caller opens them; it never raises.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def resolve_under_root(candidate: Path, root: Path) -> Path | None:
    """Return the resolved ``candidate`` iff it is ``root`` or a descendant.

    Pure apart from ``Path.resolve()``. Both paths are resolved first, so ``../``
    traversal and absolute-path joins (``root / "/etc/x"`` is ``/etc/x``) are
    caught. Returns ``None`` when ``candidate`` escapes ``root``. Already-resolved
    candidates are fine (``.resolve()`` is idempotent).
    """
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate == resolved_root:
        return resolved_candidate
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return resolved_candidate


def is_safe_read_target(path: Path, *, max_bytes: int) -> bool:
    """True iff ``path`` is a plain regular file no larger than ``max_bytes``.

    ``lstat`` rejects symlinks before following them (the link itself is the
    attack surface, even with a benign target), then non-regular files (FIFO,
    device, socket, directory) and anything over ``max_bytes``. Never raises:
    any ``OSError`` (missing, permission denied, broken link) means ``False``.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return False
    if not stat.S_ISREG(info.st_mode):
        return False
    return info.st_size <= max_bytes
