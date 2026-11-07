"""Explicit, recoverable knowledge transfer before proposal/audit retirement."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path

from ...build.git_delta import head_commit
from ..atomic_io import _replace_bytes
from ..buildloop import parse_checklist
from ..docguard.citations import cites_disposable
from ..lesson.enums import LearningStatus
from .errors import CloseoutError
from .retirement import (
    ADMIN_FILES,
    contained,
    digest,
    durable_evidence,
    durable_references,
    receipt_path,
    text_unit,
    unit_present,
    workspace_inventory,
)
from .store import validate_slug

Learner = Callable[..., dict]

_STATES = ("planned", "implemented", "evaluated", "applied", "verified")


def learning_exit_code(learning: Mapping | None) -> int:
    """CLI exit code for a closeout's learning outcome: only ``failed`` is non-zero."""
    return 1 if learning and learning.get("status") == "failed" else 0


def closeout_workspace(
    context_dir: Path,
    kind: str,
    slug: str,
    manifest: dict,
    *,
    learner: Learner | None = None,
) -> dict:
    """Apply one reviewed transfer manifest; never delete the generated workspace.

    ``learner`` replaces the default learning pass (``evolve_learning.run_learning``).
    """
    if kind not in {"proposal", "audit"}:
        raise CloseoutError("closeout kind must be proposal or audit")
    slug = validate_slug(slug)
    context_dir = context_dir.resolve()
    family = contained(
        context_dir / ("proposals" if kind == "proposal" else "audits"), context_dir
    )
    workspace = contained(family / slug, family)
    if not workspace.is_dir():
        raise CloseoutError(f"workspace not found: {workspace}")
    with _locked(context_dir):
        try:
            receipt = _close(context_dir, workspace, kind, manifest)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise CloseoutError(
                f"invalid or unreadable closeout evidence: {exc}"
            ) from exc
    _learn_after_closeout(context_dir, workspace, kind, manifest, receipt, learner)
    return receipt


def closeout_from_file(
    context_dir: Path,
    kind: str,
    slug: str,
    path: Path,
    *,
    learner: Learner | None = None,
) -> dict:
    try:
        if path.stat().st_size > 1_000_000:
            raise CloseoutError("closeout manifest exceeds 1 MB")
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CloseoutError(f"cannot read closeout manifest: {exc}") from exc
    return closeout_workspace(context_dir, kind, slug, manifest, learner=learner)


