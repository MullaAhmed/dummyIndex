"""Closed alphabet for the audit-debate domain.

The audit feature reuses the council's effort dial (``CouncilMode``) and the
model alphabet (``ModelChoice``) from ``context.domains.config`` — they mean the
same thing here, so they are not re-declared. What is local to audit is the
debate-log status alphabet and the hard cap on rebuttal rounds.
"""

from __future__ import annotations

from enum import Enum

# Hard ceiling on rebuttal rounds. Round 0 is the independent-findings pass;
# rounds 1..MAX_REBUTTAL_ROUNDS are the argue/rebuttal passes. The skill stops
# *earlier* the moment the panel reaches agreement (a round that changes no
# finding's status) — this constant is only the cap it may never exceed.
MAX_REBUTTAL_ROUNDS = 3


class LogStatus(str, Enum):
    """Per-(round, persona) work status in the debate resumption log.

    Mirrors the council log's alphabet so a resumed audit can tell which
    rounds already ran. ``skipped`` covers a persona dropped from a later
    round once it has conceded.
    """

    STARTED = "started"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"
