"""Closed alphabet and tuning constants for the failure-miner."""

from __future__ import annotations

from enum import Enum


class LoopKind(str, Enum):
    """How a repeated-signature group was classified.

    ``ERROR_REPEAT``: at least half the calls failed (an even split counts).
    ``OUTPUT_REPEAT``: the calls mostly succeeded but were re-run, e.g. a wider
    re-read. Mirrors headroom's ``error-loop`` / ``rtk-refetch-loop`` split.
    """

    ERROR_REPEAT = "error-repeat"
    OUTPUT_REPEAT = "output-repeat"


class SkillDirectiveKind(str, Enum):
    """The two state transitions recognized from an external human prompt."""

    CORRECTION = "correction"
    REVOCATION = "revocation"


# Repeats of one signature within one transcript before it counts as a pattern:
# one retry is normal, three or more is a loop (headroom's `loops.py` threshold).
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
