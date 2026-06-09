"""Turn ranked candidates into an actionable install plan. Pure; no I/O.

Mechanism: a candidate from a loose collection is VENDORED (copied); everything
else is NATIVE (enabled via settings keys). Approval: a code-running candidate
from an UNTRUSTED source requires explicit ``--yes``; inert or trusted
candidates do not (spec §7).
"""
from __future__ import annotations

from dataclasses import dataclass

from .blast_radius import BlastRadius, analyze_blast_radius
from .discover import Candidate
from .enums import InstallMechanism


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
    requires_approval = blast.runs_code and not candidate.trusted
    return PlannedInstall(
        candidate=candidate,
        blast=blast,
        mechanism=mechanism,
        requires_approval=requires_approval,
    )


def build_install_plan(candidates: tuple[Candidate, ...]) -> InstallPlan:
    return InstallPlan(installs=tuple(_plan_one(c) for c in candidates))
