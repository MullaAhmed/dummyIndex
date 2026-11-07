"""Shared I/O helper for domain store modules.

Kept in the `domains` package so any domain store can import without
creating cross-domain dependencies.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from tempfile import NamedTemporaryFile


def is_link(path: Path) -> bool:
    """``True`` when ``path`` is a symlink or reparse point (fail-closed).

    Uses ``os.lstat`` so the link itself is inspected, never its target. A Windows
    junction is not ``S_ISLNK`` but carries ``FILE_ATTRIBUTE_REPARSE_POINT`` (read
    via ``getattr`` so py3.10 / POSIX hosts without it stay safe). A missing path
    is ``False``; any other ``OSError`` counts as linked, so a caller that would
    delete or descend into ``path`` declines instead of guessing.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _replace_bytes(path: Path, data: bytes) -> None:
    """Replace ``path`` from a unique temporary sibling.

    The temporary name must be unique because hooks from two Claude profiles
    can update the same repo-local cache concurrently.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(data)
        for attempt in range(6):
            try:
                tmp_path.replace(path)
                break
            except PermissionError:
                # Windows readers can briefly deny replacement while their
                # handle is open. Retain the complete temporary until retry.
                if os.name != "nt" or attempt == 5:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a tmp file + ``replace`` (atomic on POSIX).

    Byte-faithful by contract: the on-disk content is exactly ``text``, never
    normalized. Equip's hash-baselines fingerprint the in-memory string
    (``equip/lifecycle/hashing.text_hash``), so a silent rewrite would make every
    generated artifact look user-edited. For pre-commit-clean output, run
    :func:`normalize_eof_newline` *after* writing.
    """
    _replace_bytes(path, text.encode("utf-8"))


def normalize_eof_newline(path: Path) -> bool:
    """Ensure a non-empty file ends with exactly one ``\\n``; ``True`` if rewritten.

    Generated ``.context/`` artifacts are committed in consumer repos, so they must
    pass pre-commit's ``end-of-file-fixer`` (no missing final newline, no surplus
    EOF blank lines) as written. Works on bytes (a ``\\r\\n`` ending is kept) and
    rewrites atomically via tmp + ``replace``. Empty files are untouched.
    """
    data = path.read_bytes()
    if not data:
        return False
    ending = b"\r\n" if data.endswith(b"\r\n") else b"\n"
    normalized = data.rstrip(b"\r\n") + ending
    if normalized == data:
        return False
    _replace_bytes(path, normalized)
    return True
