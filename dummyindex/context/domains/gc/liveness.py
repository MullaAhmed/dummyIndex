"""In-flight checks shared by proposal deletion and equipment GC candidates.

A proposal is in flight when its ``proposal.json`` status is ``in_progress`` or its
checklist has unchecked boxes. Deleting or retiring such a workspace would drop a
plan a ``/dummyindex-build`` is still executing.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..audit.errors import AuditSlugError
from ..audit.workspace import audit_dir, report_written
from ..audit.workspace import validate_slug as validate_audit_slug
from ..buildloop.checklist import counts, parse_checklist
from ..proposals.errors import ProposalSlugError
from ..proposals.store import proposal_dir
from ..proposals.store import validate_slug as validate_proposal_slug

_FINISHED_PROPOSAL_STATUSES = frozenset({"done", "superseded"})


def ref_resolvable(ref: str) -> bool:
    """Whether a task ref names a valid proposal or audit slug at all.

    A malformed kind or slug (``foo:bar``, ``proposal:``, ``proposal:../x``) can
    never resolve to a workspace, so GC surfaces it instead of carrying it forever.
    """
    kind, _, slug = ref.partition(":")
    if kind == "proposal":
        try:
            validate_proposal_slug(slug)
        except ProposalSlugError:
            return False
        return True
    if kind == "audit":
        try:
            validate_audit_slug(slug)
        except AuditSlugError:
            return False
        return True
    return False


def ref_finished(context_dir: Path, ref: str) -> bool:
    """Whether a ``proposal:<slug>`` / ``audit:<slug>`` task ref is finished.

    The one liveness definition shared by GC candidates and equipment carry-forward.
    Finished: a proposal ``done``/``superseded`` with no in-flight block (no
    ``in_progress`` status, no unchecked checklist box); an audit with ``report.md``;
    or no workspace at all. Unknown refs count as unfinished.
    """
    kind, _, slug = ref.partition(":")
    if kind == "proposal":
        try:
            target = proposal_dir(context_dir, validate_proposal_slug(slug))
        except ProposalSlugError:
            return False
        if not target.is_dir():
            return True
        if _liveness_block(target) is not None:
            return False
        return _proposal_status(target) in _FINISHED_PROPOSAL_STATUSES
    if kind == "audit":
        try:
            validate_audit_slug(slug)
            target = audit_dir(context_dir, slug)
        except AuditSlugError:
            return False
        if not target.is_dir():
            return True
        return report_written(context_dir, slug)
    return False


def _liveness_block(target: Path) -> str | None:
    """Return a refusal reason if the proposal is in-flight, else ``None``.

    In-flight = ``proposal.json`` status ``in_progress`` or any unchecked
    checklist box. An unreadable/absent file simply contributes no block.
    """
    if _proposal_status(target) == "in_progress":
        return "in-flight (status in_progress)"
    if _checklist_partial(target):
        return "in-flight (checklist partial)"
    return None


def _proposal_status(target: Path) -> str | None:
    """Read ``proposal.json``'s ``status`` field, tolerantly (``None`` on miss)."""
    path = target / "proposal.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _checklist_partial(target: Path) -> bool:
    """Whether ``checklist.md`` has any unchecked box (``done < total``).

    An absent, unparseable or empty checklist is not partial (no block).
    """
    path = target / "checklist.md"
    if not path.is_file():
        return False
    try:
        items = parse_checklist(path)
    except Exception:  # noqa: BLE001 — a malformed checklist must not block GC
        return False
    done, total = counts(items)
    if total == 0:
        return False
    return done < total
