"""Typed exceptions for the context-hygiene GC domain."""

from __future__ import annotations


class GcError(Exception):
    """Base class for every GC-domain error."""


class GcPathError(GcError):
    """Raised when a delete target's realpath escapes the generated-doc root.

    Reachable only via ``--path`` (or a symlinked workspace); a ``--slug`` is
    charset-validated upstream so it can never resolve outside the root.
    """

    def __init__(self, path: str, root: str) -> None:
        super().__init__(f"refusing to delete {path!r}: resolves outside root {root}")
        self.path = path
        self.root = root


class GcTargetError(GcError):
    """Raised when a delete target is missing, ambiguous, or a sentinel.

    Covers the sentinel-reject guard (``_archive``, a leading-underscore slug,
    ``.``/``..``, or empty) and an ambiguous / unresolvable target request.
    """

    def __init__(self, target: str, reason: str) -> None:
        super().__init__(f"invalid GC target {target!r}: {reason}")
        self.target = target
        self.reason = reason
