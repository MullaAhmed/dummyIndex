"""Content-bound per-task execution records, separate from checklist marks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...build.git_delta import head_commit
from ..atomic_io import write_text_atomic
from .checklist import (
    _flip_item_unlocked,
    _mutation_lock,
    _resolve_index,
    parse_checklist,
)
from .errors import BuildLoopError
from .models import ChecklistItem


def check_with_receipt(path: Path, key: str, receipt_path: Path) -> ChecklistItem:
    """Validate exact task/artifact identity, record its state, then close its box."""
    with _mutation_lock(path):
        return _check_with_receipt_unlocked(path, key, receipt_path)


def _check_with_receipt_unlocked(
    path: Path, key: str, receipt_path: Path
) -> ChecklistItem:
    try:
        if receipt_path.stat().st_size > 1_000_000:
            raise BuildLoopError("task receipt exceeds 1 MB")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        items = parse_checklist(path)
        item = items[_resolve_index(items, key)]
        validate_receipt(receipt, item, path.parents[3])
        receipt = {**receipt, "task_id": item.item_id}
        stored_path = path.parent / "checks.json"
        stored = (
            json.loads(stored_path.read_text(encoding="utf-8"))
            if stored_path.exists()
            else {}
        )
        stored[item.item_id] = receipt
        # Recording an execution does not claim the checkbox was updated if that fails.
        write_text_atomic(
            stored_path, json.dumps(stored, indent=2, sort_keys=True) + "\n"
        )
        return _flip_item_unlocked(path, item.item_id)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise BuildLoopError(f"invalid task receipt: {exc}") from exc


def validate_receipt(receipt: dict, item: ChecklistItem, root: Path) -> None:
    if not isinstance(receipt, dict):
        raise BuildLoopError("receipt must be an object")
    if (
        "task_id" in receipt
        and "item_id" in receipt
        and receipt["task_id"] != receipt["item_id"]
    ):
        raise BuildLoopError("conflicting task_id and legacy item_id")
    if receipt.get("task_id", receipt.get("item_id")) != item.item_id:
        raise BuildLoopError("receipt task_id does not identify the selected task")
    expected = hashlib.sha256(item.text.encode("utf-8")).hexdigest()
    if receipt.get("task_sha256", receipt.get("item_sha256")) != expected:
        raise BuildLoopError("task text changed after the receipt was produced")
    if "source_commit" not in receipt or receipt["source_commit"] != head_commit(root):
        raise BuildLoopError("task receipt source_commit is stale")
    state = receipt.get("state")
    if state not in {"implemented", "evaluated", "applied", "verified"}:
        raise BuildLoopError(
            "receipt state must be implemented|evaluated|applied|verified"
        )
    if not receipt.get("artifacts"):
        raise BuildLoopError("task receipt requires scoped artifact identities")
    if state != "implemented" and not receipt.get("evidence"):
        raise BuildLoopError(
            "evaluated/applied/verified task requires outcome evidence"
        )
    for row in [*receipt["artifacts"], *receipt.get("evidence", [])]:
        target = (root / row["path"]).resolve()
        if not target.is_relative_to(root.resolve()):
            raise BuildLoopError("task receipt path escapes the repository")
        relative = target.relative_to(root.resolve()).as_posix()
        if relative.startswith(
            (".context/proposals/", ".context/audits/", ".context/cache/")
        ):
            raise BuildLoopError(
                "task evidence must survive disposable workspace retirement"
            )
        if row.get("deleted") is True:
            if target.exists() or row.get("sha256") is not None:
                raise BuildLoopError("deleted artifact no longer matches the receipt")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
            raise BuildLoopError(f"task artifact/evidence changed: {relative}")
