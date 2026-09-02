"""Tests for the drift-ack store (``context.domains.drift_acks``).

The store is append-only gitignored cache state under
``.context/cache/drift-acks.json``: read tolerates a missing/corrupt file
(the ``_load_memo`` pattern), writes are atomic, and clear is idempotent.
Expiry is data, not behaviour: an entry only suppresses while the consumer's
sha comparison matches, so the expiry case here exercises the observable
end-to-end contract through ``compute_drift``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from dummyindex.context.build.reconcile import blob_sha
from dummyindex.context.domains.drift_acks import (
    ACKS_SCHEMA_VERSION,
    acks_path,
    append_ack,
    clear_acks,
    read_acks,
)
from dummyindex.context.drift import compute_drift

_NOW = datetime(2026, 8, 23, 12, 0, 0)


@pytest.mark.unit
def test_read_acks_empty_when_absent(tmp_path: Path) -> None:
    assert read_acks(tmp_path) == []


@pytest.mark.unit
def test_append_then_read_roundtrip_shape(tmp_path: Path) -> None:
    entry = append_ack(
        tmp_path,
        feature_id="auth",
        acked_sha="abc123",
        path="auth.py",
        reason="false positive",
        now=_NOW,
    )
    assert entry == {
        "feature_id": "auth",
        "path": "auth.py",
        "acked_sha": "abc123",
        "reason": "false positive",
        "ts": _NOW.isoformat(),
    }
    acks = read_acks(tmp_path)
    assert len(acks) == 1 and acks[0]["acked_sha"] == "abc123"
    # Optional fields stay explicit-null when omitted (stable envelope).
    bare = append_ack(tmp_path, feature_id="b", acked_sha="d", now=_NOW)
    assert bare["path"] is None and bare["reason"] is None


@pytest.mark.unit
def test_append_is_additive_and_ordered(tmp_path: Path) -> None:
    for i in range(3):
        append_ack(tmp_path, feature_id=f"f{i}", acked_sha=str(i), now=_NOW)
    assert [a["feature_id"] for a in read_acks(tmp_path)] == ["f0", "f1", "f2"]


@pytest.mark.unit
def test_write_is_atomic_with_parent_dirs_and_schema_marker(
    tmp_path: Path,
) -> None:
    append_ack(tmp_path, feature_id="x", acked_sha="s", now=_NOW)
    payload = json.loads(acks_path(tmp_path).read_text(encoding="utf-8"))
    assert payload["schema_version"] == ACKS_SCHEMA_VERSION == 1
    assert isinstance(payload["acks"], list)


@pytest.mark.unit
def test_corrupt_store_reads_back_empty_never_raises(tmp_path: Path) -> None:
    path = acks_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for bad in ("{corrupt", "null", '"str"', '{"acks": 42}', "[]"):
        path.write_text(bad, encoding="utf-8")
        assert read_acks(tmp_path) == []
    # Non-dict entries inside a valid list are dropped, not fatal.
    path.write_text('{"acks": [{"ok": 1}, "junk", 7]}', encoding="utf-8")
    assert [a.get("ok") for a in read_acks(tmp_path)] == [1]


@pytest.mark.unit
def test_clear_returns_count_and_is_idempotent(tmp_path: Path) -> None:
    assert clear_acks(tmp_path) == 0  # nothing there yet
    for i in range(2):
        append_ack(tmp_path, feature_id=f"f{i}", acked_sha=str(i), now=_NOW)
    assert clear_acks(tmp_path) == 2
    assert clear_acks(tmp_path) == 0
    assert read_acks(tmp_path) == []


def _make_feature(project_root: Path, feature_id: str, files: list[str]) -> None:
    d = project_root / ".context" / "features" / feature_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "feature.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_id": feature_id,
                "kind": "community",
                "name": feature_id,
                "files": files,
                "members": [],
                "entry_points": [],
                "flow_ids": [],
            }
        ),
        encoding="utf-8",
    )
    (d / "spec.md").write_text("# x\n", encoding="utf-8")


@pytest.mark.integration
def test_recorded_ack_expires_when_file_edited(tmp_path: Path) -> None:
    """End-to-end expiry: an ack suppresses today's row; any edit re-reports."""
    src = tmp_path / "svc.py"
    src.write_text("def f(): return 1\n", encoding="utf-8")
    os.utime(src, (1000.0, 1000.0))
    spec = tmp_path / ".context" / "features" / "auth" / "spec.md"
    _make_feature(tmp_path, "auth", ["svc.py"])
    os.utime(spec, (500.0, 500.0))

    append_ack(
        tmp_path / ".context",
        feature_id="auth",
        acked_sha=blob_sha(src.read_bytes()),
        path="svc.py",
        now=_NOW,
    )
    report = compute_drift(tmp_path)
    assert report.rows == () and report.acked_count == 1

    src.write_text("def f(): return 2\n", encoding="utf-8")
    os.utime(src, (1200.0, 1200.0))
    report = compute_drift(tmp_path)
    assert report.rows != () and report.acked_count == 0
