"""Compose the read-only ``gc status`` sweep into a single :class:`SweepReport`.

This is the thin domain composer the wire-only ``cli/gc.py`` calls so the CLI
never carries logic (``conventions/folder-organization.md`` — ``cli/<sub>.py`` is
parse-argv / hand-off / print only). ``scan`` stitches the existing domain pieces
together:

1. ``enumerate_candidates`` — the generated-doc workspaces under
   ``proposals/`` + ``audits/``.
2. ``classify`` — the deterministic signal tags for each candidate (enriched
   onto each :class:`Candidate` via :func:`dataclasses.replace`, since the
   frozen dataclass is never mutated).
3. ``read_gc_anchor`` / ``gc_commits_since`` / ``anchor_orphaned`` — the
   committed commit-throttle state.

The ``should_signal`` reported here is a **pure threshold check** —
``commits_since is not None and commits_since >= threshold`` — and deliberately
NOT a call to :func:`gc.should_signal`: ``gc status`` is read-only and must not
consume the per-session fire-once memo (that is ``gc signal``'s job). No
``print`` here — the CLI owns stdout.
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

    Enumerates every generated-doc candidate, enriches each with its signal
    tags, and folds in the commit-throttle state (anchor, ``commits_since``,
    ``threshold``, a pure-threshold ``should_signal``, and ``anchor_orphaned``).

    ``should_signal`` is a *pure* threshold predicate
    (``commits_since >= threshold``); it never touches the per-session memo, so
    repeated ``scan`` calls are side-effect-free and idempotent.
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
