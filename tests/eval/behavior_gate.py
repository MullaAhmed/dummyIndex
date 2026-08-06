"""Deterministic behavior-gate grader over ``ALWAYS_ON_OUTPUT_POLICY``.

This is the spec's Item 1 (ADOPT) and Item 3 (ADAPT):
`.context/proposals/repo-adoptions-ponytail-headroom/spec.md`. Ported from
``DietrichGebert/ponytail`` (MIT, © 2026 DietrichGebert), following the credit
idiom at ``tests/eval/test_retrieval_eval.py:11``:

- The **check-per-rule, regex/structure heuristic, never an LLM judge** shape
  mirrors ponytail's ``CHECKS`` dispatch table and
  ``module.exports(output, context)`` (``benchmarks/behavior.js:17-54``).
  ``behavior.js`` dispatches to exactly *one* check per call, keyed by
  ``context.vars.probe``; this port instead runs all four checks on every
  response (:func:`grade_response`) and lets the caller — the two-arm harness
  in task 3 — pick which :class:`BehaviorCheck` is relevant for a given probe.
- The **known-good / known-lazy-wrong selftest discipline** — "prove every
  check is correct before any paid run" — mirrors
  ``benchmarks/robustness-audit.js``'s ``--selftest`` flag (``:1-5``,
  ``:168-178``): every check gets a reference response that MUST pass and one
  that MUST fail. Proven in ``test_behavior_gate.py``.
- The **multiple-reference discipline** — more than one good/bad pair per
  check, each chosen to exercise one branch of the checker — mirrors
  ``tests/behavior.test.js`` (the upstream grader's own selftest), which ships
  two or three passing references per probe (e.g. ``hardware``'s "calibration
  knob" case and its independent "tuning knobs / reads off" case,
  ``tests/behavior.test.js:18-31``) rather than one. An adversarial audit of
  this port's first pass found that a single good/bad pair per check leaves
  several inert or fall-through code paths undetected; ``behavior_gate_fixtures.json``
  now ships multiple labelled references per check for exactly that reason.

This module is **pure**: no network, no API key, no model call — a grader
over a plain ``str``. It scores the OBSERVABLE SHAPE of a response (does the
first line lead with a concrete artifact or a stated outcome/action, are
multi-step items numbered sequentially, are quantities specific and not
outweighed by vague ones, does the response close on a stated next action) —
never whether the response *talks about* following the rules. A reply that
recites "I'll be concise" while staying vague, unstructured, and open-ended
must fail every check, WHETHER OR NOT it backticks the policy's own
vocabulary while doing so; see the ``trap`` and ``trap_backticked`` fixtures
in ``behavior_gate_fixtures.json``.

The subject under test is
``dummyindex.context.output.bootstrap.ALWAYS_ON_OUTPUT_POLICY``
(``dummyindex/context/output/bootstrap.py:32-52``). Task 3 (the two-arm
model-dependent run) imports :func:`grade_response`, :func:`grade_batch`, and
:func:`pass_rate` from this module unchanged.

**``action_first`` is lead-only, by design.** It grades only the first
non-blank line. A reply whose first line names a real path or leads with a
stated outcome/action, but whose *body* is otherwise hedging, vague, and
unstructured, still passes ``action_first`` — the check does not re-inspect
the rest of the response (``numbered_steps``, ``specific_quantities``, and
``closing_action`` cover the rest of the shape independently). Task 3 should
read a small control-arm ``action_first`` pass rate as this lead-only design,
not as noise or a check that is inert.

**Fence-stripped vs. raw input, by design (not an oversight).** Only
``_check_numbered_steps`` (via :func:`_is_single_bounded_action`) runs on
fence-stripped text (:func:`_strip_fenced_code`) — pasted code must not
smuggle in a bogus numbered/bulleted sequence or inflate the action-verb
count. ``_check_specific_quantities`` and ``_check_closing_action`` run on
the raw response: a specific quantity or a closing action can legitimately
appear inside a backticked command (see the ``marker_and_artifact`` fixture),
and stripping fences there would throw away real signal for no benefit.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


class BehaviorGateError(Exception):
    """Base exception for the behavior-gate grader."""


class UnknownBehaviorCheckError(BehaviorGateError):
    """Raised when a :class:`BehaviorVerdict` has no recorded result for a
    requested :class:`BehaviorCheck` (should not happen via :func:`grade_response`,
    which always populates all four — guards hand-built verdicts)."""


class BehaviorCheck(str, Enum):
    """The four observable-shape rules probed from ``ALWAYS_ON_OUTPUT_POLICY``.

    ``dummyindex/context/output/bootstrap.py:32-52`` states these as prose;
    each member here is the one regex/structure heuristic that checks whether
    a response's *shape* actually exhibits the rule.
    """

    ACTION_FIRST = "action_first"
    NUMBERED_STEPS = "numbered_steps"
    SPECIFIC_QUANTITIES = "specific_quantities"
    CLOSING_ACTION = "closing_action"

    # Render as the value ("action_first"), never the enum repr, matching
    # dummyindex.context.enums.DocConfidence's __str__ pin.
    __str__ = str.__str__


@dataclass(frozen=True)
class CheckVerdict:
    """One check's pass/fail outcome for a single response."""

    check: BehaviorCheck
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"check": str(self.check), "passed": self.passed, "reason": self.reason}


