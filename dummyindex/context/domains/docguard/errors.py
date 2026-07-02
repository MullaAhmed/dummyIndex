"""Typed exceptions for the docguard (managed-doc-home) domain."""

from __future__ import annotations


class DocGuardError(Exception):
    """Base class for every docguard-domain error."""


class DocPathError(DocGuardError):
    """Raised when a path cannot be made repo-relative (escapes ``repo_root``).

    The classifier is path-based and never touches the filesystem, so this is a
    purely *lexical* containment failure (``Path.relative_to`` rejected the
    path). The write-guard treats it as fail-open; a deliberate caller may
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

    The transactional pre-validation in ``migrate.plan_moves`` resolves symlinks
    (``realpath``) on every source and target and asserts each stays inside its
    bound — sources under ``docs/`` and targets under ``.context/``. A ``..``
    segment or an escaping symlink trips this guard and aborts the **whole**
    plan before any move executes (mirrors the ``gc`` realpath containment
    guard).
    """

    def __init__(self, path: str, root: str) -> None:
        super().__init__(f"{path!r} escapes the managed containment under {root}")
        self.path = path
        self.root = root
