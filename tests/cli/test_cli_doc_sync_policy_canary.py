"""Rule-copy canary: ALWAYS_ON_OUTPUT_POLICY vs its restatements.

A self-contained guard on one constant vs three docs, split by concern out of
the subcommand doc-sync guards in ``test_cli_doc_sync.py``.
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


# --- rule-copy canary: invariant phrases tied to ALWAYS_ON_OUTPUT_POLICY
#
# Ported from ponytail's ``scripts/check-rule-copies.js`` (MIT, © 2026
# DietrichGebert): its ``INVARIANTS`` fallback for surfaces too long to
# byte-compare. ``ALWAYS_ON_OUTPUT_POLICY`` is the single source that three
# docs (`docs/COMMANDS.md`, `docs/guide/07-cli.md`, `dummyindex/skills/skill.md`)
# restate in different prose, so this is a canary, not byte equality.
#
# SCOPE: catches (a) a rule's statement dropped from a doc region and (b) a small
# named set of region-scoped inversions. It is NOT general contradiction
# detection: a hedge that keeps every pinned phrase (e.g. appending "unless
# brevity requires trimming it") still passes, and `inversions` is not exhaustive.
#
# COUPLING HOLE: `constant_pattern` and `statement_pattern`/`inversions` are
# hand-maintained independently. Reword the constant, update only
# `constant_pattern` and re-pin `_POLICY_CONSTANT_HASH`, and the doc patterns go
# stale with the suite green. A human reviewing `_POLICY_INVARIANTS` is the only
# safeguard.
#
# Each doc has two marker-delimited regions, never widened into each other:
# whole-file scanning let a hedge slip past while every pinned token stayed put.
#   - ``test-anchor:policy-restatement``: the output-policy prose restatement.
#   - ``test-anchor:policy-selfapply``: the `i-have-adhd` bullet. With
#     `disable-model-invocation: true`, enabling the plugin alone cannot make the
#     skill self-apply (upstream's opt-in SessionStart hook is inert without a
#     per-profile flag), so the project policy is the reliable carrier.
# Markers use `test-anchor:`, never the `dummyindex:*` namespace reserved for
# tool-parsed managed regions; `render_skill()` strips them from installed skills.
@dataclass(frozen=True)
class _PolicyInvariant:
    """One policy rule, checked against the constant and one doc region.

    - constant_pattern: regex (not a literal, so glue-word copy-edits stay
      green) that the whitespace-flattened, lowercased constant must match.
    - statement_pattern: regex for the rule's content, never its name, in the
      flattened, lowercased region; None means the region may omit the rule.
    - inversions: regexes that redden the region even if the statement matches.
    """

    label: str
    constant_pattern: str
    statement_pattern: str | None
    inversions: tuple[str, ...] = ()
    region: str = "restatement"


_POLICY_INVARIANTS: tuple[_PolicyInvariant, ...] = (
    _PolicyInvariant(
        # `inversions` name the shapes that invert the rule, never a negative
        # lookbehind over correct ones: a lookbehind on the cue before "wait"
        # reddened correct rewordings ("does not wait", "rather than waiting").
        # A fully dropped negation fails `statement_pattern` and reddens via `missing`.
        "always-on / never-wait-for-invocation",
        r"always on[,;]?\s*never wait for an invocation",
        # The rule's statement, not the policy's name. Family A is cue-first
        # ("<negation> wait(ing) for ... invocation"); family B is
        # invocation-first or wait-free. Both accept the known correct
        # rewordings, including the constant's own "never wait for".
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
            # additive contradiction: the negated statement survives elsewhere
            # while a later clause says the policy waits before applying
            # (mirrors the `selfapply` row's "reach it on its own" catch).
            r"wait\w*\s+(?:for\s+(?:an\s+)?(?:explicit\s+)?"
            r"(?:plugin/skill\s+)?invocation\s+)?before\s+(?:it\s+)?appl\w*",
        ),
    ),
    _PolicyInvariant(
        # The `i-have-adhd` bullet (`selfapply` region). statement_pattern
        # accepts each true shape ("never makes it self-apply", "cannot
        # self-apply", "nothing about X will make it self-apply"); a dropped
        # clause reddens via `missing`, an appended contradiction via the inversion.
        "self-contained-even-when-neither-skill-loaded",
        r"self-contained.{0,30}even when neither skill is loaded",
        r"(?:never\s+(?:make[s]?\s+it\s+)?self-appl\w*"
        r"|cannot\s+self-appl\w*"
        r"|nothing\s+about\b.{0,40}will\s+make\s+it\s+self-apply)",
        (
            # additive contradiction: the negation survives but an appended
            # clause says the model reaches the skill unaided anyway.
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
            # the key/value survives but its consequence is reversed (the
            # model "may still override" it, so it is "reachable without ...").
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
            # precedence reversed: the policy overrides the user/safety yield.
            # "overrides nothing" is the true disclaimer, so it is excluded.
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

# Decay guard: a sha256 pin of the flattened constant fires on ANY edit so a
# human re-checks `_POLICY_INVARIANTS`. It is not a proxy for "every clause has
# a row"; a sentence-count guard both false-positived and false-negatived.
_POLICY_CONSTANT_HASH = "6177b89c4ea1033b"


@pytest.mark.unit
def test_always_on_output_policy_carries_every_load_bearing_invariant() -> None:
    """The constant itself must state each behavior-contract rule inline.

    ``ALWAYS_ON_OUTPUT_POLICY`` is rendered into every managed CLAUDE.md /
    AGENTS.md block and restated by the three docs. This must fail on a revert
    to the shorthand ("use the combined `caveman`/`i-have-adhd` behavior"
    without the inlined rules or the `disable-model-invocation` caveat) that
    shipped the ADHD half of the policy inert.
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
    """Every doc's policy regions must not drop or contradict a load-bearing rule.

    See SCOPE in the module comment: this catches a dropped statement and the
    named inversions in each row's region, not general contradiction; a hedge
    that keeps the key phrase can still pass. Region-scoping keeps `inversions`
    from false-positiving on correct prose elsewhere in the doc.
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