def _close(context_dir: Path, workspace: Path, kind: str, manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise CloseoutError("closeout manifest must be an object")
    inventory = workspace_inventory(workspace)
    path = receipt_path(context_dir, kind, workspace.name)
    committed = path.read_bytes() if path.exists() else None
    old = json.loads(committed) if committed is not None else {}
    intent = path.with_suffix(".pending.json")
    previous = json.loads(intent.read_text(encoding="utf-8")) if intent.exists() else {}
    if intent.exists() and manifest.get("resume_interrupted") is not True:
        raise CloseoutError(
            "interrupted closeout: review current files and set resume_interrupted: true"
        )
    moved_ids = {
        r.get("task_id", r.get("item_id"))
        for r in [
            *old.get("pending_verification", []),
            *previous.get("pending_verification", []),
        ]
    }
    if manifest.get("reviewed_files") != inventory:
        raise CloseoutError(
            "reviewed_files must match every current workspace file hash"
        )
    state = manifest.get("state", "implemented")
    if state not in _STATES:
        raise CloseoutError(f"invalid closeout state: {state!r}")
    disposition = manifest.get("disposition", "completed")
    if disposition not in {"completed", "abandoned", "superseded"}:
        raise CloseoutError("invalid closeout disposition")
    if disposition == "completed" and state == "planned":
        raise CloseoutError("planned work cannot be reported as implemented")
    revision = head_commit(context_dir.parent)
    if "source_commit" in manifest and manifest["source_commit"] != revision:
        raise CloseoutError("source_commit does not match the current source revision")
    refs = durable_references(context_dir, workspace)
    if refs:
        raise CloseoutError(
            "repair durable references before closeout: " + ", ".join(refs[:8])
        )
    pending, resolved = _verification(context_dir, manifest, old, previous)
    reflection = manifest.get("learning_reflection")
    if reflection is not None:
        from ..evolve_gate import EvolveError
        from ..lesson import validate_lesson

        try:
            validate_lesson(reflection)
        except EvolveError as exc:
            raise CloseoutError(f"invalid learning_reflection: {exc}") from exc
    writes: dict[Path, bytes] = {}
    baseline: dict[Path, bytes | None] = {}
    if kind == "proposal":
        _proposal_state(
            workspace, state, disposition, pending, writes, baseline, moved_ids
        )
    units = _transfers(
        context_dir, workspace, manifest.get("transfers", []), writes, baseline
    )
    discarded = manifest.get("discarded", {})
    if not isinstance(discarded, dict) or any(
        not isinstance(v, str) or not v.strip() for v in discarded.values()
    ):
        raise CloseoutError("discarded entries require an explicit reason")
    classified = ADMIN_FILES | {u["source"] for u in units} | set(discarded)
    remaining = set(inventory) - classified
    if remaining:
        raise CloseoutError(
            "unreviewed knowledge/assets: " + ", ".join(sorted(remaining)[:8])
        )
    evidence = _evidence(context_dir, manifest.get("evidence", []))
    if _STATES.index(state) >= _STATES.index("evaluated") and not evidence:
        raise CloseoutError(
            "evaluated/applied/verified state requires content-bound outcome evidence"
        )
    baseline[path] = committed
    superseded = manifest.get("superseded", {})
    if not isinstance(superseded, dict) or any(
        not isinstance(v, str) or not v.strip() for v in superseded.values()
    ):
        raise CloseoutError("superseded units require an explicit reason")
    merged = {u["id"]: u for u in old.get("transfers", [])}
    for unit in units:
        prior = merged.get(unit["id"])
        if prior is not None and any(
            prior.get(key) != unit.get(key)
            for key in ("kind", "target", "sha256", "lines")
        ):
            raise CloseoutError(
                f"accepted unit ID cannot be rebound: {unit['id']}; "
                "use a new ID and explicitly supersede the prior unit"
            )
    merged.update({u["id"]: u for u in units})
    superseded = {**old.get("superseded", {}), **superseded}
    for unit in merged.values():
        target = contained(context_dir.parent / unit["target"], context_dir.parent)
        if unit["id"] not in superseded and not unit_present(
            target, unit, data=writes.get(target)
        ):
            raise CloseoutError(
                f"prior accepted unit is missing; explicitly supersede it: {unit['id']}"
            )
    after = dict(inventory)
    for target, data in writes.items():
        if target.is_relative_to(workspace):
            after[target.relative_to(workspace).as_posix()] = digest(data)
    receipt = {
        "schema_version": 1,
        "kind": kind,
        "slug": workspace.name,
        "source_commit": revision,
        "state": state,
        "disposition": disposition,
        "workspace_files": after,
        "transfers": list(merged.values()),
        "superseded": superseded,
        "discarded": discarded,
        "pending_verification": pending,
        "resolved_verification": resolved,
        "evidence": evidence,
        "ownership": _ownership(context_dir, workspace, manifest.get("ownership", {})),
        "items": json.loads((workspace / "checks.json").read_text(encoding="utf-8"))
        if (workspace / "checks.json").exists()
        else {},
    }
    encoded = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    if len(encoded) > 1_000_000:
        raise CloseoutError(
            "closeout receipt exceeds 1 MB; retain compact evidence references"
        )
    writes[path] = encoded
    if workspace_inventory(workspace) != inventory:
        raise CloseoutError("workspace changed while preparing closeout")
    _apply(writes, baseline, intent, encoded)
    return receipt


_SETTLED = {
    LearningStatus.APPLIED,
    LearningStatus.EVALUATED,
    LearningStatus.BLOCKED,
    LearningStatus.NO_ENTRY,
    LearningStatus.IGNORED,
}


def _no_mark(*_args: object) -> None:
    """Stand-in when the lazy learning imports themselves failed."""
    return None


def _learn_after_closeout(
    context_dir: Path,
    workspace: Path,
    kind: str,
    manifest: dict,
    receipt: dict,
    learner: Learner | None = None,
) -> None:
    """Run learning once; persist its status beside, never inside, the receipt.

    The receipt bytes feed the event ID, so ``receipt["learning"]`` is in-memory
    only. A settled stored status is reported as-is; ``failed`` or ``pending``
    is retried on the next closeout.
    """
    reflection = manifest.get("learning_reflection")
    if not (manifest.get("transfers") or reflection):
        return
    root = context_dir.parent
    event_id = ""
    failed = None
    mark_failed = _no_mark
    try:
        from ..evolve_gate import safe_file
        from ..evolve_learning import (
            learning_status,
            mark_failed,
            read_event,
            run_learning,
        )

        failed = safe_file(
            root,
            f".context/gc/learning/{kind}-{workspace.name}.failed.json",
            exists=False,
        )
        path = receipt_path(context_dir, kind, workspace.name)
        encoded = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
        if path.read_bytes() != encoded:
            raise CloseoutError("closeout receipt changed before learning intake")
        event_id = f"closeout:{kind}:{workspace.name}:{digest(encoded)}"
        stored = read_event(context_dir, event_id)
        if stored is not None and learning_status(stored) in _SETTLED:
            receipt["learning"] = stored
            failed.unlink(missing_ok=True)
            return
        receipt["learning"] = (learner or run_learning)(
            context_dir,
            event_id=event_id,
            evidence=[path.relative_to(root).as_posix()],
            cue="Review accepted closeout knowledge for one narrow convention update",
            reflection=reflection or None,
            tests=tuple(reflection.get("tests", [])) if reflection else (),
        )
        failed.unlink(missing_ok=True)
    except Exception as exc:  # Closeout committed; persist learning failure.
        error = f"{type(exc).__name__}: {exc}"
        event = mark_failed(context_dir, event_id, error) if event_id else None
        if event is None:
            record = {"kind": kind, "slug": workspace.name, "state": "failed"}
            record.update(status="failed", error=error)
            _replace_bytes(
                failed, (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()
            )
        receipt["learning"] = event or record
    else:
        if receipt["learning"].get("status") is None:
            receipt["learning"]["status"] = learning_status(receipt["learning"])


def _ownership(context_dir: Path, workspace: Path, value: dict) -> dict:
    if not isinstance(value, dict):
        raise CloseoutError("ownership must be an object")
    changed = value.get("changed_paths", [])
    reconciled = value.get("reconciled_paths", [])
    if not isinstance(changed, list) or not isinstance(reconciled, list):
        raise CloseoutError("ownership paths must be lists")
    records = []
    for raw in sorted(set(changed)):
        target = contained(context_dir.parent / raw, context_dir.parent)
        path = target.relative_to(context_dir.parent).as_posix()
        records.append(
            {
                "path": path,
                "sha256": digest(target.read_bytes()) if target.is_file() else None,
            }
        )
    paths = {row["path"] for row in records}
    if set(reconciled) - paths:
        raise CloseoutError(
            "reconciliation may claim only explicitly owned changed_paths"
        )
    return {
        "task_id": value.get("task_id", f"{workspace.parent.name}:{workspace.name}"),
        "session_id": value.get("session_id"),
        "changed_paths": records,
        "reconciled_paths": sorted(set(reconciled)),
    }


def _transfers(
    context_dir: Path,
    workspace: Path,
    rows: list,
    writes: dict[Path, bytes],
    baseline: dict[Path, bytes | None],
) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > 100:
        raise CloseoutError("transfers must be a list of at most 100 accepted units")
    units = []
    for row in rows:
        if not isinstance(row, dict) or row.get("kind") not in {
            "lesson",
            "decision",
            "evidence",
            "fixture",
        }:
            raise CloseoutError(
                "each transfer needs kind lesson|decision|evidence|fixture"
            )
        source = contained(workspace / row["source"], workspace)
        target = contained(context_dir.parent / row["target"], context_dir.parent)
        rel = target.relative_to(context_dir.parent).as_posix()
        allowed = rel.startswith(
            (
                ".context/features/",
                ".context/conventions/",
                ".context/playbooks/",
                ".context/equipment/",
                ".context/capabilities/",
            )
        )
        if row["kind"] == "fixture":
            allowed = rel.startswith("tests/")
        elif not target.is_file() or target.suffix != ".md":
            raise CloseoutError(
                f"knowledge target must be an existing durable home: {rel}"
            )
        if (
            not allowed
            or target.is_relative_to(workspace)
            or target.name in {"feature.json", "INDEX.json", "naming.md"}
        ):
            raise CloseoutError(f"target is not an allowed durable home: {rel}")
        raw = source.read_bytes()
        if row.get("source_sha256", digest(raw)) != digest(raw):
            raise CloseoutError(f"transfer source changed: {row['source']}")
        baseline.setdefault(target, target.read_bytes() if target.exists() else None)
        before = writes.get(target, baseline[target] or b"")
        if row["kind"] == "fixture":
            if before and before != raw:
                raise CloseoutError(
                    f"fixture destination already has different content: {rel}"
                )
            data = raw
            writes[target] = raw
            width = None
        else:
            data = text_unit(row.get("content", raw.decode("utf-8")).encode("utf-8"))
            if not data or len(data) > 65536 or data not in text_unit(raw):
                raise CloseoutError(
                    "accepted text must be a nonempty source snippet of at most 64 KiB"
                )
            if cites_disposable(data.decode("utf-8")):
                raise CloseoutError(
                    "accepted knowledge must not depend on disposable proposal/audit paths"
                )
            width = len(data.split(b"\n"))
            unit = {"kind": row["kind"], "sha256": digest(data), "lines": width}
            if not unit_present(target, unit, data=before):
                writes[target] = before.rstrip(b"\n") + b"\n\n" + data + b"\n"
        units.append(
            {
                "id": row.get(
                    "id", "unit-" + digest((rel + digest(data)).encode())[:16]
                ),
                "kind": row["kind"],
                "source": source.relative_to(workspace).as_posix(),
                "target": rel,
                "sha256": digest(data),
                "lines": width,
            }
        )
    if len({u["id"] for u in units}) != len(units):
        raise CloseoutError("duplicate accepted unit IDs")
    return units


def _pending(rows: list) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > 50:
        raise CloseoutError("pending_verification must be a list of at most 50 checks")
    result = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("description"), str)
            or not row["description"].strip()
        ):
            raise CloseoutError("pending verification requires a description")
        if cites_disposable(json.dumps(row)):
            raise CloseoutError(
                "pending verification must be usable after workspace retirement"
            )
        if "task_id" in row and "item_id" in row and row["task_id"] != row["item_id"]:
            raise CloseoutError(
                "conflicting pending verification task_id and legacy item_id"
            )
        row = dict(row)
        task_id = row.get("task_id", row.pop("item_id", None))
        if task_id is not None:
            row["task_id"] = task_id
        identity = row.get("verification_id", task_id) or (
            "verification-" + digest(row["description"].encode())[:16]
        )
        if not isinstance(identity, str) or not identity.strip():
            raise CloseoutError("pending verification requires a nonempty ID")
        row["verification_id"] = identity
        result.append(row)
    if len({row["verification_id"] for row in result}) != len(result):
        raise CloseoutError("duplicate pending verification IDs")
    return result


