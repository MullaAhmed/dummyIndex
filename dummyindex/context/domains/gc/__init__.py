"""Context-hygiene GC: detect & delete stale/superseded/dead generated docs.

Deterministic plumbing for the ``/dummyindex-gc`` skill, which holds every judgment:
this package never reasons or deletes on its own. ``__all__`` is the CLI + skill
surface (enumerate, classify, anchor/throttle, scan, guarded delete), including the
- ``DEFAULT_COMMIT_THRESHOLD``, ``ARCHIVE_SENTINEL``, ``GC_STATE_REL``,
  ``GC_MEMO_REL``, ``PROPOSALS_REL``, ``AUDITS_REL`` layout constants.
"""

from __future__ import annotations

from .anchor import (
    anchor_orphaned,
    gc_commits_since,
    read_gc_anchor,
    should_signal,
    stamp_gc,
    write_gc_anchor,
)
from .constants import (
    ARCHIVE_SENTINEL,
    AUDITS_REL,
    DEFAULT_COMMIT_THRESHOLD,
    GC_MEMO_REL,
    GC_STATE_REL,
    PROPOSALS_REL,
)
from .delete import delete_workspace
from .enumerate import enumerate_candidates
from .enums import CandidateKind, Disposition
from .errors import GcError, GcPathError, GcTargetError
from .models import Candidate, DeleteResult, SweepReport
from .scan import scan
from .signals import classify

__all__ = [
    "ARCHIVE_SENTINEL",
    "AUDITS_REL",
    "DEFAULT_COMMIT_THRESHOLD",
    "GC_MEMO_REL",
    "GC_STATE_REL",
    "PROPOSALS_REL",
    "Candidate",
    "CandidateKind",
    "DeleteResult",
    "Disposition",
    "GcError",
    "GcPathError",
    "GcTargetError",
    "SweepReport",
    "anchor_orphaned",
    "classify",
    "delete_workspace",
    "enumerate_candidates",
    "gc_commits_since",
    "read_gc_anchor",
    "scan",
    "should_signal",
    "stamp_gc",
    "write_gc_anchor",
]
