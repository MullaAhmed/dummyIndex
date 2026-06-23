"""Parallel-council batch frontier — the council twin of build's `next_wave`.

The serial council loop processed one feature at a time. This module computes,
deterministically and with no LLM, the *earliest incomplete stage* across all
non-trivial features and the dispatch-units for that stage, so the council
skill can fan independent features out to parallel Task subagents.

Stage numbers match the council-log convention (`council/00-overview.md`):
specify=1, plan=2, critique=3 — extended here with flow=4, tree-enrich=5.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any

from dummyindex.context.domains.council import (
    append_reset_marker,
    is_stage_complete,
    is_standalone_complete,
)
from dummyindex.context.domains.dev_pick import (
    SubagentType,
    harvest_dep_tokens,
    pick_dev,
    read_feature_files,
)


class CouncilStage(IntEnum):
    """The ordered council stages, numbered as written to `_council-log.json`."""

    SPECIFY = 1
    PLAN = 2
    CRITIQUE = 3
    FLOW = 4
    TREE = 5


class CouncilMode(str, Enum):
    """Council depth modes (passed via `/dummyindex --mode`)."""

    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


# Deterministic critic roster by mode: (role, subagent_type) pairs.
# light = no critique; standard = one critic (security, the most universal);
# deep = all three. Replaces per-feature "relevance" judgment with a fixed,
# resumable roster — see 22-parallel-dispatch.md / 40-critique.md.
CRITIC_ROSTER: dict[CouncilMode, tuple[tuple[str, str], ...]] = {
    CouncilMode.LIGHT: (),
    CouncilMode.STANDARD: (("critic-security", "Security Engineer"),),
    CouncilMode.DEEP: (
        ("critic-database", "Data Engineer"),
        ("critic-security", "Security Engineer"),
        ("critic-product", "general-purpose"),
    ),
}


def active_stages(mode: CouncilMode, *, tree_enrich: bool) -> tuple[CouncilStage, ...]:
    """The stages that actually run for ``mode``.

    light = dev only (specify) + flow; standard/deep add plan + critique.
    Tree-enrich is mode-gated and appended only when ``tree_enrich`` is set.
    """
    stages: list[CouncilStage] = [CouncilStage.SPECIFY]
    if mode in (CouncilMode.STANDARD, CouncilMode.DEEP):
        stages.append(CouncilStage.PLAN)
        stages.append(CouncilStage.CRITIQUE)
    stages.append(CouncilStage.FLOW)
    if tree_enrich:
        stages.append(CouncilStage.TREE)
    return tuple(stages)


def _pipeline_feature_ids(
    features_dir: Path, feature_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Drop Outcome-C standalone features — done by design (stage-0-only log,
    spec.md only), never part of the pipeline frontier."""
    return tuple(
        fid for fid in feature_ids if not is_standalone_complete(features_dir, fid)
    )


def earliest_incomplete_stage(
    features_dir: Path,
    feature_ids: tuple[str, ...],
    *,
    mode: CouncilMode,
    tree_enrich: bool,
) -> CouncilStage | None:
    """The lowest active stage not yet complete for *every* feature, or None.

    A stage ``S`` is the frontier iff at least one feature has not completed it.
    Returns None when every feature has completed every active stage.
    Standalone-complete features (Outcome C) are exempt.
    """
    pipeline_ids = _pipeline_feature_ids(features_dir, feature_ids)
    for stage in active_stages(mode, tree_enrich=tree_enrich):
        if any(
            not is_stage_complete(features_dir, fid, int(stage)) for fid in pipeline_ids
        ):
            return stage
    return None


def force_recouncil(
    features_dir: Path,
    feature_ids: tuple[str, ...],
    *,
    mode: CouncilMode,
    tree_enrich: bool,
) -> tuple[str, ...]:
    """Start a forced re-council for already-complete scoped features.

    Appends a reset marker (see ``council.append_reset_marker``) ONLY to
    features with no incomplete active stage — a feature mid-run is left
    alone, so re-running ``council-batch --next --feature ID --force`` while
    the forced run is in flight is idempotent and the loop converges.
    Returns the feature ids actually reset.
    """
    reset: list[str] = []
    for fid in feature_ids:
        stage = earliest_incomplete_stage(
            features_dir, (fid,), mode=mode, tree_enrich=tree_enrich
        )
        if stage is None:
            append_reset_marker(features_dir, fid)
            reset.append(fid)
    return tuple(reset)


def _prior_active_stage(
    stage: CouncilStage, mode: CouncilMode, *, tree_enrich: bool
) -> CouncilStage | None:
    """The active stage immediately before ``stage``, or None if it is first."""
    stages = active_stages(mode, tree_enrich=tree_enrich)
    idx = stages.index(stage)
    return stages[idx - 1] if idx > 0 else None