@dataclass(frozen=True)
class BehaviorVerdict:
    """All four :class:`CheckVerdict` results for one graded response."""

    results: tuple[CheckVerdict, ...]

    def passed(self, check: BehaviorCheck) -> bool:
        for result in self.results:
            if result.check == check:
                return result.passed
        raise UnknownBehaviorCheckError(f"no verdict recorded for check {check!r}")

    def reason(self, check: BehaviorCheck) -> str:
        for result in self.results:
            if result.check == check:
                return result.reason
        raise UnknownBehaviorCheckError(f"no verdict recorded for check {check!r}")

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "all_passed": self.all_passed,
        }


# ---------------------------------------------------------------------------
# Shared shape primitives.
# ---------------------------------------------------------------------------


def _first_nonblank_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _last_nonblank_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _strip_fenced_code(text: str) -> str:
    """Blank out fenced code regions so list/step counting never credits a
    pasted file listing, a bibliography, or lorem ipsum inside a code block
    (D5: ``_check_numbered_steps`` used to count numbered lines anywhere,
    fenced or not)."""
    return _FENCE_RE.sub(" ", text)


# A "concrete artifact" is a line that names something real and checkable —
# a file:line reference, a path with an extension, a bare dot-extension
# token (``bootstrap.py``), or a shell-prompt-led command. Deliberately
# NOT "any backticked span" (D1) and NOT "any line opening with `> `"
# (D7) — a bare backtick around a policy word, and a markdown blockquote,
# are both far more common than a real artifact and must not qualify.
_FILE_LINE_RE = re.compile(r"[\w./-]+\.\w{1,10}:\d+")
_PATH_RE = re.compile(r"\b[\w-]+(?:/[\w.-]+)+\.\w{1,10}\b")
# A bare dot-extension token, e.g. "pyproject.toml" or "app.py", with no
# slash. The real exclusions, corrected: it is NOT the extension's "{2,10}"
# lower bound doing this work (a previous version of this comment wrongly
# credited it). "e.g."/"i.e." are excluded by the "[\w-]{2,}" PREFIX bound —
# the "e"/"i" before each dot is only one character, short of the required
# two. "3.5" is excluded twice over: "3" also fails that same one-character
# prefix bound, and independently its "5" fails the letters-only
# "[A-Za-z]{2,10}" extension class (a digit is not a letter at all,
# regardless of count). A sentence-ending period followed by a capitalized
# word ("...done. Next steps...") is excluded because the extension class
# must immediately follow the dot with no space — the space after a real
# sentence-final period means no candidate extension ever starts there.
_DOT_EXT_RE = re.compile(r"\b[\w-]{2,}\.[A-Za-z]{2,10}\b")


def _has_concrete_artifact(line: str) -> bool:
    return bool(
        _FILE_LINE_RE.search(line)
        or _PATH_RE.search(line)
        or _DOT_EXT_RE.search(line)
        or line.startswith("$ ")
    )


