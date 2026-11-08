"""Repo-level style ratchet and policy-text lint."""

from __future__ import annotations

import pytest

from dummyindex.context.domains import docbudget
from dummyindex.context.domains.docbudget.constants import STYLE_RATCHET_REL
from dummyindex.context.output.bootstrap import (
    ALWAYS_ON_OUTPUT_POLICY,
    ALWAYS_ON_TURN_REMINDER,
)
from dummyindex.context.output.instructions import generate_how_to_use_md
from tests.paths import REPO_ROOT

_STYLE_RATCHET = REPO_ROOT / STYLE_RATCHET_REL


@pytest.mark.unit
def test_style_ratchet_exists_and_passes() -> None:
    assert _STYLE_RATCHET.is_file(), f"{STYLE_RATCHET_REL} is missing"
    ratchet = docbudget.read_ratchet(_STYLE_RATCHET)
    violations = docbudget.check(REPO_ROOT, ratchet, docbudget.BudgetGroup.STYLE)
    assert not violations, (
        "doc(s) gained style violations: "
        f"{[(v.path, v.words, v.limit) for v in violations]}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [ALWAYS_ON_OUTPUT_POLICY, ALWAYS_ON_TURN_REMINDER, generate_how_to_use_md()],
    ids=["output-policy", "turn-reminder", "how-to-use"],
)
def test_policy_and_how_to_use_pass_style_lint(text: str) -> None:
    assert docbudget.lint_text(text) == ()
