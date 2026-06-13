"""Shared I/O helper for domain store modules.

Kept in the `domains` package so any domain store can import without
creating cross-domain dependencies.
"""
from __future__ import annotations

from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a tmp file + ``replace`` (atomic on POSIX).

    Byte-faithful by contract: the on-disk content is exactly ``text``,
    never normalized. Equip's lifecycle hash-baselines fingerprint the
    in-memory string (``equip/lifecycle/hashing.text_hash``), so any
    silent rewrite here would make every generated artifact look
    user-edited. Callers that want pre-commit-clean output run
    :func:`normalize_eof_newline` *after* writing instead.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def normalize_eof_newline(path: Path) -> bool:
    """Ensure a non-empty file ends with exactly one ``\\n``.

    pre-commit's ``end-of-file-fixer`` rewrites files that are missing a
    final newline *or* carry surplus blank lines at EOF; generated
    ``.context/`` artifacts get committed in consumer repos, so they must
    pass it as-written. Operates on bytes (a ``\\r\\n`` final line is left
    alone) and rewrites atomically via tmp + ``replace``. Empty files are
    untouched. Returns ``True`` when the file was rewritten.
    """
    data = path.read_bytes()
    if not data:
        return False
    normalized = data.rstrip(b"\n") + b"\n"
    if normalized == data:
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(normalized)
    tmp.replace(path)
    return True
