# path-confinement primitives — keep filesystem access inside a trusted root
"""Named, tested replacements for the inline ``x.resolve().relative_to(root)``
guards scattered across the codebase.

Two concerns, two helpers:

- ``resolve_under_root`` is **pure** — it only calls ``.resolve()`` and compares
  paths. It answers "does this candidate land inside ``root`` (or *is* ``root``)
  once both are fully resolved?", catching ``../`` traversal *and* absolute-path
  joins (``root / "/etc/x"`` collapses to ``/etc/x``, which escapes). It accepts
  both already-resolved and not-yet-resolved candidates — ``.resolve()`` is
  idempotent, so a second resolve on an already-resolved path is a no-op.
- ``is_safe_read_target`` **does** touch the filesystem (``os.lstat`` / ``os.stat``)
  to reject symlinks, non-regular files (FIFO / device / socket), and oversize
  files before a caller opens them. It never raises — a stat failure means
  "not safe", returning ``False`` like the other rejection paths.

These consolidate the inline guards at ``cli/common.py:41-45``,
``context/reconcile_gate.py:64-68``, ``context/build/incremental.py:108-112``,
``context/build/manifest.py:105``, ``cli/check.py:78``, and
``cli/equip/discover.py:257``. Migrating those call sites is a follow-up; this
module only introduces the primitive.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


def resolve_under_root(candidate: Path, root: Path) -> Path | None:
    """Return the resolved ``candidate`` iff it is ``root`` or a descendant.

    Pure — the only side effect is ``Path.resolve()`` (no I/O on the result).
    Both arguments are fully resolved first, so this catches:

    - ``../`` traversal: ``root / "../escape"`` resolves outside ``root``.
    - absolute-path joins: ``root / "/etc/x"`` collapses to ``/etc/x``.

    ``candidate`` may be already-resolved or not — ``.resolve()`` is idempotent,
    so passing a path that is already absolute/resolved is safe and returns that
    same path on success.

    Returns the resolved path on success, or ``None`` when ``candidate`` escapes
    ``root`` (the equivalent of the inline ``relative_to`` raising ``ValueError``).
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

    Touches the filesystem: an ``lstat`` rejects symlinks *before* following
    them (a symlink whose target is benign is still refused, because the link
    itself is the attack surface), then the same metadata rejects non-regular
    files (FIFO, device, socket, directory) and anything over ``max_bytes``.

    Never raises. Any ``OSError`` (missing file, permission denied, broken
    link) is treated as "not a safe target" and returns ``False`` — callers get
    a plain bool they can branch on without a try/except.
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