# A shared action-verb vocabulary used by both the action-first (past-tense/
# imperative lead) and closing-action (imperative next step only, see D-A
# below) checks. Split by tense — not one flat list — because the two checks
# need different tenses: action_first's lead may legitimately state either
# what already happened ("Rolled back...") or what's next ("Run..."), but
# closing_action must credit only a NEXT action, never a recap of one already
# done. Past-tense forms are added only to the past set, imperative forms
# only to the imperative set; ``_ACTION_VERBS``/``_ACTION_ANYWHERE_RE`` (both
# tenses combined) stay the shared vocabulary for action_first and for
# counting "how many actions does this describe" in
# :func:`_is_single_bounded_action`.
_ACTION_VERBS_PAST = (
    r"ran|rolled back|rolled|fixed|patched|added|removed|refactored|deployed|"
    r"migrated|updated|reverted|restarted|merged|rebased|tagged|pushed|"
    r"bumped|regenerated|renamed|replaced|resolved|closed|opened|"
    r"implemented|wired|gated|extracted|inlined|wrote|tested|verified|"
    r"confirmed|reviewed|checked|installed|configured|built|created|"
    r"deleted|disabled|enabled|restored|rebuilt"
)
_ACTION_VERBS_IMPERATIVE = (
    r"run|check|verify|deploy|merge|rebase|restart|rotate|revert|patch|"
    r"update|install|configure|retry|apply|migrate|promote|redeploy|"
    r"validate|inspect|investigate|rebuild|regenerate|rename|schedule|"
    r"re-run|rerun|roll back|rollback"
)
_ACTION_VERBS = rf"{_ACTION_VERBS_PAST}|{_ACTION_VERBS_IMPERATIVE}"
_ACTION_LEAD_RE = re.compile(rf"^(?:{_ACTION_VERBS})\b", re.IGNORECASE)
_ACTION_ANYWHERE_RE = re.compile(rf"\b(?:{_ACTION_VERBS})\b", re.IGNORECASE)
# D-A: closing_action's "states a concrete next action" test must credit only
# an IMPERATIVE verb, and only when it leads the closing line — not a
# past-tense verb matched anywhere in it. Before this fix, "The patch was
# merged into main last night." wrongly passed closing_action: "merged" (past
# tense, describing something already done) matched the old combined
# any-position ``_ACTION_ANYWHERE_RE``. A past-tense recap is not a next
# action, whatever position it appears in, so the imperative-only vocabulary
# is also matched sentence-initially, not searched anywhere in the line.
_IMPERATIVE_ACTION_RE = re.compile(rf"^(?:{_ACTION_VERBS_IMPERATIVE})\b", re.IGNORECASE)
# An explicit next-step marker ("Next:", "Then:", "Now:", "TODO:") — shared by
# closing_action (a marker is itself a stated next action) and numbered_steps
# (a compound "rotate X, then re-run Y" *inside* a single next-step sentence
# is one forward-looking instruction, not unnumbered past multi-step work;
# see _text_before_next_marker below).
_NEXT_MARKER_RE = re.compile(r"\b(?:next|then|now|todo)\s*:", re.IGNORECASE)


def _text_before_next_marker(text: str) -> str:
    """The "what already happened" portion of a response, up to (not
    including) its first explicit next-step marker.

    Used only to decide whether PAST work was multi-step and left unnumbered
    — a compound next-step instruction ("Next: rotate the key, then re-run
    the job") chains two imperative sub-actions inside ONE forward-looking
    sentence, which is closing_action's territory, not evidence of numbered
    multi-step work.
    """
    m = _NEXT_MARKER_RE.search(text)
    return text[: m.start()] if m else text


# ---------------------------------------------------------------------------
# Check 1 — action-first: outcome or next action leads; prose follows.
# ---------------------------------------------------------------------------

_HEDGE_OPENERS = re.compile(
    r"^(i think|i believe|let me|i'll|i will|so|well|sure|okay|certainly|"
    r"great question|to start|before (i|we)|in order to|thanks for|happy to|"
    r"i'm going to|i took a look|took a look)\b",
    re.IGNORECASE,
)


def _check_action_first(response: str) -> tuple[bool, str]:
    first_line = _first_nonblank_line(response)
    if not first_line:
        return False, "empty response has no lead to grade"
    if _HEDGE_OPENERS.match(first_line):
        return False, (
            f"opens with a hedge/preamble, not the outcome or next action: "
            f"{first_line[:70]!r}"
        )
    if _has_concrete_artifact(first_line):
        return (
            True,
            f"leads with a concrete artifact (command/path/file:line): {first_line[:70]!r}",
        )
    if _ACTION_LEAD_RE.match(first_line):
        return (
            True,
            f"leads with a stated outcome/action verb: {first_line[:70]!r}",
        )
    return (
        False,
        f"first line is neither a hedge nor a concrete/action lead: {first_line[:70]!r}",
    )