def _feature_ready_for(
    features_dir: Path,
    feature_id: str,
    stage: CouncilStage,
    mode: CouncilMode,
    *,
    tree_enrich: bool,
) -> bool:
    """True iff ``feature_id`` needs ``stage`` and its prior active stage is done."""
    if is_stage_complete(features_dir, feature_id, int(stage)):
        return False  # already done this stage
    prior = _prior_active_stage(stage, mode, tree_enrich=tree_enrich)
    if prior is None:
        return True
    return is_stage_complete(features_dir, feature_id, int(prior))


@dataclass(frozen=True)
class DispatchUnit:
    """One Task-tool agent invocation the council skill must launch."""

    feature_id: str
    stage: int
    role: str  # council-log --agent AND persona-file selector
    subagent_type: str  # the Task-tool agent to launch
    framework: str | None  # dev-authored stages only; else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "stage": self.stage,
            "role": self.role,
            "subagent_type": self.subagent_type,
            "framework": self.framework,
        }


@dataclass(frozen=True)
class Batch:
    """The dispatch frontier for one `--next` call."""

    complete: bool
    stage: CouncilStage | None
    units: tuple[DispatchUnit, ...]


def _dev_unit(
    feature_id: str, stage: CouncilStage, features_dir: Path, dep_tokens: frozenset[str]
) -> DispatchUnit:
    """A dev-authored unit (specify / flow / tree) with stack-resolved subagent."""
    try:
        files = read_feature_files(features_dir, feature_id)
    except FileNotFoundError:
        files = ()
    pick = pick_dev(feature_files=files, dep_tokens=dep_tokens)
    return DispatchUnit(
        feature_id=feature_id,
        stage=int(stage),
        role="dev",
        # .value, never str(): str() on a (str, Enum) member is the
        # 'SubagentType.FRONTEND' repr on Python 3.11+, not the agent name.
        subagent_type=pick.subagent_type.value,
        framework=pick.framework,
    )


def _units_for_feature(
    feature_id: str,
    stage: CouncilStage,
    features_dir: Path,
    dep_tokens: frozenset[str],
    mode: CouncilMode,
) -> tuple[DispatchUnit, ...]:
    """Expand one feature at ``stage`` into its dispatch-unit(s)."""
    if stage in (CouncilStage.SPECIFY, CouncilStage.FLOW, CouncilStage.TREE):
        return (_dev_unit(feature_id, stage, features_dir, dep_tokens),)
    if stage == CouncilStage.PLAN:
        return (
            DispatchUnit(
                feature_id=feature_id,
                stage=int(stage),
                role="architect",
                subagent_type=SubagentType.BACKEND.value,
                framework=None,
            ),
        )
    if stage == CouncilStage.CRITIQUE:
        return tuple(
            DispatchUnit(
                feature_id=feature_id,
                stage=int(stage),
                role=role,
                subagent_type=subagent_type,
                framework=None,
            )
            for role, subagent_type in CRITIC_ROSTER[mode]
        )
    return ()


def next_batch(
    features_dir: Path,
    repo_root: Path,
    feature_ids: tuple[str, ...],
    *,
    mode: CouncilMode,
    cap: int,
    tree_enrich: bool,
) -> Batch:
    """Compute the next dispatch batch — the council twin of ``next_wave``.

    Picks the earliest incomplete active stage, gathers the features ready for
    it (prior stage complete), expands each to its unit(s), and returns up to
    ``cap`` units (agent-bounded; a single feature's units are never split).
    """
    if cap < 1:
        raise ValueError(f"cap must be >= 1, got {cap}")

    pipeline_ids = _pipeline_feature_ids(features_dir, feature_ids)
    stage = earliest_incomplete_stage(
        features_dir, pipeline_ids, mode=mode, tree_enrich=tree_enrich
    )
    if stage is None:
        return Batch(complete=True, stage=None, units=())

    dep_tokens = harvest_dep_tokens(repo_root)
    collected: list[DispatchUnit] = []
    for fid in pipeline_ids:
        if not _feature_ready_for(
            features_dir, fid, stage, mode, tree_enrich=tree_enrich
        ):
            continue
        feature_units = _units_for_feature(fid, stage, features_dir, dep_tokens, mode)
        if not feature_units:
            continue
        if collected and len(collected) + len(feature_units) > cap:
            break  # honour cap at feature granularity (never split a feature)
        collected.extend(feature_units)
    return Batch(complete=False, stage=stage, units=tuple(collected))
