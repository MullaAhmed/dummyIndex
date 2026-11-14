"""Equipment items that GC may retire (contract 18).

An equipment item is a candidate when either:

(a) it is task-scoped and every ref is finished. A finished ref is a proposal
    ``done``/``superseded``, a closed audit (``report.md`` written), or no
    workspace. A ref to an in-flight proposal blocks the item.
(b) it is a generated specialist nobody requested (``legacy``/unrequested) that
    the baseline catalog no longer produces. Evidence-gated db/search specialists
    fall out of the baseline when the stack shows no evidence.

A task-scoped item with no refs has nothing left to wait on, so it is a review
candidate. ``add_specialist`` items are never candidates. Recommendation lives in
``recommend.py``; this module only gathers the facts.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from ..equip.enums import (
    EquipmentKind,
    EquipmentScope,
    EquipmentSource,
    ItemState,
    RequestedBy,
)
from ..equip.errors import EquipError
from ..equip.generate.catalog import build_catalog
from ..equip.generate.detect import detect_stack
from ..equip.generate.fresh import drop_generated_stems, project_slug
from ..equip.generate.render import list_convention_docs
from ..equip.lifecycle.manifest import read_manifest
from ..equip.lifecycle.status import classify_item, is_evolved, is_sourced
from ..equip.models import EquipmentItem, EquipmentManifest
from ..preflight import build_preflight_report
from .enums import CandidateKind
from .liveness import ref_finished, ref_resolvable
from .models import Candidate

_SPECIALIST_KINDS = (EquipmentKind.AGENT, EquipmentKind.SKILL)


def enumerate_equipment_candidates(context_dir: Path) -> tuple[Candidate, ...]:
    """Equipment items the GC may retire, as ``EQUIPMENT`` candidates.

    A corrupt manifest yields no candidates (``gc status`` must not crash on it).
    The baseline catalog is built only when a legacy/unrequested specialist
    needs it, since building it runs the preflight scan.
    """
    try:
        manifest = read_manifest(context_dir)
    except EquipError:
        return ()
    if not manifest.items:
        return ()

    root = context_dir.parent
    baseline: frozenset[str] | None = None
    out: list[Candidate] = []
    for item in manifest.items:
        if item.requested_by is RequestedBy.ADD_SPECIALIST:
            continue
        if (
            item.source is not EquipmentSource.GENERATED
            or item.kind not in _SPECIALIST_KINDS
        ):
            continue
        state = classify_item(root, item)
        if state is ItemState.MISSING:
            continue
        if item.scope is EquipmentScope.TASK:
            if not item.task_refs:
                signals = ("task-unreferenced",)
            elif not all(ref_resolvable(ref) for ref in item.task_refs):
                signals = ("unresolvable-ref",)
            elif _refs_finished(context_dir, item.task_refs):
                signals = ("task-finished",)
            else:
                continue
        elif _unrequested(item):
            if baseline is None:
                baseline = _baseline_names(root, context_dir, manifest)
            if item.name in baseline:
                continue
            signals = ("unproduced-baseline",)
        else:
            continue
        out.append(
            Candidate(
                kind=CandidateKind.EQUIPMENT,
                slug=item.name,
                rel_path=item.path,
                signals=signals + _state_signals(state, item),
                task_refs=item.task_refs,
            )
        )
    return tuple(sorted(out, key=lambda c: c.slug))


def _unrequested(item: EquipmentItem) -> bool:
    """Pre-v4 or backfilled items: nobody asked for them via a proposal."""
    return item.requested_by in (None, RequestedBy.LEGACY)


def _state_signals(state: ItemState, item: EquipmentItem) -> tuple[str, ...]:
    tags = [state.value]
    if is_evolved(item):
        tags.append("evolved")
    if is_sourced(item):
        tags.append("sourced")
    return tuple(tags)


def _refs_finished(context_dir: Path, refs: tuple[str, ...]) -> bool:
    """Every ref finished and none in-flight. Unknown refs count as unfinished."""
    return all(ref_finished(context_dir, ref) for ref in refs)


def _baseline_names(
    root: Path, context_dir: Path, manifest: EquipmentManifest
) -> frozenset[str]:
    """Names the baseline catalog produces: no proposal, no carry-forward.

    Mirrors ``fresh.fresh_rendered``'s preflight and generated-stem filtering,
    but passes no forced capabilities. ``fresh_rendered`` carries every applied
    specialist forward, so it cannot tell "still produced" from "legacy".
    """
    report = build_preflight_report(root)
    report = dataclasses.replace(
        report,
        project_agents=drop_generated_stems(root, manifest, report.project_agents),
    )
    decision = build_catalog(
        profile=detect_stack(context_dir),
        conventions=list_convention_docs(context_dir),
        preflight=report,
        proj=project_slug(root),
    )
    return frozenset(spec.name for spec in decision.generate)