def _verification(
    context_dir: Path, manifest: dict, old: dict, interrupted: dict
) -> tuple[list[dict], dict]:
    """A later closeout cannot silently forget a previously moved live check."""
    pending: dict[str, dict] = {}
    for rows in (
        old.get("pending_verification", []),
        interrupted.get("pending_verification", []),
        manifest.get("pending_verification", []),
    ):
        for row in _pending(rows):
            identity = row["verification_id"]
            prior = pending.get(identity)
            if prior is not None and prior != row:
                raise CloseoutError(
                    f"pending verification identity changed: {identity}; "
                    "resolve the prior check explicitly and use a new ID"
                )
            pending[identity] = row
    resolutions = manifest.get("resolved_verification", {})
    if not isinstance(resolutions, dict):
        raise CloseoutError("resolved_verification must be an ID-to-resolution object")
    resolved = dict(old.get("resolved_verification", {}))
    for identity, resolution in resolutions.items():
        if identity not in pending:
            raise CloseoutError(
                f"resolution names an unknown pending check: {identity}"
            )
        if (
            not isinstance(resolution, dict)
            or resolution.get("state") not in {"verified", "discarded"}
            or not isinstance(resolution.get("reason"), str)
            or not resolution["reason"].strip()
        ):
            raise CloseoutError(
                "verification resolution requires state verified|discarded and a reason"
            )
        evidence = _evidence(context_dir, resolution.get("evidence", []))
        if not evidence:
            raise CloseoutError("verification resolution requires durable evidence")
        resolved[identity] = {
            **resolution,
            "evidence": evidence,
            "check": pending.pop(identity),
        }
    if set(pending) & set(resolved):
        raise CloseoutError("resolved verification IDs cannot be reused for new checks")
    return _pending(list(pending.values())), resolved


