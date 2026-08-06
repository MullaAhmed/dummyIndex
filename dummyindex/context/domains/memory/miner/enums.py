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


class SkillDirectiveKind(str, Enum):
    """The two state transitions recognized from an external human prompt."""

    CORRECTION = "correction"
    REVOCATION = "revocation"


# Minimum repetitions of one canonical signature, within a single transcript,
# before it counts as a repeated pattern rather than a one-off retry. Mirrors
# the threshold headroom's `loops.py` settled on (a single retry is normal;
# three-or-more is a loop), reused here as a plain tuning number rather than
# copied expression.
DEFAULT_MIN_OCCURRENCES = 3

# A single request is ordinary task input; two distinct human events establish
# the recurring-compliance signal that is safe to persist.
DEFAULT_MIN_SKILL_CORRECTIONS = 2

# Safe slug bound used by both transcript parsing and prompt-context rendering.
MAX_SKILL_SLUG_CHARS = 64

# Rough bytes-per-token used to turn a measured output size into a token
# estimate for "wasted tokens" reporting. Same order-of-magnitude heuristic
# headroom's digest builder uses; not a precise tokenizer count.
BYTES_PER_TOKEN = 4
