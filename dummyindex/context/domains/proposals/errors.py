"""Typed exceptions for the `context.proposals` domain."""
from __future__ import annotations


class ProposalError(Exception):
    """Base class for every proposal-domain error."""


class ProposalExistsError(ProposalError):
    """Raised when a proposal directory already exists and `force` is False."""

    def __init__(self, slug: str, path: str) -> None:
        super().__init__(
            f"proposal {slug!r} already exists at {path} (pass force=True to overwrite)"
        )
        self.slug = slug
        self.path = path


class ProposalSlugError(ProposalError):
    """Raised when a slug is empty or unsafe as a folder name."""

    def __init__(self, slug: str, reason: str) -> None:
        super().__init__(f"invalid proposal slug {slug!r}: {reason}")
        self.slug = slug
        self.reason = reason
