"""Read `.context/features/INDEX.json` for `dummyindex context features-list --json`.

Contract: docs/schemas/features-list.json and docs/engine-contract.md section
7. The consumer checks ``schema_version`` first, so this module refuses any
index whose ``schema_version`` is not exactly the integer 1 (a bool ``True``
is rejected too). Features that break the minimum item shape are dropped and
counted in ``skipped``; they never fail the whole listing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_SCHEMA_VERSION = 1
CONFIDENCE_VALUES: frozenset[str] = frozenset({"EXTRACTED", "INFERRED"})
_FEATURE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class FeaturesListError(Exception):
    """A failure the caller reports as ``{"error": {"code", "message"}}``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def list_features(root: Path) -> dict[str, Any]:
    """The features document for the repo at ``root``.

    Raises ``FeaturesListError`` with code ``not_indexed`` when there is no
    ``.context/features/INDEX.json``, ``unsupported_schema_version`` when the
    index is not schema version 1, and ``invalid_index`` when it is not a
    readable JSON document with a ``features`` list.
    """
    context_dir = root / ".context"
    index_path = context_dir / "features" / "INDEX.json"
    if not context_dir.is_dir():
        raise FeaturesListError(
            "not_indexed",
            f"no .context/ under {root}; run `dummyindex ingest` first",
        )
    if not index_path.is_file():
        raise FeaturesListError(
            "not_indexed",
            f"no features index at {index_path}; run `dummyindex ingest` first",
        )
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FeaturesListError(
            "invalid_index", f"features INDEX.json is not readable JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise FeaturesListError("invalid_index", "features INDEX.json is not an object")

    version = payload.get("schema_version")
    if type(version) is not int or version != SUPPORTED_SCHEMA_VERSION:
        raise FeaturesListError(
            "unsupported_schema_version",
            f"features INDEX.json schema_version is {version!r}; "
            f"this dummyindex reads {SUPPORTED_SCHEMA_VERSION}",
        )
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise FeaturesListError(
            "invalid_index", "features INDEX.json has no features list"
        )

    features: list[dict[str, Any]] = []
    skipped = 0
    for entry in raw_features:
        item = _feature_item(entry)
        if item is None:
            skipped += 1
        else:
            features.append(item)
    return {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "root": str(root.resolve()),
        "features": features,
        "skipped": skipped,
    }


def _feature_item(entry: object) -> dict[str, Any] | None:
    """The schema item for one INDEX entry, or None when it breaks the minimum."""
    if not isinstance(entry, dict):
        return None
    feature_id = entry.get("feature_id")
    name = entry.get("name")
    confidence = entry.get("confidence")
    member_count = _count(entry.get("member_count"))
    if not isinstance(feature_id, str) or not _FEATURE_ID.match(feature_id):
        return None
    if not isinstance(name, str) or not name:
        return None
    if confidence not in CONFIDENCE_VALUES or member_count is None:
        return None

    summary = entry.get("summary")
    item: dict[str, Any] = {
        "feature_id": feature_id,
        "name": name,
        "summary": summary if isinstance(summary, str) else "",
        "member_count": member_count,
        "confidence": confidence,
    }
    kind = entry.get("kind")
    if isinstance(kind, str):
        item["kind"] = kind
    path = entry.get("path")
    if isinstance(path, str):
        item["path"] = path
    for key in ("file_count", "entry_point_count", "flow_count"):
        value = _count(entry.get(key))
        if value is not None:
            item[key] = value
    return item


def _count(value: object) -> int | None:
    """A non-negative integer, excluding bools."""
    if type(value) is int and value >= 0:
        return value
    return None
