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
    assert [v for v in docbudget.lint_text(text) if v.severity == "strict"] == []


@pytest.mark.unit
def test_style_scope_globs_and_exemptions(tmp_path) -> None:
    bad = "It's ready.\n"
    for rel in (
        ".context/features/a/flows/f.md",
        ".context/playbooks/p.md",
        ".context/proposals/x/spec.md",
        ".context/audits/y/z/a.md",
        ".context/HOW_TO_USE.md",
        ".context/INDEX.md",
        ".context/conventions/naming.md",
        ".context/equipment/e.md",
        ".context/session-memory/s.md",
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(bad, encoding="utf-8")
    found = docbudget.scan(tmp_path, docbudget.BudgetGroup.STYLE)
    assert sorted(found) == [
        ".context/audits/y/z/a.md",
        ".context/features/a/flows/f.md",
        ".context/playbooks/p.md",
        ".context/proposals/x/spec.md",
    ]


@pytest.mark.unit
def test_reseed_stale_style_rewrites_header_once(tmp_path) -> None:
    from dummyindex.context.domains.docbudget import reseed_stale_style

    doc = tmp_path / ".context/conventions/a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("It's ready.\n", encoding="utf-8")
    ratchet = tmp_path / ".context/style-budget.txt"
    ratchet.write_text(".context/conventions/a.md\t0\n", encoding="utf-8")
    assert reseed_stale_style(tmp_path, ratchet) is True
    assert ratchet.read_text(encoding="utf-8") == (
        "# ruleset 1\n.context/conventions/a.md\t1\n"
    )
    assert reseed_stale_style(tmp_path, ratchet) is False
