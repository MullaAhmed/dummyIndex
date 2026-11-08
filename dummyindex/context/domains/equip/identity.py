"""Package identity is reusable; project bindings and loaded body bytes are local."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .models import EquipmentItem

PACKAGE_FIELDS = (
    "capability_id",
    "package_version",
    "package_source",
    "package_sha256",
    "required_tools",
    "triggers",
    "qualification_refs",
    "project_binding",
)


def capability_id(item: EquipmentItem) -> str:
    """The reusable id of ``item``: its recorded id, else ``local/<name>``."""
    return item.capability_id or f"local/{item.name}"


def capability_metadata(item: EquipmentItem) -> dict:
    return {name: getattr(item, name) for name in PACKAGE_FIELDS}


def capability_identity(
    item: EquipmentItem, project_root: Path, *, qualify_body: bool = False
) -> dict:
    """Read actual guidance before binding it; qualification requires its baseline."""
    if not item.path:
        raise ValueError(f"Capability {item.name!r} has no readable project body")
    root = project_root.resolve()
    target = (root / item.path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Capability body escapes the project")
    raw = target.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    normalized = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    baseline_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    verified = item.origin_hash in ("sha256:" + digest, "sha256:" + baseline_digest)
    if qualify_body and not verified:
        raise ValueError(
            f"Capability {item.name!r} body differs from its recorded baseline"
        )
    return dict(
        id=capability_id(item),
        version=item.version or digest[:12],
        path=item.path,
        sha256=digest,
        body_verified=verified,
        **{
            name: value
            for name, value in capability_metadata(item).items()
            if name != "capability_id"
        },
    )
