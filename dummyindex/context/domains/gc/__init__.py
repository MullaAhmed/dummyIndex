"""Context-hygiene GC: detect & delete stale/superseded/dead generated docs.

Deterministic plumbing for the commit-throttled hygiene sweep — enumerate
generated-doc candidates, gather objective signals, throttle the SessionStart
nudge against a committed commit anchor, and execute bounded, guarded deletions
of whole doc workspaces. The LLM council judgment lives in the
``/dummyindex-gc`` skill; this package never reasons or deletes on its own.

Public surface (the CLI + skill import target):

- ``Disposition``, ``CandidateKind`` — closed alphabets
- ``Candidate``, ``SweepReport``, ``DeleteResult`` — frozen dataclasses
- ``GcError``, ``GcPathError``, ``GcTargetError`` — typed errors
- ``DEFAULT_COMMIT_THRESHOLD``, ``ARCHIVE_SENTINEL``, ``GC_STATE_REL``,
  ``GC_MEMO_REL``, ``PROPOSALS_REL``, ``AUDITS_REL`` — layout constants
- ``enumerate_candidates``, ``classify`` — candidate discovery + signal tags
- ``read_gc_anchor``, ``write_gc_anchor``, ``gc_commits_since``,
  ``anchor_orphaned``, ``should_signal``, ``stamp_gc`` — anchor + throttle
- ``scan`` — the read-only ``gc status`` composer (enumerate + classify + throttle)
- ``delete_workspace`` — the bounded destructive op
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
