"""Selftest for the behavior-gate grader (``behavior_gate.py``).

Ported from ponytail's ``--selftest`` discipline
(``benchmarks/robustness-audit.js:1-5``, ``:168-178``, MIT © 2026
DietrichGebert): every check gets a known-good reference that MUST pass and a
known-lazy-wrong reference that MUST fail, proven **before** task 3 ever
points this grader at a real model. Runs in the default ``pytest -q`` path —
pure functions over fixture strings, no network, no API key, no model call.

Multiple references per check, not one, following ``tests/behavior.test.js``
(the upstream grader's own selftest, MIT © 2026 DietrichGebert) — it ships
two or three passing references per probe (``tests/behavior.test.js:18-31``)
rather than one. An adversarial audit of this port's first pass found that a
single good/bad pair per check leaves several inert-branch and fall-through
defects undetected (a mutant that always returns the same verdict as the
existing fall-through path survives); ``behavior_gate_fixtures.json`` now
ships one fixture per (check, id) pair, several of which are labelled
"MUTATION-KILL" in their ``note`` for exactly the branch they pin.

This is also the guard against the class of defect this proposal exists to
prevent: a grader that scores a response by grepping for the policy's own
vocabulary would score "present-but-inert" identically to "actually
followed" (the ``i-have-adhd``-named-but-uninvokable bug). See
``test_vocabulary_trap_fails_every_check`` below, which now covers both a
plain vocabulary trap and a backticked one (D1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.behavior_gate import (
    BehaviorCheck,
    BehaviorVerdict,
    UnknownBehaviorCheckError,
    grade_batch,
    grade_response,
    pass_rate,
)

_FIXTURES_PATH = Path(__file__).resolve().parent / "behavior_gate_fixtures.json"


def _load_fixtures() -> list[dict]:
    return json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))


def _check_fixtures() -> list[dict]:
    """Every (check, id) fixture entry — excludes the ``trap`` entries."""
    return [f for f in _load_fixtures() if f["check"] != "trap"]


def _trap_fixtures() -> list[dict]:
    traps = [f for f in _load_fixtures() if f["check"] == "trap"]
    assert len(traps) >= 2, (
        "expected at least a plain and a backticked trap fixture (D1)"
    )
    return traps


_CHECK_FIXTURES = _check_fixtures()
_CHECK_FIXTURE_IDS = [f"{f['check']}-{f['kind']}-{f['id']}" for f in _CHECK_FIXTURES]


# ---------------------------------------------------------------------------
# The load-bearing part: every labelled reference must grade as expected.
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("fixture", _CHECK_FIXTURES, ids=_CHECK_FIXTURE_IDS)
def test_check_reference_fixtures(fixture: dict) -> None:
    """Every labelled good fixture MUST pass its check; every labelled bad
    fixture MUST fail it. Several bad fixtures are specifically constructed
    (see their ``note``) so that disabling one discriminator branch flips
    this from red to green — that mutation resistance is the point of
    shipping more than one reference per check."""
    check = BehaviorCheck(fixture["check"])
    verdict = grade_response(fixture["response"])
    passed = verdict.passed(check)
    if fixture["kind"] == "good":
        assert passed, (
            f"{fixture['check']}/{fixture['id']}: known-good reference failed — "
            f"{verdict.reason(check)}"
        )
    else:
        assert not passed, (
            f"{fixture['check']}/{fixture['id']}: known-bad reference passed — "
            f"{verdict.reason(check)}"
        )


@pytest.mark.unit
def test_every_check_has_at_least_two_good_and_two_bad_fixtures() -> None:
    """Guards the multiple-reference discipline itself (D3): a regression
    that deletes a fixture and leaves only one good/bad pair per check
    should fail loudly here, not silently reduce coverage."""
    by_check_kind: dict[tuple[str, str], int] = {}
    for f in _CHECK_FIXTURES:
        key = (f["check"], f["kind"])
        by_check_kind[key] = by_check_kind.get(key, 0) + 1
    for check in BehaviorCheck:
        for kind in ("good", "bad"):
            count = by_check_kind.get((check.value, kind), 0)
            assert count >= 2, (
                f"{check.value}/{kind}: expected >= 2 fixtures, found {count}"
            )


@pytest.mark.unit
def test_vocabulary_trap_fails_every_check() -> None:
    """A response that TALKS about being concise/action-first while staying
    verbose and unstructured must fail every check — scoring the observable
    shape of the output, not whether it mentions the rules. Covers both the
    plain trap and a backticked variant (D1): backticking the policy's own
    vocabulary must not flip any check to PASS.
    """
    for trap in _trap_fixtures():
        verdict = grade_response(trap["response"])
        passing = [str(r.check) for r in verdict.results if r.passed]
        assert not verdict.all_passed, (
            f"trap/{trap['id']}: vocabulary-trap response unexpectedly passed: {passing!r}"
        )
        for check in BehaviorCheck:
            assert not verdict.passed(check), (
                f"trap/{trap['id']}/{check.value}: vocabulary-trap response passed — "
                f"{verdict.reason(check)}"
            )


# ---------------------------------------------------------------------------
# The bar-item cases named in the correction brief, pinned as their own
# tests so a future regression fails with an unambiguous name.
# ---------------------------------------------------------------------------


def _fixture(check: str, kind: str, fixture_id: str) -> str:
    matches = [
        f
        for f in _CHECK_FIXTURES
        if f["check"] == check and f["kind"] == kind and f["id"] == fixture_id
    ]
    assert len(matches) == 1, (
        f"expected exactly one fixture for {check}/{kind}/{fixture_id}"
    )
    return matches[0]["response"]


@pytest.mark.unit
def test_prose_only_compliant_reply_passes_all_four() -> None:
    """A genuinely compliant reply using NO code marks at all must pass
    action_first and closing_action (it previously failed 3 of 4 under the
    artifact-only design)."""
    response = (
        "Rolled back the release; traffic is on the previous build.\n\n"
        "Run the migration on the replica before promoting it."
    )
    verdict = grade_response(response)
    assert verdict.passed(BehaviorCheck.ACTION_FIRST), verdict.reason(
        BehaviorCheck.ACTION_FIRST
    )
    assert verdict.passed(BehaviorCheck.CLOSING_ACTION), verdict.reason(
        BehaviorCheck.CLOSING_ACTION
    )


@pytest.mark.unit
def test_audit_prose_only_example_passes_all_four() -> None:
    """The correction brief quotes the audit's own compliance example with
    an elision: 'Rolled back the release; traffic is on the previous
    build. ... Next: rotate the key in the ops console, then re-run the
    release job.' The '...' marks text the brief omitted for brevity, not a
    literal ellipsis in a real reply, so this reconstructs a complete,
    realistic reply around the two quoted sentences — filling the elided
    middle with a concrete quantity, since a real reply following 'prefer
    specific quantities over vague ones' would state one there. All four
    checks must pass: this is the bar item's central case, and specifically
    exercises the "next:"-marker split in ``_text_before_next_marker`` — the
    compound 'rotate X, then re-run Y' next-step chain must not be miscounted
    as unnumbered past multi-step work."""
    response = (
        "Rolled back the release; traffic is on the previous build. "
        "The outage lasted 6 minutes before the team caught it. "
        "Next: rotate the key in the ops console, then re-run the release job."
    )
    verdict = grade_response(response)
    assert verdict.all_passed, [
        (str(r.check), r.passed, r.reason) for r in verdict.results if not r.passed
    ]


@pytest.mark.unit
def test_realistic_unguided_reply_shape_fails() -> None:
    """The audit's U2 shape: chatty prose, a numbered-but-non-sequential or
    bulleted aside, and a trailing code fence — the single most common
    modern unguided-assistant shape. Must not pass closing_action (trailing
    fence) or numbered_steps (no genuine sequential structure)."""
    response = (
        "Sure, happy to help! So I dug into this a bit and here's what's going on. "
        "There are a couple of things worth calling out along the way.\n\n"
        "- looked at the config\n"
        "- looked at the cache layer\n\n"
        "```\n"
        "def maybe_fix():\n"
        "    pass\n"
        "```"
    )
    verdict = grade_response(response)
    assert not verdict.passed(BehaviorCheck.ACTION_FIRST), verdict.reason(
        BehaviorCheck.ACTION_FIRST
    )
    assert not verdict.passed(BehaviorCheck.NUMBERED_STEPS), verdict.reason(
        BehaviorCheck.NUMBERED_STEPS
    )
    assert not verdict.passed(BehaviorCheck.CLOSING_ACTION), verdict.reason(
        BehaviorCheck.CLOSING_ACTION
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "fixture_id",
    [
        "past_tense_merged",
        "past_tense_updated",
        "past_tense_fixed_upstream",
        "past_tense_reverted",
        "past_tense_deployed",
    ],
)
def test_past_tense_closing_line_fails_closing_action(fixture_id: str) -> None:
    """D-A: a closing line stating something already happened (past tense)
    must never be credited as a stated NEXT action, whatever position the
    past-tense verb appears in. This was the second audit's single
    held-out disagreement, and it was systematic across all five of these
    realistic past-tense closers."""
    response = _fixture("closing_action", "bad", fixture_id)
    verdict = grade_response(response)
    assert not verdict.passed(BehaviorCheck.CLOSING_ACTION), verdict.reason(
        BehaviorCheck.CLOSING_ACTION
    )


@pytest.mark.unit
def test_real_imperative_closer_still_passes_after_the_past_tense_fix() -> None:
    """D-A's fix must not overcorrect: a genuine imperative, prose-only
    closing line (no code marks) must still pass closing_action."""
    response = _fixture("closing_action", "good", "prose_only_action")
    verdict = grade_response(response)
    assert verdict.passed(BehaviorCheck.CLOSING_ACTION), verdict.reason(
        BehaviorCheck.CLOSING_ACTION
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "fixture_id",
    [
        "coordinated_list_split_module",
        "coordinated_list_dropped_index",
        "coordinated_list_turned_off_cron",
        "coordinated_list_wiped_cache",
    ],
)
def test_terse_multistep_reply_with_unlisted_verbs_fails_numbered_steps(
    fixture_id: str,
) -> None:
    """D-D: a terse multi-step reply built entirely from verbs outside the
    closed ``_ACTION_VERBS`` vocabulary must not vacuously pass as a single
    bounded action just because none of its verbs are recognized."""
    response = _fixture("numbered_steps", "bad", fixture_id)
    verdict = grade_response(response)
    assert not verdict.passed(BehaviorCheck.NUMBERED_STEPS), verdict.reason(
        BehaviorCheck.NUMBERED_STEPS
    )


@pytest.mark.unit
def test_documented_next_marker_coordinated_list_exception_still_passes() -> None:
    """D-D must not break the documented exception: a coordinated comma list
    INSIDE a forward-looking ``Next:`` instruction is one next-step
    instruction, not unnumbered past multi-step work, and must still pass
    numbered_steps as a vacuous single-bounded-action reply."""
    response = _fixture(
        "numbered_steps", "good", "next_marker_coordinated_list_exception"
    )
    verdict = grade_response(response)
    assert verdict.passed(BehaviorCheck.NUMBERED_STEPS), verdict.reason(
        BehaviorCheck.NUMBERED_STEPS
    )


@pytest.mark.unit
def test_blockquote_closing_line_with_next_marker_fails_closing_action() -> None:
    """D-E: the fence/blockquote guard in _check_closing_action had no
    fixture that discriminated it from the fall-through path — deleting the
    guard entirely survived the suite because the two existing fixtures also
    fail via the fall-through. A blockquote line that ALSO contains a
    'Next:' marker and an imperative verb only fails because the guard is
    active; without it, this exact input would fall through to the
    next-marker check and wrongly pass."""
    response = _fixture("closing_action", "bad", "blockquote_next_marker")
    verdict = grade_response(response)
    assert not verdict.passed(BehaviorCheck.CLOSING_ACTION), verdict.reason(
        BehaviorCheck.CLOSING_ACTION
    )


# ---------------------------------------------------------------------------
# Public-surface sanity — the shape task 3 will import and call unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_response_fails_every_check() -> None:
    verdict = grade_response("")
    assert not verdict.all_passed


@pytest.mark.unit
def test_grade_batch_preserves_order_and_count() -> None:
    good = _fixture("action_first", "good", "artifact_lead")
    bad = _fixture("action_first", "bad", "hedge")
    responses = [good, bad, ""]
    verdicts = grade_batch(responses)

    assert len(verdicts) == 3
    assert verdicts[0].passed(BehaviorCheck.ACTION_FIRST)
    assert not verdicts[1].passed(BehaviorCheck.ACTION_FIRST)
    assert not verdicts[2].passed(BehaviorCheck.ACTION_FIRST)


@pytest.mark.unit
def test_pass_rate_computes_fraction_for_arm_deltas() -> None:
    """The primitive task 3 needs to report a control-vs-guidance delta."""
    good = _fixture("action_first", "good", "artifact_lead")
    bad = _fixture("action_first", "bad", "hedge")
    verdicts = grade_batch([good, bad])

    assert pass_rate(verdicts, BehaviorCheck.ACTION_FIRST) == pytest.approx(0.5)
    assert pass_rate((), BehaviorCheck.ACTION_FIRST) == 0.0


@pytest.mark.unit
def test_check_verdict_and_behavior_verdict_to_dict_shape() -> None:
    """Exercises ``CheckVerdict.to_dict``/``BehaviorVerdict.to_dict`` — the
    wire shape task 3's report step would serialize."""
    good = _fixture("action_first", "good", "artifact_lead")
    verdict = grade_response(good)
    as_dict = verdict.to_dict()

    assert as_dict["all_passed"] is False  # only action_first is guaranteed here
    assert len(as_dict["results"]) == 4
    action_first_dict = next(
        r for r in as_dict["results"] if r["check"] == "action_first"
    )
    assert action_first_dict == {
        "check": "action_first",
        "passed": True,
        "reason": verdict.reason(BehaviorCheck.ACTION_FIRST),
    }


@pytest.mark.unit
def test_unknown_behavior_check_error_on_hand_built_verdict() -> None:
    """``UnknownBehaviorCheckError`` guards a hand-built ``BehaviorVerdict``
    that omits a check — ``grade_response`` itself always populates all
    four, per its own docstring, so this can only happen for a verdict
    assembled outside :func:`grade_response`."""
    empty_verdict = BehaviorVerdict(results=())
    with pytest.raises(UnknownBehaviorCheckError):
        empty_verdict.passed(BehaviorCheck.ACTION_FIRST)
    with pytest.raises(UnknownBehaviorCheckError):
        empty_verdict.reason(BehaviorCheck.CLOSING_ACTION)
