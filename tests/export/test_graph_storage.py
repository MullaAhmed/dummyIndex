"""Lossless bounded graph generations, legacy reads and failed publication."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path, PurePosixPath

import pytest

from dummyindex.export import storage
from dummyindex.export.storage import (
    GraphStorageError,
    read_graph_payload,
    shard_names,
    write_graph_payload,
)

pytestmark = pytest.mark.unit

_AGED = 3600  # Seconds; comfortably past storage.SHARD_GRACE_SECONDS.


def _age(directory: Path) -> None:
    """Backdate every regular, unlinked entry so the prune grace has expired."""
    old = time.time() - _AGED
    for entry in directory.iterdir():
        if entry.is_file() and not entry.is_symlink():
            os.utime(entry, (old, old))


def _link_dir(link: Path, target: Path) -> None:
    """Create a directory symlink, or a junction where only those are allowed."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            pytest.skip("symlink creation unavailable on this host")
    import _winapi  # Windows-only; junctions need no symlink privilege.

    _winapi.CreateJunction(str(target), str(link))


def _seed(parts: Path, *indices: int) -> list[Path]:
    seeded = [parts / f"{i:064x}.json" for i in indices]
    for orphan in seeded:
        orphan.write_bytes(b'{"orphan":true}\n')
    return seeded


@pytest.mark.parametrize(
    "relative",
    [
        "C:relative.json",
        "C:/absolute.json",
        "//server/share/file.json",
        r"\\server\share\file.json",
        "//?/C:/file.json",
        "//./C:/file.json",
        "../escape.json",
    ],
)
def test_storage_rejects_drive_unc_and_parent_paths(tmp_path: Path, relative: str):
    with pytest.raises(GraphStorageError, match="unsafe graph storage path"):
        storage._plain_path(tmp_path, relative)


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


def _write_sharded(tmp_path: Path, count: int = 60) -> tuple[Path, dict, dict]:
    path = tmp_path / "symbol-graph.json"
    payload = _payload(count)
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
    parts = tmp_path / "symbol-graph.parts"
    orphans = _seed(parts, 1, 2, 3)
    _age(parts)
    before = path.read_bytes()
    existing = set(os.listdir(parts))
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
    # A failed publish prunes nothing: aged orphans and old shards all remain.
    assert all(orphan.exists() for orphan in orphans)
    assert existing <= set(os.listdir(parts))


def test_superseded_manifest_fails_closed_after_publication(
    tmp_path: Path,
) -> None:
    path, _, _ = _write_sharded(tmp_path)
    previous = tmp_path / "previous-manifest.json"
    previous.write_bytes(path.read_bytes())
    _age(tmp_path / "symbol-graph.parts")
    changed = _payload(80)
    write_graph_payload(changed, path, max_file_bytes=4096)
    assert read_graph_payload(path) == changed
    with pytest.raises(GraphStorageError, match="rebuild --changed"):
        read_graph_payload(previous)


def test_three_publishes_retain_only_the_current_generation(tmp_path: Path) -> None:
    path = tmp_path / "symbol-graph.json"
    parts = tmp_path / "symbol-graph.parts"
    generations: list[frozenset[str]] = []
    for count in (60, 80, 100):
        if parts.exists():
            _age(parts)
        payload = _payload(count)
        write_graph_payload(payload, path, max_file_bytes=4096)
        generations.append(shard_names(path))
    assert set(os.listdir(parts)) == shard_names(path) == generations[-1]
    retired = generations[0] - generations[-1]
    assert retired, "fixture must retire some first-generation shards"
    assert not any((parts / name).exists() for name in retired)
    assert read_graph_payload(path) == payload


def test_aged_orphans_are_pruned_and_young_ones_survive(tmp_path: Path) -> None:
    path, _, _ = _write_sharded(tmp_path)
    parts = tmp_path / "symbol-graph.parts"
    orphans = _seed(parts, *range(5))
    _age(parts)
    (young,) = _seed(parts, 99)
    changed = _payload(80)
    write_graph_payload(changed, path, max_file_bytes=4096)
    assert not any(orphan.exists() for orphan in orphans)
    assert young.exists()
    assert read_graph_payload(path) == changed


def test_plain_publish_after_sharded_removes_the_parts_directory(
    tmp_path: Path,
) -> None:
    path, _, _ = _write_sharded(tmp_path)
    _age(tmp_path / "symbol-graph.parts")
    small = _payload(2)
    write_graph_payload(small, path, max_file_bytes=4096)
    assert "format" not in json.loads(path.read_bytes())
    assert not (tmp_path / "symbol-graph.parts").exists()
    assert read_graph_payload(path) == small


