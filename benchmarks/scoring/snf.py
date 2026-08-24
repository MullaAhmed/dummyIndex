"""Official RepoQA SNF grading rule, preserved verbatim in spirit.

RepoQA evaluates Searching-Needle-Function with a case-insensitive substring
check: the task passes iff the target function name appears anywhere in the
model's response (see evalplus/repoqa ``eval`` — "Case-insensitive substring
match for target function name"). No normalization beyond casefolding: no
fence stripping, no punctuation trimming. Keeping the rule exact is what
makes our numbers comparable with the published RepoQA leaderboard and with
competitor claims that reuse this benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnfVerdict:
    passed: bool
    needle: str


def grade_snf(response: str, needle_func: str) -> SnfVerdict:
    """Apply the official substring rule."""
    return SnfVerdict(
        passed=needle_func.lower() in response.lower(),
        needle=needle_func,
    )
