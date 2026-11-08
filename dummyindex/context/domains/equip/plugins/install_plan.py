"""Turn ranked candidates into an actionable install plan. Pure; no I/O.

A loose-collection candidate is VENDORED (copied); the rest are NATIVE (settings
keys). **Every UNTRUSTED candidate needs explicit ``--yes``**: its declared surfaces
are attacker-controlled, so ``runs_code=False`` cannot waive approval (the payload
can still ship hooks/bin). Only trusted (Anthropic-official) sources skip the gate;
``runs_code`` stays for disclosure.
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
