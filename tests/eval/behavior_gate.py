"""Deterministic behavior-gate grader over ``ALWAYS_ON_OUTPUT_POLICY``.

`.context/proposals/repo-adoptions-ponytail-headroom/spec.md`. Ported from
``DietrichGebert/ponytail`` (MIT, © 2026 DietrichGebert), following the credit
idiom of ``tests/eval/test_retrieval_eval.py``. Pure, no LLM judge: every response
gets all four regex/structure checks on its observable shape, and a reply that only
talks about the rules (the ``trap`` fixtures) must fail every one.
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
    """A :class:`BehaviorVerdict` has no result for the requested check.

    :func:`grade_response` always records all four; this guards hand-built verdicts.
    """


class BehaviorCheck(str, Enum):
    """The four observable-shape rules probed from ``ALWAYS_ON_OUTPUT_POLICY``.

    The policy states them as prose; each member names the regex/structure
    heuristic that checks whether a response's shape exhibits the rule.
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


# Shared shape primitives.


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
    """Blank out fenced code so step counting never credits a pasted listing."""
    return _FENCE_RE.sub(" ", text)


# A "concrete artifact" names something checkable: a file:line, a path with an
# extension, a bare dot-extension token (``bootstrap.py``) or a ``$ ``-led command.
# Not any backticked span or ``> `` line: a backticked policy word and a markdown
# blockquote are far more common than a real artifact.
_FILE_LINE_RE = re.compile(r"[\w./-]+\.\w{1,10}:\d+")
_PATH_RE = re.compile(r"\b[\w-]+(?:/[\w.-]+)+\.\w{1,10}\b")
# A bare dot-extension token with no slash ("pyproject.toml"). The 2-char prefix
# bound excludes "e.g."/"i.e." and "3.5" (which the letters-only extension also
# excludes), and the extension must touch the dot, so a sentence-final period
# followed by a space never matches.
_DOT_EXT_RE = re.compile(r"\b[\w-]{2,}\.[A-Za-z]{2,10}\b")


def _has_concrete_artifact(line: str) -> bool:
    return bool(
        _FILE_LINE_RE.search(line)
        or _PATH_RE.search(line)
        or _DOT_EXT_RE.search(line)
        or line.startswith("$ ")
    )


# Action verbs, split by tense: action_first's lead may state what happened
# ("Rolled back...") or what's next ("Run..."), but closing_action credits only a
# next action, never a recap. The combined ``_ACTION_VERBS`` serves action_first
# and the action count in :func:`_is_single_bounded_action`.
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
# closing_action credits only an imperative verb leading the closing line: a
# past-tense recap ("The patch was merged...") is not a next action, wherever it sits.
_IMPERATIVE_ACTION_RE = re.compile(rf"^(?:{_ACTION_VERBS_IMPERATIVE})\b", re.IGNORECASE)
# An explicit next-step marker ("Next:", "Then:", "Now:", "TODO:"). closing_action
# treats it as a stated next action; numbered_steps splits on it, since "rotate X,
# then re-run Y" after a marker is one forward-looking instruction.
_NEXT_MARKER_RE = re.compile(r"\b(?:next|then|now|todo)\s*:", re.IGNORECASE)


def _text_before_next_marker(text: str) -> str:
    """The "what already happened" text, up to the first next-step marker.

    Used only to judge whether past work was multi-step and unnumbered; a compound
    instruction after the marker is closing_action's territory.
    """
    m = _NEXT_MARKER_RE.search(text)
    return text[: m.start()] if m else text


# Check 1 — action-first: outcome or next action leads; prose follows.

_HEDGE_OPENERS = re.compile(
    r"^(i think|i believe|let me|i'll|i will|so|well|sure|okay|certainly|"
    r"great question|to start|before (i|we)|in order to|thanks for|happy to|"
    r"i'm going to|i took a look|took a look)\b",
    re.IGNORECASE,
)


# Lead-only by design: grades the first non-blank line and never re-inspects the
# body, which the other three checks cover.
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


# Check 2 — multi-step work is numbered, not bulleted or chained in prose; a
# single-action reply has nothing to number and must not be penalized.

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

# A vocabulary-free multi-step signal: ``_ACTION_VERBS`` is closed, so a terse recap
# in unlisted verbs ("Split the module, moved the helpers, and swapped the parser.")
# would pass as a single action. This catches its ">= 2 commas + ', and ...'" shape.
_COORDINATED_LIST_TAIL_RE = re.compile(r",\s*and\s+\S")


def _has_coordinated_action_list(text: str) -> bool:
    """True when the pre-marker text has >= 2 commas and a ", and ..." tail.

    Pre-marker only, so ``Next: run X, deploy Y, and announce Z`` (a forward-looking
    list) is unaffected.
    """
    segment = _text_before_next_marker(text)
    return segment.count(",") >= 2 and bool(_COORDINATED_LIST_TAIL_RE.search(segment))


def _is_single_bounded_action(text: str) -> bool:
    """True when the text is a short, non-hedging description of at most one action.

    "Number multi-step work" only applies when there is some, so a terse one-action
    reply must pass. Few recognized verbs is not enough (the vocabulary trap has
    none), so all must hold: <= 1 action verb before any next-step marker, no
    coordinated list, no vague quantity, no hedge opener, <= 60 words. Each guard
    is pinned by a fixture that wrongly passes if only that guard is disabled.
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
    # Fence-stripped so pasted code can't smuggle in steps or verbs. The quantity
    # and closing checks grade the raw response on purpose: a backticked command
    # can carry a real quantity or next action.
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


# Check 3 — specific quantities over vague ones, weighed against each other.

# Named units, spaced or attached ("10ms", "10 milliseconds").
_SPECIFIC_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|kb|mb|gb|%|percent|hrs?|hours?|"
    r"min(?:ute)?s?|sec(?:ond)?s?|days?)\b",
    re.IGNORECASE,
)
# Bare-seconds shorthand ("42s"); _YEAR_DECADE_RE keeps "1980s" from reading as a duration.
_SPECIFIC_BARE_SECONDS_RE = re.compile(r"\b\d+(?:\.\d+)?s\b")
_YEAR_DECADE_RE = re.compile(r"\A(?:19|20)\d{2}s\Z")
# "Number + plural noun" ("12 dependencies"). The stem needs >= 4 letters before the
# "s", so a number before "this" or "less" never reads as a quantity.
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
        # "Prefer specific over vague" is a comparison: a lone number among more
        # vague ones fails.
        return (
            False,
            f"{specific_count} specific quantity/quantities outweighed by "
            f"{vague_count} vague one(s): {vague_matches[0].group(0)!r}",
        )
    return True, f"gives a specific quantity: {specific_matches[0].group(0)!r}"


# Check 4 — the closing line states a next step, not merely a trailing artifact.

_VAGUE_CLOSE_RE = re.compile(
    r"\b(let me know if|hope (this|that) helps|feel free to|happy to help|"
    r"glad to assist|don't hesitate|reach out if|any (other )?questions)\b",
    re.IGNORECASE,
)
# _NEXT_MARKER_RE is defined above, since numbered_steps uses it too.


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
        # A trailing fence or blockquote caveat looks "concrete" but states no action.
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


# Public surface — task 3 imports these unchanged.


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
