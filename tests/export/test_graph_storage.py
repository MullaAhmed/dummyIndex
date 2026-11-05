"""Lossless bounded graph generations, legacy reads and failed publication."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.export import storage
from dummyindex.export.storage import (
    GraphStorageError,
    read_graph_payload,
    write_graph_payload,
)

pytestmark = pytest.mark.unit


def _payload(count: int = 60) -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {"name": "kept", "nested": {"enabled": True, "value": None}},
        "nodes": [
            {
                "id": f"n-{i:04}",
                "label": f"symbol {i}",
                "source_file": "src/module.py",
                "notes": "éλ" * 90,
                "line": i + 1,
            }
            for i in range(count)
        ],
        "links": [
            {
                "source": f"n-{i:04}",
                "target": "n-0000",
                "key": i,
                "relation": "calls",
                "_src": "n-0000",
                "_tgt": f"n-{i:04}",
                "weight": 0.5,
            }
            for i in range(count)
        ],
        "hyperedges": [
            {
                "members": ["n-0000", "n-0001"],
                "kind": "shared",
                "custom": [None, True, 1],
            }
        ],
        "custom_top_level": {"preserved": True},
    }


@pytest.mark.integration
def test_committed_shards_survive_autocrlf_checkout(tmp_path):
    import subprocess

    from dummyindex.context.build.runner import ensure_context_gitattributes

    context = tmp_path / ".context"
    path = context / "features/symbol-graph.json"
    payload = _payload()
    write_graph_payload(payload, path, max_file_bytes=4096)
    ensure_context_gitattributes(context)
    subprocess.run(
        ["git", "init", "-q", str(tmp_path)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-c", "core.autocrlf=true", "add", ".context"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    manifest = json.loads(path.read_bytes())
    shard = path.parent / manifest["shards"][0]["path"]
    path.unlink()
    shard.unlink()
    subprocess.run(
        ["git", "-c", "core.autocrlf=true", "checkout", "--", ".context/features"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert read_graph_payload(path) == payload


def _write_sharded(tmp_path: Path) -> tuple[Path, dict, dict]:
    path = tmp_path / "symbol-graph.json"
    payload = _payload()
    write_graph_payload(payload, path, max_file_bytes=4096)
    manifest = json.loads(path.read_bytes())
    assert manifest["format"] == "dummyindex-symbol-graph"
    return path, payload, manifest


def test_small_graph_is_compact_json_with_hyperedges_once(tmp_path: Path) -> None:
    payload = _payload(2)
    payload["graph"]["hyperedges"] = payload["hyperedges"]
    path = tmp_path / "graph.json"
    write_graph_payload(payload, path)
    content = path.read_bytes()
    assert content.endswith(b"\n") and b"\n " not in content
    loaded = read_graph_payload(path)
    assert loaded["hyperedges"] == payload["hyperedges"]
    assert "hyperedges" not in loaded["graph"]
    assert payload["graph"]["hyperedges"] == payload["hyperedges"]
    assert loaded["graph"]["nested"] == payload["graph"]["nested"]


def test_bounded_shards_round_trip_all_fields_and_external_ids(tmp_path: Path) -> None:
    path, payload, manifest = _write_sharded(tmp_path)
    assert path.stat().st_size <= 4096
    assert manifest["counts"] == {"nodes": 60, "links": 60, "hyperedges": 1}
    for shard in manifest["shards"]:
        file = tmp_path / shard["path"]
        assert file.stat().st_size == shard["bytes"] <= 4096
    assert read_graph_payload(path) == payload
    external = {
        "id": "https://example.test/external-symbol",
        "source_file": "src/external.py",
        "all": {"false": False},
    }
    payload["nodes"].append(external)
    write_graph_payload(payload, path, max_file_bytes=4096)
    assert external in read_graph_payload(path)["nodes"]


def test_sharded_generations_are_deterministic_across_record_orders_and_names(
    tmp_path: Path,
) -> None:
    payload = _payload()
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    write_graph_payload(payload, first, max_file_bytes=4096)
    payload["nodes"].reverse()
    payload["links"].reverse()
    write_graph_payload(payload, second, max_file_bytes=4096)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    "payload",
    [
        {"nodes": [{"id": "a"}]},
        {"links": []},
        {"edges": [{"source": "a", "target": "b"}]},
    ],
)
def test_legacy_partial_payloads_keep_consumer_validation_policy(
    tmp_path: Path, payload: dict
) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = read_graph_payload(path)
    if "edges" in payload:
        assert loaded == {"links": payload["edges"]}
    else:
        assert loaded == payload


def test_legacy_duplicate_hyperedges_are_read_without_losing_graph_attributes(
    tmp_path: Path,
) -> None:
    payload = _payload(1)
    payload["graph"]["hyperedges"] = payload["hyperedges"]
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert read_graph_payload(path) == payload


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "truncated",
        "bytes",
        "count",
        "total",
        "hash",
        "payload_hash",
        "version",
        "path",
    ],
)
def test_corrupt_generation_never_returns_a_partial_graph(
    tmp_path: Path, damage: str
) -> None:
    path, _, manifest = _write_sharded(tmp_path)
    descriptor = manifest["shards"][0]
    shard = tmp_path / descriptor["path"]
    if damage == "missing":
        shard.unlink()
    elif damage == "truncated":
        shard.write_bytes(shard.read_bytes()[:-5])
    elif damage == "bytes":
        descriptor["bytes"] -= 1
    elif damage == "count":
        descriptor["count"] += 1
    elif damage == "total":
        manifest["counts"]["nodes"] += 1
    elif damage == "hash":
        descriptor["sha256"] = "0" * 64
    elif damage == "payload_hash":
        manifest["graph_sha256"] = "0" * 64
    elif damage == "version":
        manifest["version"] = 999
    else:
        descriptor["path"] = "../outside.json"
    path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    with pytest.raises((GraphStorageError, OSError)):
        read_graph_payload(path)


@pytest.mark.parametrize("oversize", ["record", "metadata", "manifest"])
def test_unrepresentable_input_preserves_previous_generation(
    tmp_path: Path, oversize: str
) -> None:
    path = tmp_path / "graph.json"
    original = _payload(1)
    write_graph_payload(original, path)
    before = path.read_bytes()
    payload = _payload(300 if oversize == "manifest" else 2)
    cap = 700 if oversize == "manifest" else 4096
    if oversize == "record":
        payload["nodes"][0]["notes"] = "x" * 5000
    elif oversize == "metadata":
        payload["graph"]["notes"] = "x" * 5000
    with pytest.raises(GraphStorageError, match="cap"):
        write_graph_payload(payload, path, max_file_bytes=cap)
    assert path.read_bytes() == before
    assert read_graph_payload(path) == original
    assert not (tmp_path / "symbol-graph.parts").exists()


def test_failed_manifest_publish_keeps_previous_graph_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, original, _ = _write_sharded(tmp_path)
    before = path.read_bytes()
    changed = _payload(80)
    publish = storage._atomic_write

    def fail_manifest(destination: Path, content: bytes) -> None:
        if destination == path:
            raise OSError("interrupted before manifest publication")
        publish(destination, content)

    monkeypatch.setattr(storage, "_atomic_write", fail_manifest)
    with pytest.raises(OSError, match="publication"):
        write_graph_payload(changed, path, max_file_bytes=4096)
    assert path.read_bytes() == before
    assert read_graph_payload(path) == original


def test_reader_holding_previous_manifest_can_finish_after_publication(
    tmp_path: Path,
) -> None:
    path, original, _ = _write_sharded(tmp_path)
    previous = tmp_path / "previous-manifest.json"
    previous.write_bytes(path.read_bytes())
    changed = _payload(80)
    write_graph_payload(changed, path, max_file_bytes=4096)
    assert read_graph_payload(path) == changed
    assert read_graph_payload(previous) == original


def test_conflicting_hyperedge_copies_are_not_silently_discarded(
    tmp_path: Path,
) -> None:
    payload = _payload(1)
    payload["graph"]["hyperedges"] = [{"different": True}]
    with pytest.raises(GraphStorageError, match="conflicting hyperedge"):
        write_graph_payload(payload, tmp_path / "graph.json")


def test_boolean_and_number_hyperedge_attributes_are_not_equivalent(
    tmp_path: Path,
) -> None:
    payload = _payload(1)
    payload["hyperedges"] = [{"value": 1}]
    payload["graph"]["hyperedges"] = [{"value": True}]
    with pytest.raises(GraphStorageError, match="conflicting hyperedge"):
        write_graph_payload(payload, tmp_path / "graph.json")


def test_nonregular_artifact_is_rejected_before_opening(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    path.mkdir()
    with pytest.raises(GraphStorageError, match="regular file"):
        read_graph_payload(path)
    with pytest.raises(GraphStorageError, match="regular file"):
        write_graph_payload(_payload(1), path)


def test_linked_shard_directory_is_rejected_without_touching_target(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    directory = tmp_path / "features"
    directory.mkdir()
    try:
        (directory / "symbol-graph.parts").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(GraphStorageError, match="symlink"):
        write_graph_payload(_payload(), directory / "graph.json", max_file_bytes=4096)
    assert list(outside.iterdir()) == []


def test_linked_graph_file_is_never_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    path = tmp_path / "graph.json"
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(GraphStorageError, match="symlink"):
        read_graph_payload(path)
    with pytest.raises(GraphStorageError, match="symlink"):
        write_graph_payload(_payload(1), path)
    assert outside.read_text() == "{}"


def test_ninety_five_mib_class_graph_is_lossless_and_every_file_is_bounded(
    tmp_path: Path,
) -> None:
    # Shared in-memory text keeps fixture construction small; JSON is >95 MiB.
    text = "x" * 65_536
    payload = {
        "directed": False,
        "multigraph": False,
        "graph": {"retained": True},
        "nodes": [{"id": f"n-{i:04}", "rationale": text} for i in range(1536)],
        "links": [],
        "hyperedges": [],
    }
    path = tmp_path / "graph.json"
    write_graph_payload(payload, path)
    manifest = json.loads(path.read_bytes())
    assert sum(s["bytes"] for s in manifest["shards"]) >= 95 * 1024 * 1024
    assert path.stat().st_size <= storage.DEFAULT_MAX_FILE_BYTES
    assert all(
        (tmp_path / s["path"]).stat().st_size <= storage.DEFAULT_MAX_FILE_BYTES
        for s in manifest["shards"]
    )
    assert read_graph_payload(path) == payload
