"""Closeout draft: a reviewable manifest written beside the GC cache, never applied."""

from __future__ import annotations

import json
from pathlib import Path

from ..atomic_io import write_text_atomic
from ..audit.workspace import audit_dir, report_written
from ..buildloop.checklist import counts, parse_checklist
from ..buildloop.errors import BuildLoopError
from .errors import CloseoutError
from .retirement import ADMIN_FILES, workspace_inventory
from .store import proposal_dir

_KINDS = frozenset({"proposal", "audit"})


def draft_manifest(context_dir: Path, kind: str, slug: str) -> dict:
    """Build an unedited closeout manifest for one proposal or audit workspace."""
    if kind not in _KINDS:
        raise CloseoutError("closeout kind must be proposal or audit")
    if kind == "proposal":
        workspace = proposal_dir(context_dir, slug)
    else:
        workspace = audit_dir(context_dir, slug)
    if not workspace.is_dir():
        raise CloseoutError(f"workspace not found: {workspace}")
    inventory = workspace_inventory(workspace)
    if kind == "proposal":
        done = _checklist_done(workspace / "checklist.md")
    else:
        done = report_written(context_dir, slug)
    return {
        "state": "implemented" if done else "planned",
        "disposition": "completed" if done else "abandoned",
        "reviewed_files": inventory,
        "transfers": [],
        "pending_verification": [],
        "discarded": {name: "" for name in inventory if name not in ADMIN_FILES},
    }


def draft_path(context_dir: Path, kind: str, slug: str) -> Path:
    """Where a closeout draft for ``kind``/``slug`` is written."""
    return context_dir / "cache" / "gc" / f"closeout-{kind}-{slug}.json"


def write_draft(context_dir: Path, kind: str, slug: str) -> Path:
    """Write a new draft manifest; refuse to overwrite an existing one."""
    manifest = draft_manifest(context_dir, kind, slug)
    path = draft_path(context_dir, kind, slug)
    if path.exists():
        raise CloseoutError(f"draft exists: {path}; delete it to redraft")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(manifest, indent=2) + "\n")
    return path


def _checklist_done(checklist: Path) -> bool:
    try:
        done, total = counts(parse_checklist(checklist))
    except BuildLoopError:
        return False
    return total > 0 and done == total
