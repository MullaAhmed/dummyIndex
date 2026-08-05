"""Rule-copy canary: ALWAYS_ON_OUTPUT_POLICY vs its restatements.

Split out of ``test_cli_doc_sync.py`` (folder-organization convention: split
by concern once a module grows past ~600 lines,
`.context/conventions/coding-practices.md:92`) — this is a self-contained
guard on one constant vs three docs, not part of the subcommand doc-sync
guards in the sibling module.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from dummyindex.context.output.bootstrap import ALWAYS_ON_OUTPUT_POLICY
from tests.cli.test_cli_doc_sync import _DEFAULT_PLUGIN_DOCS, _DOC_IDS
from tests.paths import REPO_ROOT


# ----- rule-copy canary: invariant phrases tied to ALWAYS_ON_OUTPUT_POLICY --
#
# Ported from ponytail's ``scripts/check-rule-copies.js`` (MIT, © 2026
# DietrichGebert): its ``INVARIANTS`` fallback for surfaces too long to
# byte-compare. ``ALWAYS_ON_OUTPUT_POLICY``
# (`dummyindex/context/output/bootstrap.py:32-52`) is the single source three
# shipped docs restate in deliberately different English prose
# (`docs/COMMANDS.md`, `docs/guide/07-cli.md`, `dummyindex/skills/skill.md`),
# so this is a canary, not byte equality.
#
# SCOPE, STATED PLAINLY (a second adversarial audit failed the prior,
# whole-file version of this canary — see the proposal's spec, Item 2 Risks):
# this catches (a) a load-bearing rule's *statement* being dropped from
# either of a doc's two delimited regions, and (b) a small NAMED set of
# region-scoped negation/hedge inversions. It is NOT general contradiction
# detection in free prose — out of reach for a regex canary. A hedge that
# keeps every pinned phrase intact (e.g. appending "unless brevity requires
# trimming it") can still slip through; region-scoping bounds a false
# positive's blast radius to one paragraph, it does not make `inversions`
# exhaustive.
#
# DISCLOSED COUPLING HOLE (same hedge-limit class as above, not fixed by it):
# `constant_pattern` and `statement_pattern`/`inversions` are maintained by
# hand, independently, on opposite sides of the same row. Reword or invert
# `ALWAYS_ON_OUTPUT_POLICY` while updating only `constant_pattern` and
# re-pinning `_POLICY_CONSTANT_HASH` below, and every doc's
# `statement_pattern`/`inversions` can go stale silently — the suite stays
# green because each side is checked against its own text, never against the
# other's. Nothing here mechanically ties the two together; a human
# reviewing the diff to `_POLICY_INVARIANTS` is the actual safeguard, the
# same hand-maintained-invariant limitation upstream ponytail accepts with
# its own `INVARIANTS` list.
#
# TWO independent, delimited regions per doc — deliberately not one, and
# deliberately not widened into each other (the self-apply text sits two
# unrelated paragraphs away from the restatement paragraph in every doc;
# swallowing that gap would reintroduce the whole-file false-positive class
# the region-scoping was built to kill):
#
#   - ``test-anchor:policy-restatement`` — the always-on output-policy prose
#     restatement (lead-with-outcome, keep-prose-compact, etc.).
#   - ``test-anchor:policy-selfapply`` — the `i-have-adhd` reviewed-source
#     bullet: the fact that `disable-model-invocation: true` means installing
#     and enabling the plugin alone cannot make the skill self-apply. Upstream
#     now also ships an opt-in SessionStart hook, but it stays inert without a
#     per-profile flag; dummyindex's project policy remains the reliable
#     profile-independent carrier. A doc-
#     level inversion of exactly this fact ("never makes it self-apply" ->
#     "does make it self-apply") is what the first audit caught and the
#     first version of this canary's region-scoping let back through — this
#     second region closes that gap.
#
# Each marker pair lives in the `test-anchor:` namespace, deliberately OUTSIDE
# `dummyindex:*` — this repo reserves `<!-- dummyindex:* -->` for managed,
# tool-parsed, do-not-hand-edit regions in user-facing files (`dummyindex:begin`
# /`:end` in `context/output/bootstrap.py:15,18`, `dummyindex:begin:codex`/
# `:end:codex` in `context/output/agents_md.py:25,28`,
# `dummyindex:consistency:begin/end` in `context/domains/proposals/store.py:
# 29-30`, `dummyindex:merged:begin/end` in `context/domains/features/
# constants.py:62-63`, `dummyindex:owner*` in `agents_md.py`,
# `dummyindex:generated` in `context/domains/equip/models.py:29`, and
# `dummyindex:installed` in `context/domains/equip/constants.py:69`). This
# canary's markers are test-only scaffolding, not a managed region any tool
# parses, so they must never ship inside that reserved namespace — hence
# `test-anchor:`, verified by grepping every `dummyindex:` marker string above
# to confirm none of them share so much as a prefix with `test-anchor:policy-
# restatement:*` / `test-anchor:policy-selfapply:*` (nor do the two canary
# markers collide with each other — "restatement" and "selfapply" share no
# prefix beyond `test-anchor:policy-`, itself not a parsed marker anywhere).
# `render_skill()` (`dummyindex/installer/common.py`) additionally strips any
# line matching the `test-anchor:` comment shape at install/repair render
# time, so even this test-only namespace never reaches an installed
# `SKILL.md` — see `test_render_skill_strips_test_anchor_markers` in
# `tests/test_install.py`. All region-scoped assertions below scan ONLY the
# text between one doc's ONE relevant marker pair — whole-file scanning is
# exactly what let a hedge/exception/reversal slip past while every pinned
# token in the other 30k+ chars stayed put.
#
# Each row is (label, constant_pattern, statement_pattern, inversions,
# region):
#   - constant_pattern: a regex the flattened, lowercased constant must
#     `re.search`. Regexes, not literals — an unambiguous literal also pins
#     incidental glue (a comma, an article), reddening on a same-meaning
#     copy-edit. Trimmed to the semantic core, tolerant gaps for glue.
#   - statement_pattern: a regex the doc's named `region` must `re.search` —
#     the rule's content, never its name (asserting the name "always-on
#     output policy" is what let the flagship rule be deleted from every doc
#     while staying green). `None` means the region legitimately omits this
#     rule — verified by grepping the region's actual text, not assumed.
#   - inversions: a small, tight tuple of regexes whose presence inside the
#     REGION reddens the test even when `statement_pattern` still matches (a
#     restatement can contradict the constant — negation dropped, precedence
#     reversed, scope narrowed — while the rule's key phrase survives). Empty
#     where no named contradiction shape applies.
#   - region: which of the two marker-delimited regions this row is checked
#     against ("restatement" or "selfapply"). Generalized to a field rather
#     than two hardcoded code paths so a third region, if ever needed, is one
#     new row attribute plus one new entry in `_POLICY_REGION_MARKERS`, not a
#     forked test function.
#
# Matches are case-insensitive (region text is lowercased) regex checks on
# whitespace-flattened text, mirroring `INVARIANTS`' `text.includes(phrase)`
# upgraded to `re.search`, rescoped from "whole file" to "one named region".
@dataclass(frozen=True)
class _PolicyInvariant:
    label: str
    constant_pattern: str
    statement_pattern: str | None
    inversions: tuple[str, ...] = ()
    region: str = "restatement"


_POLICY_INVARIANTS: tuple[_PolicyInvariant, ...] = (
    _PolicyInvariant(
        # A prior lookbehind-based approach tried to whitelist the negation
        # cue immediately before "wait(ing) for ... invocation"
        # (`(?<!do not )(?<!without )(?<!never )`) and false-positived on
        # every correct rewording that doesn't put the negation word
        # *directly* against "wait" — "does not wait", "rather than
        # waiting", "instead of waiting", "no need to wait", and worst, an
        # intact statement plus a correct trailing sentence ("There is no
        # need to wait for an invocation.") all reddened despite saying
        # nothing wrong. Fixed the way the `selfapply` rows already do it
        # (they produced zero false positives across eight probes): make
        # `statement_pattern` a tolerant alternation over every true "does
        # not wait" shape, and specify `inversions` positively — name the
        # shapes that actually invert the rule, never a negative lookbehind
        # over the correct ones. A mutation that drops every accepted
        # negation shape outright (e.g. bare "waiting for an invocation"
        # with no negation left anywhere) fails to match `statement_pattern`
        # at all and reddens via `missing`, same as the `selfapply` rows'
        # drop-detection — no inversion needed to catch that case.
        "always-on / never-wait-for-invocation",
        r"always on[,;]?\s*never wait for an invocation",
        # the rule's STATEMENT, not the policy's NAME. Two families, because
        # a correct restatement does not always put the negation cue before
        # the word "wait" — or use "wait" at all. Family A is cue-first
        # ("<negation> wait(ing) for ... invocation"); family B is
        # invocation-first or wait-free. Both were widened after an audit
        # found four correct rewordings reddening via `missing`, the worst
        # being the constant's OWN wording ("always on, never wait for an
        # invocation") — bare `never wait for` was absent while
        # `never need to wait for` was present.
        r"(?:(?:without\s+waiting\s+for"
        r"|do\s+not\s+wait\s+for"
        r"|does\s+not\s+wait\s+for"
        r"|never\s+wait\s+for"
        r"|instead\s+of\s+waiting\s+for"
        r"|rather\s+than\s+waiting\s+for"
        r"|no\s+need\s+to\s+wait\s+for"
        r"|need\s+not\s+wait\s+for"
        r"|never\s+need\s+to\s+wait\s+for"
        r"|no\s+waiting\s+for"
        r"|skipping\s+the\s+need\s+to\s+wait\s+for"
        r"|without)\s+(?:an\s+)?(?:explicit\s+)?(?:plugin/skill\s+)?invocation"
        # family B — the object leads, or "wait" never appears. Each keeps
        # its own negation so a bare "invocation is required" (a real
        # inversion) can never satisfy the statement.
        r"|(?:an\s+|the\s+)?(?:explicit\s+)?(?:plugin/skill\s+)?invocation"
        r"\s+is\s+(?:never|not)\s+(?:required|needed)"
        r"|no\s+(?:explicit\s+)?(?:plugin/skill\s+)?invocation\s+is\s+"
        r"(?:required|needed)"
        r")",
        (
            # scope narrowed: gated behind an explicit invocation instead
            # of unconditional — positively specified, no lookbehind.
            r"only\s+(?:after|once|upon|when)\s+(?:an\s+|receiving\s+)?"
            r"(?:explicit\s+)?(?:plugin/skill\s+)?invocation",
            # additive contradiction: the negated statement can survive
            # intact elsewhere while a later clause asserts the policy
            # actually waits before applying — the positive "wait ...
            # before applying" shape this row's fix adds, mirroring the
            # `selfapply` row's "reach it on its own" catch below.
            r"wait\w*\s+(?:for\s+(?:an\s+)?(?:explicit\s+)?"
            r"(?:plugin/skill\s+)?invocation\s+)?before\s+(?:it\s+)?appl\w*",
        ),
    ),
    _PolicyInvariant(
        # Second, independent region (`test-anchor:policy-selfapply`): the
        # `i-have-adhd` bullet, wherever it sits in the doc's default-plugins
        # list. statement_pattern is a tolerant alternation over the true
        # shapes this fact is stated in ("never makes/made it self-apply",
        # "cannot self-apply", "nothing about X will make it self-apply",
        # "never self-applies") — loose enough that a fair paraphrase stays
        # green, tight enough that dropping the clause outright (no negation
        # cue left near "self-appl*") already reddens via `missing` before
        # any dedicated inversion runs. The one dedicated inversion below
        # catches the shape a bare drop-detection can't: the pinned negated
        # phrase left intact while a contradicting clause is appended
        # elsewhere in the same bullet (audit-2's N5).
        "self-contained-even-when-neither-skill-loaded",
        r"self-contained.{0,30}even when neither skill is loaded",
        r"(?:never\s+(?:make[s]?\s+it\s+)?self-appl\w*"
        r"|cannot\s+self-appl\w*"
        r"|nothing\s+about\b.{0,40}will\s+make\s+it\s+self-apply)",
        (
            # additive contradiction: the negated statement survives intact
            # but a clause is appended asserting the model reaches the skill
            # unaided anyway (audit-2's N5: "... but the model is able to
            # reach it on its own once the plugin is enabled.").
            r"reach\w*\s+it\s+on\s+its\s+own",
        ),
        region="selfapply",
    ),
    _PolicyInvariant(
        # Same region as above, same bullet: the `disable-model-invocation`
        # key/value is the mechanism the self-apply fact rests on.
        "disable-model-invocation reason",
        "disable-model-invocation: true",
        r"disable-model-invocation:\s*true",
        (
            # the key/value survives but its consequence is reversed: the
            # model is said to reach the skill anyway (audit-2's N6:
            # "... which the model may still override, so it is reachable
            # without the user typing /i-have-adhd").
            r"may\s+still\s+override",
            r"reachable\s+without\s+the\s+user\s+typing",
        ),
        region="selfapply",
    ),
    _PolicyInvariant(
        "outcome-or-next-action-first",
        "lead with the outcome or the next action",
        "lead with the outcome or next action",
    ),
    _PolicyInvariant(
        "command-or-path-before-prose",
        r"a command, path, or `file:line` comes first and prose comes after",
        None,
    ),
    _PolicyInvariant(
        "numbered multi-step work",
        "number multi-step work",
        "number multi-step work",
    ),
    _PolicyInvariant(
        "keep prose compact",
        r"keep prose compact.{0,80}tool-call narration",
        "keep prose compact",
    ),
    _PolicyInvariant(
        "suppress tangents",
        "suppress tangents and options you are not taking",
        "suppress tangents",
    ),
    _PolicyInvariant(
        "restate current state",
        "restate the current state each turn rather than expecting the "
        "reader to hold it",
        "restate current state",
    ),
    _PolicyInvariant(
        "specific quantities over vague ones",
        r"prefer specific quantities.{0,60}over vague ones",
        None,
    ),
    _PolicyInvariant(
        "one concrete closing action",
        r"make finished work visible.{0,20}end with one concrete next action",
        None,
    ),
    _PolicyInvariant(
        "compress prose, never substance",
        r"compress (?:the )?prose,?\s*never (?:the )?substance",
        "preserve technical and safety detail",
    ),
    _PolicyInvariant(
        "session tiebreaker: unsure means it still applies",
        "when you are unsure whether it still applies, it does",
        None,
    ),
    _PolicyInvariant(
        "holds for the whole session / does not lapse",
        r"this policy holds for the whole session\.?\s*it does not lapse",
        None,
    ),
    _PolicyInvariant(
        "yields to explicit user request and safety",
        r"yields.{0,15}explicit user formatting request.{0,20}"
        r"safety requirements",
        "explicit user formatting requests and safety requirements win",
        (
            # scope narrowed: the win made conditional ("only where the
            # policy is silent") instead of unconditional.
            r"win\s+only\s+(?:where|if|when)\b",
            # precedence reversed: policy stated to override the user/
            # safety yield it is supposed to lose to. Excludes "overrides
            # nothing" — that is the TRUE, non-inverted claim (the doc
            # explicitly disclaiming any override), not an inversion.
            r"policy\s+overrides\b(?!\s+nothing\b)",
        ),
    ),
    _PolicyInvariant(
        "user opt-out escape hatch",
        r"stops when the user says so.{0,10}normal mode.{0,40}"
        r"stop adhd mode.{0,30}acknowledge in one line",
        None,
    ),
)

# Decay guard, honest version: NOT a proxy for "every clause has a row" (the
# sentence-count guard this replaces false-positived on an added `e.g.` and a
# split sentence, and false-negatived on a genuinely new clause and on a
# sentence ending `.)"` — net negative). A sha256 pin of the flattened
# constant never lies about what changed: it fires on ANY edit, with an
# explicit instruction to go re-check `_POLICY_INVARIANTS` by hand rather
# than claiming to know what changed.
_POLICY_CONSTANT_HASH = "6177b89c4ea1033b"


@pytest.mark.unit
def test_always_on_output_policy_carries_every_load_bearing_invariant() -> None:
    """The constant itself must state each behavior-contract rule inline.

    ``ALWAYS_ON_OUTPUT_POLICY`` is the single source ``agents_md.py`` renders
    into every managed CLAUDE.md/AGENTS.md block and the three docs below
    restate in prose. Reverting it to the pre-fix shorthand — "use the
    combined `caveman`/`i-have-adhd` behavior" without inlining the rules or
    the `disable-model-invocation` caveat — is exactly the bug that shipped
    the ADHD half of the policy inert (see
    `.context/proposals/repo-adoptions-ponytail-headroom/spec.md`, Item 2).
    This must fail on that revert.
    """
    flat = " ".join(ALWAYS_ON_OUTPUT_POLICY.split()).lower()
    missing = [
        inv.label
        for inv in _POLICY_INVARIANTS
        if not re.search(inv.constant_pattern, flat)
    ]
    assert not missing, (
        f"ALWAYS_ON_OUTPUT_POLICY is missing load-bearing invariant(s): {missing}"
    )


@pytest.mark.unit
def test_always_on_output_policy_hash_pin_flags_unreviewed_changes() -> None:
    """Decay guard only — a hash mismatch is a prompt to review, not a defect.

    If this reddens: read the diff to `ALWAYS_ON_OUTPUT_POLICY`, decide
    whether `_POLICY_INVARIANTS` above still names every load-bearing clause
    (add/remove/update a row if not, and its doc restatement if any), then
    update `_POLICY_CONSTANT_HASH` to the digest this test reports. Never
    "fix" this by reverting the constant.
    """
    flat = " ".join(ALWAYS_ON_OUTPUT_POLICY.split()).lower()
    digest = hashlib.sha256(flat.encode()).hexdigest()[:16]
    assert digest == _POLICY_CONSTANT_HASH, (
        f"ALWAYS_ON_OUTPUT_POLICY changed (new hash {digest}); review "
        "_POLICY_INVARIANTS coverage above, then set _POLICY_CONSTANT_HASH "
        f'= "{digest}"'
    )


class PolicyRegionMarkerError(AssertionError):
    """A doc's marker pair for a named policy region is missing, duplicated,
    or unbalanced — a hard failure, never a silently-empty region."""


# One marker pair per named region. Both are independently required to be
# present-and-balanced in all three docs (see the balanced-pair test below);
# neither is ever widened to cover the other's content.
_POLICY_REGION_MARKERS: dict[str, tuple[str, str]] = {
    "restatement": (
        "<!-- test-anchor:policy-restatement:begin -->",
        "<!-- test-anchor:policy-restatement:end -->",
    ),
    "selfapply": (
        "<!-- test-anchor:policy-selfapply:begin -->",
        "<!-- test-anchor:policy-selfapply:end -->",
    ),
}


def _policy_region(text: str, doc_label: str, region: str) -> str:
    """Return the text strictly between the named region's marker pair.

    Raises `PolicyRegionMarkerError` (an `AssertionError` subclass, so it
    fails the calling test loudly) unless exactly one begin and one end
    marker for `region` are present, in order.
    """
    begin_marker, end_marker = _POLICY_REGION_MARKERS[region]
    begin_count = text.count(begin_marker)
    end_count = text.count(end_marker)
    if begin_count != 1 or end_count != 1:
        raise PolicyRegionMarkerError(
            f"{doc_label} must carry exactly one balanced "
            f"{begin_marker!r}/{end_marker!r} marker pair; found "
            f"{begin_count} begin marker(s) and {end_count} end marker(s)"
        )
    begin_at = text.index(begin_marker) + len(begin_marker)
    end_at = text.index(end_marker)
    if end_at < begin_at:
        raise PolicyRegionMarkerError(
            f"{doc_label}: the {region!r} region's end marker appears "
            "before its begin marker"
        )
    return text[begin_at:end_at]


_ALL_DOC_REGION_CASES = [
    (doc_path, region)
    for region in _POLICY_REGION_MARKERS
    for doc_path in _DEFAULT_PLUGIN_DOCS
]
_ALL_DOC_REGION_IDS = [
    f"{doc_id}-{region}" for region in _POLICY_REGION_MARKERS for doc_id in _DOC_IDS
]


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc_path,region",
    _ALL_DOC_REGION_CASES,
    ids=_ALL_DOC_REGION_IDS,
)
def test_default_plugin_docs_have_one_balanced_policy_region(
    doc_path: Path, region: str
) -> None:
    """Each doc must delimit BOTH named regions with exactly one balanced
    marker pair each — a missing or duplicated marker is a hard failure
    here, not a silently-empty region in the tests that follow. Applies to
    both `restatement` and `selfapply` in all three docs (six cases)."""
    text = doc_path.read_text(encoding="utf-8")
    label = str(doc_path.relative_to(REPO_ROOT))
    region_text = _policy_region(text, label, region)
    assert region_text.strip(), (
        f"{label}: the {region!r} region between markers is empty"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc_path",
    _DEFAULT_PLUGIN_DOCS,
    ids=_DOC_IDS,
)
def test_default_plugin_docs_restate_policy_invariants(doc_path: Path) -> None:
    """Every doc's policy regions must not drop or contradict a load-bearing
    rule while restating it in its own prose.

    SCOPE (see the module comment above the table): this catches a dropped
    rule statement and a named set of region-scoped inversions, checked
    against whichever of the two regions each row names. It is not general
    contradiction detection — a hedge or exception clause that keeps the
    rule's key phrase intact can still pass. Region-scoping (not whole-file
    scanning) is what keeps `inversions` from false-positiving on unrelated,
    correct prose elsewhere in the same doc. A row with
    `statement_pattern=None` is a rule its region is allowed to omit
    outright.
    """
    text = doc_path.read_text(encoding="utf-8")
    label = str(doc_path.relative_to(REPO_ROOT))
    region_text_by_name = {
        region: " ".join(_policy_region(text, label, region).split()).lower()
        for region in _POLICY_REGION_MARKERS
    }

    missing = [
        inv.label
        for inv in _POLICY_INVARIANTS
        if inv.statement_pattern is not None
        and not re.search(inv.statement_pattern, region_text_by_name[inv.region])
    ]
    contradicted = [
        (inv.label, pattern)
        for inv in _POLICY_INVARIANTS
        for pattern in inv.inversions
        if re.search(pattern, region_text_by_name[inv.region])
    ]
    assert not missing, f"{label} policy region(s) omit statement(s) {missing}"
    assert not contradicted, (
        f"{label} policy region(s) contradict invariant(s) {contradicted}"
    )
