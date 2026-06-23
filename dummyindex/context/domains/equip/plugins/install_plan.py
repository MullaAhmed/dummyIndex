"""Turn ranked candidates into an actionable install plan. Pure; no I/O.

Mechanism: a candidate from a loose collection is VENDORED (copied); everything
else is NATIVE (enabled via settings keys). Approval: **any UNTRUSTED candidate
requires explicit ``--yes``** — its ``marketplace.json``-declared surfaces are
attacker-controlled, so a ``runs_code=False`` claim cannot be relied on to waive
approval (an inert-looking entry can still ship hooks/bin in the plugin payload).
Only trusted (Anthropic-official) sources install without the gate. ``runs_code``
remains for disclosure in the plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..enums import InstallMechanism
from .blast_radius import BlastRadius, analyze_blast_radius
from .discover import Candidate


@dataclass(frozen=True)
class PlannedInstall:
    """One candidate plus the decisions the plan made about it."""

    candidate: Candidate
    blast: BlastRadius
    mechanism: InstallMechanism
    requires_approval: bool


@dataclass(frozen=True)
class InstallPlan:
    installs: tuple[PlannedInstall, ...] = ()


def _plan_one(candidate: Candidate) -> PlannedInstall:
    blast = analyze_blast_radius(candidate.plugin, trusted=candidate.trusted)
    mechanism = (
        InstallMechanism.VENDOR if candidate.is_collection else InstallMechanism.NATIVE
    )
    # Untrusted source -> always gate on --yes (declared surfaces are untrusted
    # input; an attacker can claim no code surface yet ship hooks/bin on disk).
    requires_approval = not candidate.trusted
    return PlannedInstall(
        candidate=candidate,
        blast=blast,
        mechanism=mechanism,
        requires_approval=requires_approval,
    )


def build_install_plan(candidates: tuple[Candidate, ...]) -> InstallPlan:
    return InstallPlan(installs=tuple(_plan_one(c) for c in candidates))