# ---------------------------------------------------------------------------
# Check 2 — numbered multi-step work: sequential steps are numbered, not
# bulleted, not chained in unstructured prose — but a genuinely single-action
# reply has nothing to number and must not be penalized for it.
# ---------------------------------------------------------------------------

_NUMBERED_ITEM_RE = re.compile(r"(?m)^\s*(\d+)[.)]\s+\S")
_BULLET_ITEM_RE = re.compile(r"(?m)^\s*[-*]\s+\S")


def _numbered_step_values(text: str) -> list[int]:
    return [int(m.group(1)) for m in _NUMBERED_ITEM_RE.finditer(text)]


def _longest_consecutive_run(values: Sequence[int]) -> int:
    """Longest run of consecutive integers (each exactly one more than the
    last) in the order they appear — a numbered bibliography ("10.", "47.")
    or a two-item stub ("1.") does not count as sequential multi-step work."""
    if not values:
        return 0
    longest = current = 1
    for prev, curr in zip(values, values[1:], strict=False):
        if curr == prev + 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


_SINGLE_ACTION_WORD_CAP = 60

# D-D: a second, vocabulary-free multi-step signal. ``_ACTION_VERBS`` is a
# closed list, so a terse reply built entirely from unlisted verbs ("split",
# "wiped", "re-pointed", "bounced") has zero recognized action-verb
# occurrences and would otherwise vacuously pass as a single bounded action —
# e.g. "Split the module, moved the helpers into a package, and swapped the
# parser for the new one." This catches the Oxford-comma-style coordinated
# list shape (">= 2 commas" + a final ", and ..." clause) that a terse
# multi-step recap typically takes, independent of which verbs it uses.
_COORDINATED_LIST_TAIL_RE = re.compile(r",\s*and\s+\S")


def _has_coordinated_action_list(text: str) -> bool:
    """True when the "what already happened" portion of ``text`` (before any
    next-step marker — see :func:`_text_before_next_marker`) names >= 3
    coordinated items via an Oxford-comma-style list ("X, Y, and Z"). Checked
    only on that portion so the documented ``Next: run X, deploy Y, and
    announce Z`` exception (a forward-looking list, not unnumbered past
    multi-step work) is unaffected."""
    segment = _text_before_next_marker(text)
    return segment.count(",") >= 2 and bool(_COORDINATED_LIST_TAIL_RE.search(segment))


def _is_single_bounded_action(text: str) -> bool:
    """True when the text is a short, non-hedging, non-rambling description
    of at most one action.

    Decision (D5): the policy's "number multi-step work" rule is
    conditional on there BEING multi-step work. A correct, terse,
    single-action reply — exactly what ``action_first``/``closing_action``
    elsewhere reward — has nothing to number; scoring it as "failed to
    number its steps" would be a false negative that punishes compliant
    behavior and, per the task brief, would suppress the guidance arm in
    task 3's two-arm run.

    But a response with <= 1 recognized action verb is not automatically a
    *legitimate* single action — the vocabulary-trap fixture also has zero
    recognized action verbs while being verbose, hedging, and rambling about
    multiple undifferentiated things. So this requires ALL of: <= 1
    action-verb occurrence in the "what already happened" portion (before
    any explicit next-step marker — a compound "Next: rotate X, then re-run
    Y" is one forward-looking instruction, not two unnumbered past steps),
    no coordinated Oxford-comma-style action list naming >= 3 unlisted-verb
    items (D-D — :func:`_has_coordinated_action_list`; the verb-count guard
    above only sees verbs from the closed ``_ACTION_VERBS`` vocabulary, so a
    terse multi-step recap built entirely from unlisted verbs would otherwise
    slip through it), no vague-quantity filler (``_VAGUE_QUANTITY_RE``), no
    hedge/preamble opener, and a short response (<= 60 words) — the shape of
    an actually terse single-action reply, not merely the absence of a
    recognized verb.

    Each of these four guards is independently load-bearing (an ablation
    audit found three of the four removable without a test failing): the
    fixtures file carries a dedicated fixture per guard, each constructed so
    disabling ONLY that guard flips its fixture from FAIL to wrongly PASS.
    """
    if len(_ACTION_ANYWHERE_RE.findall(_text_before_next_marker(text))) > 1:
        return False
    if _has_coordinated_action_list(text):
        return False
    if _VAGUE_QUANTITY_RE.search(text):
        return False
    if _HEDGE_OPENERS.match(_first_nonblank_line(text)):
        return False
    return len(text.split()) <= _SINGLE_ACTION_WORD_CAP


