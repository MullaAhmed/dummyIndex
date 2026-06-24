"""Package-private constants for the context-hygiene GC domain.

Tunables and fixed rel-paths that are not closed-alphabet enums. The
generated-doc roots are *reused* from the domains that own them
(``proposals``/``audit``) rather than re-declaring the string literals —
there must be a single source of truth for "where proposals/audits live".
They are re-exported here under the same names so this module stays
self-describing as the GC layout reference.
"""

from __future__ import annotations

from ..audit.workspace import AUDITS_REL
from ..proposals.store import PROPOSALS_REL

__all__ = [
    "ARCHIVE_SENTINEL",
    "AUDITS_REL",
    "DEFAULT_COMMIT_THRESHOLD",
    "GC_MEMO_REL",
    "GC_STATE_REL",
    "PROPOSALS_REL",
]

# Commit-count throttle: the SessionStart nudge fires once at least this many
# commits have landed since the last GC anchor (spec: commit-count, not cron).
DEFAULT_COMMIT_THRESHOLD = 10

# Sentinel container under the generated-doc roots: a leading-underscore entry
# (the legacy ``proposals/_archive/``) is never itself a delete target, though
# its *children* surface as ``ARCHIVED`` candidates.
ARCHIVE_SENTINEL = "_archive"

# Committed GC anchor, relative to ``.context/``: holds ONLY the commit sha the
# last sweep stamped (``{"anchor": sha}``). A new committed ``.context/``
# artifact; lives apart from reconcile's ``meta.indexed_commit``.
GC_STATE_REL = "gc/state.json"

# Gitignored per-session fire-once memo, relative to ``.context/``: keyed by
# session id so a SessionStart nudge is emitted at most once per session.
# Distinct from the committed anchor above.
GC_MEMO_REL = "cache/gc-nudge-state.json"
