"""Data types for the link package: the classification alphabet + result records.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..common import LinkMode

# --- FamilyLinkState


class FamilyLinkState(str, Enum):
    """Closed classification alphabet for one family's `.claude` side.

    Renders as its value (``"not_a_link"``), like ``common.py``'s ``LinkMode``.
    """

    #: A real directory (or a regular file that is not a materialized link).
    NOT_A_LINK = "not_a_link"
    #: Our own symlink: correct value, clean parent chain, owned target.
    OURS_HEALTHY = "ours_healthy"
    #: Our own symlink, clean parent chain, target positively confirmed
    #: absent (never merely "unstatable for some other reason").
    OURS_DANGLING = "ours_dangling"
    #: A regular file whose exact content equals `relative_link_value()` —
    #: the `core.symlinks=false` Windows checkout shape. Content is the
    #: ownership proof.
    MATERIALIZED = "materialized"
    #: Path does not exist at all. Safe to create into with no ownership
    #: evidence needed; also the crash-recovery state.
    MISSING = "missing"
    #: Everything else: a disallowed parent-chain symlink, an unexpected or wrong
    #: link value, an unresolvable/un-owned target, a symlink loop, or any
    #: `OSError`/`RuntimeError` while classifying (fail closed). Never written,
    #: never removed.
    FOREIGN = "foreign"

    __str__ = str.__str__


@dataclass(frozen=True)
class FamilyLinkClassification:
    """One family's classification result at one scope root."""

    family: str
    path: Path
    state: FamilyLinkState
    detail: str


@dataclass(frozen=True)
class LinkResult:
    """Outcome of one `create_family_links` run, tuple fields throughout.

    ``created`` / ``replaced`` are bare family names. ``skipped`` / ``errors``
    are ready-to-print ``"<family>: <reason>"`` lines. A family already
    `OURS_HEALTHY` in canonical relative form is in neither ``created`` nor
    ``replaced`` (idempotent no-op).
    """

    created: tuple[str, ...]
    replaced: tuple[str, ...]
    skipped: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _FamilyOutcome:
    kind: str  # "created" | "replaced" | "skipped" | "error" | "noop"
    detail: str = ""
    #: Secondary, non-fatal notice: a surviving `tmp_old` leftover that must still
    #: be named although `kind` succeeded (or was a no-op). `create_family_links`
    #: adds it as an extra `<family>: <warning>` line in `skipped`, alongside
    #: whatever bucket `kind` lands in.
    warning: str = ""


class _CapabilityFailure(Exception):
    """Raised internally when `symlink_fn` fails in an EPERM/winerror shape.

    Caught by `create_family_links`'s loop to abort every remaining family
    while keeping every family already created/replaced this run.
    """


# --- AUTO/LINK/COPY orchestration


class LinkCapabilityError(Exception):
    """Raised by `run_link_install` under strict `LinkMode.LINK` when the
    symlink capability probe fails. The caller prints it and exits 1."""


@dataclass(frozen=True)
class LinkInstallResult:
    """Outcome of one `run_link_install` dispatch call.

    ``effective_link_mode`` is the Claude-side mode actually used; it differs
    from the requested mode only when an AUTO probe fails and it reports
    `LinkMode.COPY` (the installer then prepares thin references).
    ``link_result`` is ``None`` exactly when `create_family_links` was not
    called (a COPY request, or an AUTO probe fallback).
    """

    effective_link_mode: LinkMode
    link_result: LinkResult | None
    fell_back_to_copy: bool
    warnings: tuple[str, ...]
