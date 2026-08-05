"""Closed alphabet and tuning constants for the failure-miner."""

from __future__ import annotations

from enum import Enum


class LoopKind(str, Enum):
    """How a repeated-signature group was classified.

    ``ERROR_REPEAT`` — at least half the repeated calls failed (the same
    call, retried, kept failing); an even split counts, so this is not
    strictly a majority. ``OUTPUT_REPEAT`` — the calls mostly
    succeeded but were re-run anyway (e.g. re-reading a file with a wider
    window after a narrower read), the same distinction headroom's
    ``loops.py`` draws between ``error-loop`` and ``rtk-refetch-loop``
    (renamed here since dummyindex has no RTK-style output truncator).
    """

    ERROR_REPEAT = "error-repeat"
    OUTPUT_REPEAT = "output-repeat"


# Minimum repetitions of one canonical signature, within a single transcript,
# before it counts as a repeated pattern rather than a one-off retry. Mirrors
# the threshold headroom's `loops.py` settled on (a single retry is normal;
# three-or-more is a loop), reused here as a plain tuning number rather than
# copied expression.
DEFAULT_MIN_OCCURRENCES = 3

# Rough bytes-per-token used to turn a measured output size into a token
# estimate for "wasted tokens" reporting. Same order-of-magnitude heuristic
# headroom's digest builder uses; not a precise tokenizer count.
BYTES_PER_TOKEN = 4