def _check_numbered_steps(response: str) -> tuple[bool, str]:
    # Fence-stripped, unlike _check_specific_quantities/_check_closing_action
    # below, which grade the raw response — see the module docstring's
    # "Fence-stripped vs. raw input" note for why this asymmetry is
    # deliberate, not an oversight.
    stripped = _strip_fenced_code(response)
    numbers = _numbered_step_values(stripped)
    bullets = len(_BULLET_ITEM_RE.findall(stripped))
    run = _longest_consecutive_run(numbers)
    if run >= 2:
        return (
            True,
            f"{run} sequential numbered steps (of {len(numbers)} numbered lines)",
        )
    if numbers:
        return (
            False,
            f"{len(numbers)} numbered line(s) found but not sequential "
            f"(no run of >= 2 consecutive step numbers): {numbers}",
        )
    if bullets >= 2:
        return False, f"{bullets} multi-step items rendered as bullets, not numbered"
    if _is_single_bounded_action(stripped):
        return True, "single bounded action described; no multi-step work to number"
    return (
        False,
        "no sequential numbered multi-step structure found, and the reply "
        "describes more than one action without numbering it",
    )


# ---------------------------------------------------------------------------
# Check 3 — specific quantities over vague ones, weighed against each other.
# ---------------------------------------------------------------------------

# Named units, spaced or attached ("10ms", "10 milliseconds").
_SPECIFIC_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|kb|mb|gb|%|percent|hrs?|hours?|"
    r"min(?:ute)?s?|sec(?:ond)?s?|days?)\b",
    re.IGNORECASE,
)
# Bare-seconds shorthand ("42s", "11s") — no space, no "sec" prefix. Excludes
# a bare year-decade shape ("1980s", "2020s") via _YEAR_DECADE_RE below, so
# the ambiguous lone "s" unit can't be tricked into reading a decade as a
# duration (D6).
_SPECIFIC_BARE_SECONDS_RE = re.compile(r"\b\d+(?:\.\d+)?s\b")
_YEAR_DECADE_RE = re.compile(r"\A(?:19|20)\d{2}s\Z")
# Generalized "number + plural noun" (D6: replaces the closed unit-noun list
# that scored "12 dependencies" as "no quantity"). The noun's stem must be
# >= 4 letters before the trailing "s" — otherwise short function words that
# happen to end in "s" ("this", "is", "was", "less") false-positive on any
# adjacent number ("10:30 this morning" must not read as a quantity).
_SPECIFIC_COUNT_NOUN_RE = re.compile(r"\b\d+(?:\.\d+)?\s+[a-zA-Z]{4,}s\b")
# Comparative counts ("5 instead of 3", "2 vs 4") — a bare number pair is a
# specific quantity even with no unit noun attached.
_SPECIFIC_COMPARATIVE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:instead of|vs\.?|versus|out of)\s*\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_VAGUE_QUANTITY_RE = re.compile(
    r"\b(a (few|couple|bit|little|lot|while)|several|not (much|long)|"
    r"quite a (few|bit)|a number of|a good (bit|while)|plenty of|too much)\b",
    re.IGNORECASE,
)


def _iter_specific_quantity_matches(text: str) -> Iterable[re.Match[str]]:
    yield from _SPECIFIC_UNIT_RE.finditer(text)
    for m in _SPECIFIC_BARE_SECONDS_RE.finditer(text):
        if _YEAR_DECADE_RE.match(m.group(0)):
            continue
        yield m
    yield from _SPECIFIC_COUNT_NOUN_RE.finditer(text)
    yield from _SPECIFIC_COMPARATIVE_RE.finditer(text)


