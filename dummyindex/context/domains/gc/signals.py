"""Deterministic signal tags for one GC candidate — no verdict.

``classify`` is pure: it reads the ``Candidate``'s fields plus the workspace's own
files and never shells git. ``orphan-empty`` compares only ``plan.md`` and
``checklist.md`` with their scaffold templates (title from ``proposal.json``):
``proposals/store.py:apply_consistency`` adds a ``## Consistency`` block to
``spec.md`` right after scaffolding, so ``spec.md`` never byte-matches.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..audit.workspace import report_written
from ..buildloop.checklist import counts, parse_checklist
from ..buildloop.errors import BuildLoopError
from ..proposals.store import (
    _checklist_template,
    _plan_template,
    proposal_dir,
)
from .enums import CandidateKind
from .models import Candidate


def classify(candidate: Candidate, context_dir: Path, root: Path) -> tuple[str, ...]:
    """Return the deterministic signal tags for ``candidate``, in this order.

    ``status:<value>``; ``orphan-empty`` and ``checklist-complete`` /
    ``checklist-partial`` (proposals/archived only); ``report-written`` (audits
    only); ``untracked``; ``age-<n>d``. ``root`` is unused, accepted for
    signature symmetry with the rest of the domain.
    """
    signals: list[str] = []

    if candidate.status is not None:
        signals.append(f"status:{candidate.status}")

    # `orphan-empty` and checklist completion are proposal-shaped concerns:
    # they read the scaffolded markdown of a proposal/archived workspace and
    # are meaningless for an audit (whose layout has no plan/checklist).
    if candidate.kind in (CandidateKind.PROPOSAL, CandidateKind.ARCHIVED):
        workspace = proposal_dir(context_dir, candidate.slug)
        if _is_orphan_empty(workspace):
            signals.append("orphan-empty")
        completion = _checklist_completion(workspace)
        if completion is not None:
            signals.append(completion)
    elif candidate.kind is CandidateKind.AUDIT:
        if report_written(context_dir, candidate.slug):
            signals.append("report-written")

    if not candidate.tracked:
        signals.append("untracked")

    if candidate.age_days is not None:
        signals.append(f"age-{candidate.age_days}d")

    return tuple(signals)


def _read_title(workspace: Path) -> str:
    """Read the proposal ``title`` from ``proposal.json`` (``""`` if unreadable).

    ``""`` won't byte-match a real scaffold, so an unreadable head is
    (correctly) never reported as ``orphan-empty``.
    """
    head = workspace / "proposal.json"
    try:
        payload = json.loads(head.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    title = payload.get("title", "")
    return title if isinstance(title, str) else ""


def _is_orphan_empty(workspace: Path) -> bool:
    """Whether ``plan.md`` + ``checklist.md`` are still the raw scaffold templates.

    Deliberately ignores ``spec.md`` (``apply_consistency`` rewrites it).
    """
    plan_path = workspace / "plan.md"
    checklist_path = workspace / "checklist.md"
    if not plan_path.is_file() or not checklist_path.is_file():
        return False
    title = _read_title(workspace)
    try:
        plan = plan_path.read_text(encoding="utf-8")
        checklist = checklist_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return plan == _plan_template(title) and checklist == _checklist_template(title)


def _checklist_completion(workspace: Path) -> str | None:
    """``checklist-complete`` / ``checklist-partial`` / ``None`` for a workspace.

    - ``done == total > 0`` → ``checklist-complete``
    - ``0 < done < total`` or any unchecked item → ``checklist-partial``
    - empty checklist / no parseable checklist → ``None`` (neither tag)
    """
    checklist_path = workspace / "checklist.md"
    try:
        items = parse_checklist(checklist_path)
    except BuildLoopError:
        return None
    done, total = counts(items)
    if total == 0:
        return None
    if done == total:
        return "checklist-complete"
    return "checklist-partial"
