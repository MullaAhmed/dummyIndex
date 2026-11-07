"""Compose the read-only ``gc status`` sweep into a single :class:`SweepReport`.

The domain composer behind the wire-only ``cli/gc.py``, so the CLI never carries
logic: enumerate candidates, attach each one's ``classify`` tags, and add the
commit-throttle state. Its ``should_signal`` is a pure threshold check, not
:func:`gc.should_signal`: ``gc status`` must not consume the per-session
fire-once memo (that is ``gc signal``'s job).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .anchor import anchor_orphaned, gc_commits_since, read_gc_anchor
from .constants import DEFAULT_COMMIT_THRESHOLD
from .enumerate import enumerate_candidates
from .models import SweepReport
from .signals import classify


def scan(
    context_dir: Path,
    root: Path,
    *,
    threshold: int = DEFAULT_COMMIT_THRESHOLD,
) -> SweepReport:
    """Assemble the read-only ``gc status`` payload for ``context_dir``.

    Tagged candidates plus anchor, ``commits_since``, ``threshold``,
    ``anchor_orphaned`` and ``should_signal`` (``commits_since >= threshold``),
    which never touches the memo, so repeated calls are side-effect-free.
    """
    enriched = tuple(
        replace(candidate, signals=classify(candidate, context_dir, root))
        for candidate in enumerate_candidates(context_dir)
    )

    anchor = read_gc_anchor(context_dir)
    commits = gc_commits_since(context_dir, root)
    pure_should_signal = commits is not None and commits >= threshold

    return SweepReport(
        candidates=enriched,
        anchor=anchor,
        commits_since=commits,
        threshold=threshold,
        should_signal=pure_should_signal,
        anchor_orphaned=anchor_orphaned(context_dir, root),
    )
