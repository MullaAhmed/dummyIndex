"""Data types for the link package: the classification alphabet + result records.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..common import LinkMode

# ----- FamilyLinkState ----------------------------------------------------------


class FamilyLinkState(str, Enum):
    """Closed classification alphabet for one family's `.claude` side.

    Rendered as its value (``"not_a_link"``, not ``FamilyLinkState.NOT_A_LINK``)
    like every other closed-alphabet enum in this codebase (see
    ``common.py``'s ``LinkMode``).
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
    #: Everything else: a disallowed symlink anywhere in the parent chain, a
    #: link with an unexpected value/absolute-and-wrong target, an
    #: unresolvable/un-owned target, a symlink loop, or any
    #: `OSError`/`RuntimeError` raised while classifying (fail closed). Never
    #: written, never removed.
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
    are ``"<family>: <reason>"`` lines, ready to print — mirroring the
    ``describe_plan`` line-formatting precedent in ``repair.py`` rather than
    forcing a caller to re-parse structured records it doesn't otherwise
    need. A family already `OURS_HEALTHY` in its canonical relative form is
    counted in **neither** ``created`` nor ``replaced`` (idempotent no-op).
    """

    created: tuple[str, ...]
    replaced: tuple[str, ...]
    skipped: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _FamilyOutcome:
    kind: str  # "created" | "replaced" | "skipped" | "error" | "noop"
    detail: str = ""
    #: A SECONDARY, non-fatal notice riding along with `kind` — used when
    #: the primary operation succeeded (or needed nothing) but a leftover
    #: `tmp_old` from an earlier or this-very run's own cleanup survives and
    #: must still be named (NEW-1). `create_family_links` appends this, when
    #: non-empty, as an EXTRA `<family>: <warning>` line in `skipped` —
    #: alongside whatever bucket `kind` itself lands in, never replacing it.
    warning: str = ""


class _CapabilityFailure(Exception):
    """Raised internally when `symlink_fn` fails in an EPERM/winerror shape.

    Caught by `create_family_links`'s loop to abort every remaining family
    while keeping every family already created/replaced this run.
    """


# ----- AUTO/LINK/COPY orchestration ---------------------------------------------


class LinkCapabilityError(Exception):
    """Raised by `run_link_install` under strict `LinkMode.LINK` when the
    one-time symlink capability probe fails. The caller (install.py, Wave 3)
    is expected to print the message and exit 1."""


@dataclass(frozen=True)
class LinkInstallResult:
    """Outcome of one `run_link_install` dispatch call.

    ``effective_link_mode`` is the mode actually used this run for the
    Claude side — it differs from the caller's requested ``link_mode`` only
    for `LinkMode.AUTO`, which downgrades to `LinkMode.COPY` for the WHOLE
    run when the capability pre-probe fails. ``link_result`` is ``None``
    exactly when `create_family_links` was never called this run (a plain
    `LinkMode.COPY` request, or an AUTO probe fallback) — Wave 3's
    `install.py` uses that ``None``-ness, together with the DI/spy seam this
    function's own ``symlink_fn`` parameter threads through to
    `create_family_links`, as its single "did link.py touch anything"
    signal (the ``--copy`` characterization test spies on exactly this).
    """

    effective_link_mode: LinkMode
    link_result: LinkResult | None
    fell_back_to_copy: bool
    warnings: tuple[str, ...]
