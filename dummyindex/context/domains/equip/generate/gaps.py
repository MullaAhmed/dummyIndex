"""Capability-gap analysis: ``required(stack, proposal) - covered(manifest)``.

Pure over its inputs, no I/O. This is the real gap signal that replaces the old
2-tag ``_needed_caps`` stub: it knows what the repo's stack + a proposal *require*
and subtracts what ``equipment.json`` *already covers*, so discovery, the
build-loop missing-capability signal, and plan-time auto-equip all act on a
deterministic gap rather than a guess.

``required`` is intentionally conservative — the always-needed code baseline
(gated by stack signals) plus whatever a proposal explicitly scopes. Specialist
capabilities (security / database / performance / docs / search / frontend) enter
``required`` only through ``proposal_capabilities`` so a backend repo is never
told it "needs" a frontend skill off an incidental keyword (the same
false-positive caution as ``adopt.resolve_coverage``'s stack-consistency gate).
"""

from __future__ import annotations

from ..enums import Capability
from ..models import EquipmentManifest, StackProfile


def covered_capabilities(manifest: EquipmentManifest) -> frozenset[str]:
    """The union of every manifest item's capabilities (what is already equipped)."""
    return frozenset(cap for item in manifest.items for cap in item.capabilities)


def required_capabilities(
    profile: StackProfile,
    *,
    proposal_capabilities: tuple[str, ...] = (),
) -> frozenset[str]:
    """The capabilities this repo requires: stack baseline + proposal scoping.

    Stack baseline (each gated by a real signal so a fresh/generic repo asks for
    nothing it cannot use):

    - ``implement`` / ``review`` / ``verify`` — when the stack is a real (non
      ``generic``) language;
    - ``test`` — when a test runner was detected;
    - ``format`` — when a formatter was detected.

    ``proposal_capabilities`` are folded in verbatim — they are already canonical
    :class:`Capability` values harvested by ``extract_proposal_capabilities``.
    """
    required: set[str] = set()
    has_stack = bool(profile.label) and profile.label != "generic"
    if has_stack:
        required.update(
            {
                Capability.IMPLEMENT.value,
                Capability.REVIEW.value,
                Capability.VERIFY.value,
            }
        )
    if profile.test_runner:
        required.add(Capability.TEST.value)
    if profile.formatter:
        required.add(Capability.FORMAT.value)
    required.update(proposal_capabilities)
    return frozenset(required)


def capability_gaps(
    *,
    profile: StackProfile,
    manifest: EquipmentManifest,
    proposal_capabilities: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """``required - covered``, ordered by :class:`Capability` declaration order.

    Deterministic: the iteration order is the enum's, never the input order, so
    two runs over the same inputs yield byte-identical output. A capability the
    manifest already covers never re-appears; an unknown capability that is not a
    member of :class:`Capability` is dropped (only the closed alphabet is
    surfaced).
    """
    required = required_capabilities(
        profile, proposal_capabilities=proposal_capabilities
    )
    gap = required - covered_capabilities(manifest)
    return tuple(c.value for c in Capability if c.value in gap)
