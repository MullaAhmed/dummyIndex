"""Closed alphabets for the docguard (managed-doc-home) domain."""

from __future__ import annotations

from enum import Enum


class DocKind(str, Enum):
    """Which managed home a planning doc belongs to (``NONE``: not a planning doc).

    ``PROPOSAL`` routes to ``.context/proposals/<slug>/`` and ``AUDIT`` to
    ``.context/audits/<slug>/``.
    """

    PROPOSAL = "proposal"
    AUDIT = "audit"
    NONE = "none"


class DocRole(str, Enum):
    """A planning doc's role within a ``(directory, stem)`` pair (``NONE``: not one).

    ``SPEC`` is ``<stem>-design.md`` (→ ``spec.md``) and ``PLAN`` is ``<stem>.md``
    (→ ``plan.md``); the grouper merges a spec with its plan on this.
    """

    SPEC = "spec"
    PLAN = "plan"
    NONE = "none"
