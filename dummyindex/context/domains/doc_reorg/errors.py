"""Typed errors for the destructive doc-reorg flow."""
from __future__ import annotations


class DocReorgError(Exception):
    """Base for every doc-reorg failure the CLI maps to an exit code."""


class DirtyTreeError(DocReorgError):
    """The working tree isn't clean (or git state is unknown) and the caller
    didn't pass ``--allow-dirty``. We refuse to edit real docs in place unless
    the changes are reversible via git."""


class BackupError(DocReorgError):
    """A backup could not be created or read (missing manifest, unreadable dir)."""
