"""Small, explicit dispatch/result records; full logs remain artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_ENVELOPE_BYTES = 8192


def envelope(
    task_id: str,
    *,
    state: str,
    artifacts: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    blocker: str | None = None,
    next_action: str | None = None,
    **bindings: Any,
) -> dict[str, Any]:
    if not task_id or state not in {
        "planned",
        "running",
        "evaluated",
        "applied",
        "verified",
        "blocked",
    }:
        raise ValueError("A stable task ID and explicit execution state are required")
    result = dict(
        schema_version=1,
        task_id=task_id,
        state=state,
        artifacts=artifacts or [],
        evidence=evidence or [],
        blocker=blocker,
        next_action=next_action,
        bindings=bindings,
    )
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_ENVELOPE_BYTES:
        raise ValueError("Handoff exceeds 8192 bytes; move details to an artifact")
    if state == "verified" and not result["evidence"]:
        raise ValueError("Verified results require evidence references")
    return result


def task_binding(entry: dict, context_dir: Path, proposal_dir: Path) -> dict:
    """Bind shared capability and selected policy versions to one task."""
    metadata = (
        json.loads((proposal_dir / "proposal.json").read_text(encoding="utf-8"))
        if (proposal_dir / "proposal.json").is_file()
        else {}
    )
    if not isinstance(metadata, dict):
        raise ValueError("Proposal metadata must be an object")
    selected = metadata.get("policies", [])
    if not isinstance(selected, list) or len(selected) > 16:
        raise ValueError("Selected policies must be a list of at most 16 references")
    policies = []
    for policy in selected:
        if not isinstance(policy, dict) or not isinstance(policy.get("path"), str):
            raise ValueError("Selected policies require name/path bindings")
        path = Path(policy["path"])
        if not path.is_absolute():
            path = context_dir.parent / path
        raw = path.read_bytes()
        policies.append(
            dict(
                name=policy.get("name", path.stem),
                path=str(path),
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    role = entry.get("role_path")
    capability = None
    if role:
        from dummyindex.context.domains.equip import EquipmentItem, capability_identity

        manifest_path = context_dir / "equipment.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
        rows = manifest if isinstance(manifest, list) else manifest.get("items", [])
        # Dispatch has always accepted minimal legacy records. Defaults permit
        # reading their mandate, while the absent baseline stays unqualified.
        matches = [
            EquipmentItem.from_dict({"kind": "agent", "source": "installed", **row})
            for row in rows
            if isinstance(row, dict) and row.get("path") == role
        ]
        if len(matches) > 1:
            raise ValueError("Capability path is ambiguous in the manifest")
        path = Path(role)
        if not path.is_absolute():
            path = context_dir.parent / path
        if path.is_file():
            capability = (
                capability_identity(matches[0], context_dir.parent)
                if matches
                else dict(
                    path=role, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
                )
            )
    return envelope(
        entry["task_id"],
        state="planned",
        next_action=entry["text"],
        capability=capability,
        policies=policies,
        project_root=str(context_dir.parent),
        result_contract={
            "states": ["evaluated", "applied", "verified", "blocked"],
            "fields": [
                "task_id",
                "state",
                "artifacts",
                "evidence",
                "blocker",
                "next_action",
            ],
            "max_bytes": MAX_ENVELOPE_BYTES,
        },
    )
