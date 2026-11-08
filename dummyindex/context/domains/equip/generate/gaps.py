"""Capability-gap analysis: ``required(stack, proposal) - covered(manifest)``.

Pure, no I/O. Discovery, the build-loop missing-capability signal and plan-time
auto-equip all act on this deterministic gap. ``required`` is conservative: the
stack-gated code baseline plus what a proposal scopes. Specialist capabilities
enter only via ``proposal_capabilities``, so a backend repo is never told it
"needs" a frontend skill off an incidental keyword.
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

    Baseline, each gated by a real signal: ``implement``/``review``/``verify``
    for a non-``generic`` stack, ``test`` with a test runner, ``format`` with a
    formatter. ``proposal_capabilities`` (already canonical) fold in verbatim.
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

    Deterministic whatever the input order. A covered capability never
    re-appears; a value outside the :class:`Capability` alphabet is dropped.
    """
    required = required_capabilities(
        profile, proposal_capabilities=proposal_capabilities
    )
    gap = required - covered_capabilities(manifest)
    return tuple(c.value for c in Capability if c.value in gap)
