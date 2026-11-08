"""Closed alphabet for the audit-debate domain.

``CouncilMode`` and ``ModelChoice`` are reused from ``context.domains.config``;
only the debate-log status alphabet and the rebuttal-round cap are local.
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