def _proposal_state(
    workspace: Path,
    state: str,
    disposition: str,
    pending: list,
    writes: dict[Path, bytes],
    baseline: dict[Path, bytes | None],
    moved_ids: set[str | None],
) -> None:
    checklist = workspace / "checklist.md"
    if checklist.exists():
        baseline[checklist] = checklist.read_bytes()
        items = parse_checklist(checklist)
        move = {
            r.get("task_id", r.get("item_id"))
            for r in pending
            if "task_id" in r or "item_id" in r
        }
        if move - {i.item_id for i in items} - moved_ids:
            raise CloseoutError("pending verification names an unknown task ID")
        if disposition == "completed" and any(
            not i.done and i.item_id not in move for i in items
        ):
            raise CloseoutError("implementation checklist is incomplete")
        if move:
            lines, index = [], 0
            for line in checklist.read_text(encoding="utf-8").splitlines(keepends=True):
                if re.match(r"^\s*- \[.\]\s+", line):
                    item = items[index]
                    index += 1
                    if item.item_id in move:
                        continue
                lines.append(line)
            writes[checklist] = "".join(lines).encode("utf-8")
    head = workspace / "proposal.json"
    baseline[head] = head.read_bytes()
    payload = json.loads(baseline[head])
    payload["status"] = "done" if disposition == "completed" else "superseded"
    payload["implementation_state"] = state
    writes[head] = (json.dumps(payload, indent=2) + "\n").encode()


