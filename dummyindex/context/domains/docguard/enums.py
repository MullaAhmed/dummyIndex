"""Closed alphabets for the docguard (managed-doc-home) domain."""

from __future__ import annotations

from enum import Enum


class DocKind(str, Enum):
    """Which managed home a planning doc belongs to.

    ``PROPOSAL`` routes to ``.context/proposals/<slug>/`` and ``AUDIT`` to
    ``.context/audits/<slug>/``; ``NONE`` means the path is not a planning doc
    and has no managed home. Values are wire-safe lowercase strings.
    """

    PROPOSAL = "proposal"
    AUDIT = "audit"
    NONE = "none"


class DocRole(str, Enum):
    """A planning doc's role within a ``(directory, stem)`` pair.

    ``SPEC`` is the ``<stem>-design.md`` member (relocates onto ``spec.md``);
    ``PLAN`` is the plain ``<stem>.md`` member (relocates onto ``plan.md``);
    ``NONE`` is carried by anything that is not a planning doc. The role is the
    pairing signal the grouping helper uses to merge a spec with its plan.
    """

    SPEC = "spec"
    PLAN = "plan"
    NONE = "none"