def _check_specific_quantities(response: str) -> tuple[bool, str]:
    specific_matches = list(_iter_specific_quantity_matches(response))
    vague_matches = list(_VAGUE_QUANTITY_RE.finditer(response))
    specific_count = len(specific_matches)
    vague_count = len(vague_matches)

    if specific_count == 0 and vague_count == 0:
        return False, "no quantity, specific or vague, found in the response"
    if specific_count == 0:
        return (
            False,
            f"uses a vague quantity instead of a specific one: {vague_matches[0].group(0)!r}",
        )
    if vague_count > specific_count:
        # D6/D4: a lone specific number buried among several vague ones must
        # not pass — "prefer specific over vague" is a comparison, not a
        # one-hit-and-done check. This is what makes _VAGUE_QUANTITY_RE
        # load-bearing rather than decorative.
        return (
            False,
            f"{specific_count} specific quantity/quantities outweighed by "
            f"{vague_count} vague one(s): {vague_matches[0].group(0)!r}",
        )
    return True, f"gives a specific quantity: {specific_matches[0].group(0)!r}"


# ---------------------------------------------------------------------------
# Check 4 — one concrete closing action: a stated next step, not merely a
# trailing artifact (D2).
# ---------------------------------------------------------------------------

_VAGUE_CLOSE_RE = re.compile(
    r"\b(let me know if|hope (this|that) helps|feel free to|happy to help|"
    r"glad to assist|don't hesitate|reach out if|any (other )?questions)\b",
    re.IGNORECASE,
)
# _NEXT_MARKER_RE is defined above, alongside the shared action-verb
# vocabulary — numbered_steps needs it too (_text_before_next_marker).


def _check_closing_action(response: str) -> tuple[bool, str]:
    last_line = _last_nonblank_line(response)
    if not last_line:
        return False, "empty response has no closing action to grade"
    if _VAGUE_CLOSE_RE.search(last_line):
        return (
            False,
            f"ends with a vague pleasantry, not a concrete action: {last_line[:70]!r}",
        )
    if last_line.startswith("```") or last_line.startswith(">"):
        # D2/D7: a trailing code fence and a markdown blockquote caveat both
        # read as "concrete" under a bare artifact test but state no action.
        return (
            False,
            f"closing line is a code fence/blockquote, not a stated action: "
            f"{last_line[:70]!r}",
        )
    if _NEXT_MARKER_RE.search(last_line) or _IMPERATIVE_ACTION_RE.match(last_line):
        return True, f"states a concrete next action: {last_line[:70]!r}"
    return (
        False,
        f"no concrete next action found in the closing line: {last_line[:70]!r}",
    )


_CHECK_FUNCS: dict[BehaviorCheck, Callable[[str], tuple[bool, str]]] = {
    BehaviorCheck.ACTION_FIRST: _check_action_first,
    BehaviorCheck.NUMBERED_STEPS: _check_numbered_steps,
    BehaviorCheck.SPECIFIC_QUANTITIES: _check_specific_quantities,
    BehaviorCheck.CLOSING_ACTION: _check_closing_action,
}


# ---------------------------------------------------------------------------
# Public surface — task 3 imports these unchanged.
# ---------------------------------------------------------------------------


def grade_response(response: str) -> BehaviorVerdict:
    """Score one response against all four observable-shape checks.

    Pure function over a string — no network, no API key, no model call.
    """
    results: list[CheckVerdict] = []
    for check, fn in _CHECK_FUNCS.items():
        ok, reason = fn(response)
        results.append(CheckVerdict(check=check, passed=ok, reason=reason))
    return BehaviorVerdict(results=tuple(results))


def grade_batch(responses: Iterable[str]) -> tuple[BehaviorVerdict, ...]:
    """Score a batch of responses, preserving order — one verdict per response."""
    return tuple(grade_response(r) for r in responses)


def pass_rate(verdicts: Sequence[BehaviorVerdict], check: BehaviorCheck) -> float:
    """Fraction of ``verdicts`` that passed ``check`` — for arm-vs-arm deltas.

    ponytail leaves this arithmetic to promptfoo's own aggregation
    (spec.md's "How the delta is computed"); dummyindex asserts it explicitly.
    """
    if not verdicts:
        return 0.0
    return sum(1 for v in verdicts if v.passed(check)) / len(verdicts)