@pytest.mark.parametrize("link_kind", ["symlink", "junction"])
def test_prune_never_deletes_foreign_names_nonfiles_or_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_kind: str
) -> None:
    path, _, _ = _write_sharded(tmp_path)
    parts = tmp_path / "symbol-graph.parts"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "target.json"
    target.write_bytes(b"outside bytes")
    link = parts / f"{7:064x}.json"
    if link_kind == "symlink":
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation unavailable on this host")
    elif os.name == "nt":
        _link_dir(link, outside)
    else:
        pytest.skip("junctions are Windows-only")
    foreign = [parts / "notes.txt", parts / ".x.tmp"]
    for file in foreign:
        file.write_bytes(b"keep")
    directory = parts / f"{8:064x}.json"
    directory.mkdir()
    _age(parts)
    # Link mtimes cannot be backdated portably; make every entry count as aged.
    monkeypatch.setattr(storage, "SHARD_GRACE_SECONDS", -_AGED)
    changed = _payload(80)
    write_graph_payload(changed, path, max_file_bytes=4096)
    assert all(file.read_bytes() == b"keep" for file in foreign)
    assert directory.is_dir()
    assert os.path.lexists(link)
    assert target.read_bytes() == b"outside bytes"
    assert sorted(p.name for p in outside.iterdir()) == ["target.json"]
    assert read_graph_payload(path) == changed


def test_unlink_failure_warns_and_publication_still_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _, _ = _write_sharded(tmp_path)
    parts = tmp_path / "symbol-graph.parts"
    stuck, other = _seed(parts, 1, 2)
    _age(parts)
    real_unlink = os.unlink

    def unlink(target, *args, **kwargs):
        # Fail only the one seeded shard; temp-file cleanup keeps working.
        if os.path.basename(os.fspath(target)) == stuck.name:
            raise PermissionError("shard locked by another process")
        return real_unlink(target, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)
    changed = _payload(80)
    with pytest.warns(UserWarning, match="shard locked") as caught:
        write_graph_payload(changed, path, max_file_bytes=4096)
    assert len([w for w in caught if issubclass(w.category, UserWarning)]) == 1
    assert stuck.exists() and not other.exists()
    assert read_graph_payload(path) == changed


def test_missing_shard_names_the_rebuild_command(tmp_path: Path) -> None:
    path, _, manifest = _write_sharded(tmp_path)
    (tmp_path / manifest["shards"][0]["path"]).unlink()
    with pytest.raises(GraphStorageError, match="rebuild --changed"):
        read_graph_payload(path)


@pytest.mark.parametrize("damage", [b"corrupt", b"x" * 5000])
def test_preexisting_shard_with_wrong_bytes_is_rewritten(
    tmp_path: Path, damage: bytes
) -> None:
    path, payload, manifest = _write_sharded(tmp_path)
    shard = tmp_path / manifest["shards"][0]["path"]
    expected = shard.read_bytes()
    shard.write_bytes(damage)
    write_graph_payload(payload, path, max_file_bytes=4096)
    assert shard.read_bytes() == expected
    assert read_graph_payload(path) == payload


def test_shard_names_reads_only_manifest_references(tmp_path: Path) -> None:
    assert shard_names(tmp_path / "missing.json") == frozenset()
    path, _, manifest = _write_sharded(tmp_path / "sharded")
    assert shard_names(path) == {
        PurePosixPath(d["path"]).name for d in manifest["shards"]
    }
    plain = tmp_path / "plain" / "graph.json"
    write_graph_payload(_payload(1), plain)
    assert shard_names(plain) == frozenset()
    garbage = tmp_path / "garbage.json"
    garbage.write_bytes(b"not json")
    assert shard_names(garbage) == frozenset()
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (storage.DEFAULT_MAX_FILE_BYTES + 1))
    assert shard_names(oversized) == frozenset()


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
    _link_dir(directory / "symbol-graph.parts", outside)
    with pytest.raises(GraphStorageError, match="symlink"):
        write_graph_payload(_payload(), directory / "graph.json", max_file_bytes=4096)
    assert list(outside.iterdir()) == []
    # A plain publish skips pruning a linked parts directory entirely.
    (aged,) = _seed(outside, 3)
    _age(outside)
    write_graph_payload(_payload(1), directory / "graph.json")
    assert [p.name for p in outside.iterdir()] == [aged.name]


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