def _evidence(context_dir: Path, rows: list) -> list[dict]:
    return durable_evidence(context_dir, rows)


@contextmanager
def _locked(context_dir: Path):
    from ..evolve_gate import EvolveError
    from ..evolve_promotion import project_lock

    try:
        with project_lock(context_dir.parent):
            yield
    except EvolveError as exc:
        raise CloseoutError(str(exc)) from exc


def _apply(
    writes: dict[Path, bytes],
    baseline: dict[Path, bytes | None],
    intent: Path,
    receipt_bytes: bytes,
) -> None:
    before = {
        p: baseline[p] if p in baseline else p.read_bytes() if p.exists() else None
        for p in writes
    }
    applied = []
    _replace_bytes(
        intent,
        (
            json.dumps(
                {
                    "receipt_sha256": digest(receipt_bytes),
                    "state": "pending",
                    "pending_verification": json.loads(receipt_bytes)[
                        "pending_verification"
                    ],
                }
            )
            + "\n"
        ).encode(),
    )
    try:
        for path, data in writes.items():
            current = path.read_bytes() if path.exists() else None
            if current != before[path]:
                raise CloseoutError(f"destination changed during closeout: {path}")
            _replace_bytes(path, data)
            applied.append(path)
        intent.unlink()
    except Exception:
        restored = True
        for path in reversed(applied):
            if path.read_bytes() != writes[path]:
                restored = False
                continue  # Do not overwrite a concurrent owner's edit during rollback.
            if before[path] is None:
                path.unlink()
            else:
                _replace_bytes(path, before[path])
        if restored:
            intent.unlink(missing_ok=True)
        raise
