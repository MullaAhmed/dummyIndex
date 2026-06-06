"""Never-clobber guard for equip's writes into ``.claude/``.

The one rule equip must never break: **never overwrite a user-authored file**.
:func:`is_safe_to_write` returns True only when the target is absent, or present
but carrying our :data:`GENERATED_SENTINEL` (so regenerating our own output is
fine). Any other existing file — a hand-written agent, a foreign skill — is
off-limits and the caller skips it (and reports the skip). The on-disk content
is the authoritative ownership signal; for targets already recorded in the
manifest, the hash-based :func:`.lifecycle.classify_item` is the gate instead.
"""
from __future__ import annotations

from pathlib import Path

from .models import GENERATED_SENTINEL


def is_safe_to_write(path: Path) -> bool:
    """True when writing ``path`` cannot clobber a user file.

    - Absent path → safe (nothing to clobber).
    - Present + carries our sentinel → safe (ours to regenerate).
    - Present + no sentinel → unsafe (a user file; skip it).
    """
    if not path.exists():
        return True
    if not path.is_file():
        return False  # a directory at the target path — never touch it
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False  # can't verify ownership → treat as a user file, skip
    return GENERATED_SENTINEL in content
