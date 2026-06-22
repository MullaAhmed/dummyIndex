"""Typed exceptions for the ``context.audit`` domain."""
from __future__ import annotations


class AuditError(Exception):
    """Base class for every audit-domain error."""


class AuditSlugError(AuditError):
    """Raised when a slug is empty or unsafe as a folder name."""

    def __init__(self, slug: str, reason: str) -> None:
        super().__init__(f"invalid audit slug {slug!r}: {reason}")
        self.slug = slug
        self.reason = reason


class AuditExistsError(AuditError):
    """Raised when an audit directory already exists and ``force`` is False."""

    def __init__(self, slug: str, path: str) -> None:
        super().__init__(
            f"audit {slug!r} already exists at {path} (pass --force to overwrite)"
        )
        self.slug = slug
        self.path = path


class AuditNotFoundError(AuditError):
    """Raised when an audit workspace cannot be found for a slug."""

    def __init__(self, slug: str, path: str) -> None:
        super().__init__(f"audit {slug!r} not found at {path}")
        self.slug = slug
        self.path = path


class ModelRequiredError(AuditError):
    """No ``--model`` given and no ``.context/config.json`` to fall back on.

    The model is **never** silently defaulted — the user must choose one, or
    persist a choice via ``dummyindex context onboard``.
    """

    def __init__(self) -> None:
        super().__init__(
            "a model is required: pass --model opus-4.8|sonnet-4.6|haiku-4.5 "
            "(or run `dummyindex context onboard` to persist a choice). "
            "The model is never silently defaulted."
        )


class AuditLogError(AuditError):
    """Invalid status / round / persona for a debate-log append."""
