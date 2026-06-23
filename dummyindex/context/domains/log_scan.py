"""Shared log-scan helper for domain resumption logs.

Kept in the ``domains`` package so any domain log module can import it
without creating cross-domain dependencies — the same sanctioned
shared-domain-helper shape that :mod:`context.domains.atomic_io` sets
(``conventions/folder-organization.md`` §"How a domain directory is split":
a domain-neutral peer that a sibling domain with the same need would want
is cross-cutting and lives top-level, not inside one domain).

The helper is **pure**: it takes the already-read entries and a predicate,
takes no domain object, and reaches into no domain's internals.
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

    Scans ``entries`` in order and keeps the matching entry seen most recently,
    so a later append wins over an earlier one for the same key — the exact
    "keep the last entry matching a (key, agent) pair, return its status"
    semantics both the council and audit resumption logs rely on. Returns
    ``None`` when no entry matches (including an empty iterable).
    """
    found: str | None = None
    for entry in entries:
        if predicate(entry):
            found = getattr(entry, attr)
    return found
