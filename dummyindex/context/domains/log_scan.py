"""Shared log-scan helper for domain resumption logs.

Top-level in ``domains`` (like :mod:`context.domains.atomic_io`) so any domain log
module can import it without cross-domain dependencies. Pure: it takes read
entries and a predicate, never a domain object.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")


def last_matching(
    entries: Iterable[T],
    predicate: Callable[[T], bool],
    attr: str = "status",
) -> str | None:
    """Return ``getattr(entry, attr)`` of the *last* entry satisfying ``predicate``.

    A later append wins over an earlier one for the same key — the semantics
    both the council and audit resumption logs rely on. ``None`` when no entry
    matches (including an empty iterable).
    """
    found: str | None = None
    for entry in entries:
        if predicate(entry):
            found = getattr(entry, attr)
    return found
