"""Typed exceptions for the docguard (managed-doc-home) domain."""

from __future__ import annotations


class DocGuardError(Exception):
    """Base class for every docguard-domain error."""


class DocPathError(DocGuardError):
    """Raised when a path cannot be made repo-relative (escapes ``repo_root``).

    A purely *lexical* failure (``Path.relative_to``); the classifier never touches
    the filesystem. The write-guard treats it as fail-open; a deliberate caller may
    catch it to skip + report an out-of-tree stray.
    """

    def __init__(self, path: str, root: str) -> None:
        super().__init__(f"{path!r} is not contained under repo root {root}")
        self.path = path
        self.root = root


class MigrationError(DocGuardError):
    """Base class for a stray-doc migration failure (planning or applying)."""


class MigrationContainmentError(MigrationError):
    """Raised when a source/target escapes the ``docs/`` → ``.context/`` bounds.

    ``migrate.plan_moves`` resolves symlinks on every source and target; a ``..``
    segment or an escaping symlink trips this and aborts the **whole** plan
    before any move executes.
    """

    def __init__(self, path: str, root: str) -> None:
        super().__init__(f"{path!r} escapes the managed containment under {root}")
        self.path = path
        self.root = root
