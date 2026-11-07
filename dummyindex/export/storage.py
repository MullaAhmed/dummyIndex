"""Lossless, bounded symbol-graph JSON storage with legacy read compatibility.

Small graphs stay ordinary node-link JSON. Larger graphs use an atomically
published manifest referencing content-addressed shards in
``symbol-graph.parts/``.

Retention is current-generation only: after a successful publish, every
``<sha256>.json`` shard that neither the new file nor the manifest re-read from
disk references is deleted once its mtime is older than
``SHARD_GRACE_SECONDS``. A reader still holding a superseded manifest therefore
fails closed with ``GraphStorageError`` instead of finishing. Links, reparse
points and foreign names are never deleted, and pruning failures only warn.

One manifest per directory is the supported layout: the parts directory is
shared, so publishing one graph prunes shards referenced only by a sibling.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import tempfile
import time
import warnings
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

DEFAULT_MAX_FILE_BYTES = 1_000_000
SHARD_GRACE_SECONDS = 600
_FORMAT = "dummyindex-symbol-graph"
_VERSION = 1
_PARTS_DIR = "symbol-graph.parts"
_FAMILIES = ("nodes", "links", "hyperedges")
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_SHARD_NAME_RE = re.compile(r"[0-9a-f]{64}\.json")
_REPORTED_FAILURES = 5


class GraphStorageError(ValueError):
    """A graph cannot be represented safely or its stored generation is invalid."""


def _is_linked(info: os.stat_result) -> bool:
    """True for a symlink or any reparse point (Windows junctions included)."""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GraphStorageError(f"graph is not valid JSON data: {exc}") from exc


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _plain_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or pure.is_absolute()
        or PureWindowsPath(relative).drive
        or ".." in pure.parts
        or str(pure) == "."
    ):
        raise GraphStorageError(f"unsafe graph storage path: {relative!r}")
    try:
        root_info = root.lstat()
    except FileNotFoundError:
        root_info = None
    if root_info is not None and _is_linked(root_info):
        raise GraphStorageError(
            f"graph storage directory is a symlink or reparse point: {root}"
        )
    path = root
    for part in pure.parts:
        path = path / part
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if _is_linked(info):
            raise GraphStorageError(
                f"graph storage path is a symlink or reparse point: {path}"
            )
    if not path.resolve().is_relative_to(root.resolve()):
        raise GraphStorageError(f"graph storage path escapes its directory: {path}")
    if path.exists() and not path.is_file():
        raise GraphStorageError(f"graph storage is not a regular file: {path}")
    return path


def _read_bytes(path: Path, *, max_bytes: int | None = None) -> bytes:
    path = _plain_path(path.parent, path.name)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise GraphStorageError(f"graph storage is not a regular file: {path}")
        if max_bytes is not None and info.st_size > max_bytes:
            raise GraphStorageError(f"graph storage file exceeds its byte cap: {path}")
        content = (
            handle.read()
            if max_bytes is None
            else handle.read(min(max_bytes, info.st_size) + 1)
        )
    if max_bytes is not None and len(content) > max_bytes:
        raise GraphStorageError(f"graph storage file exceeds its byte cap: {path}")
    return content


def _decode(content: bytes, path: Path) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise GraphStorageError(f"invalid graph JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GraphStorageError(f"graph JSON must be an object: {path}")
    return data


def _canonical_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Sort complete records without changing IDs, paths or graph attributes."""
    data = dict(payload)
    if data.get("format") == _FORMAT:
        raise GraphStorageError("graph payload uses the reserved storage format marker")
    graph = data.get("graph", {})
    if not isinstance(graph, dict):
        raise GraphStorageError("graph metadata must be an object")
    graph = dict(graph)  # node_link_data may alias G.graph.
    data["graph"] = graph
    if "edges" in data:
        if "links" in data and _json_bytes(data["links"]) != _json_bytes(data["edges"]):
            raise GraphStorageError("graph contains conflicting links and edges arrays")
        data["links"] = data.pop("edges")
    top_hyperedges = data.get("hyperedges", graph.get("hyperedges", []))
    if not isinstance(top_hyperedges, list):
        raise GraphStorageError("hyperedges must be an array")
    hyperedges = sorted(top_hyperedges, key=lambda row: _json_bytes(row))
    if "hyperedges" in graph:
        other = graph.pop("hyperedges")
        if not isinstance(other, list) or _json_bytes(
            sorted(other, key=lambda row: _json_bytes(row))
        ) != _json_bytes(hyperedges):
            raise GraphStorageError("graph contains conflicting hyperedge copies")
    data["hyperedges"] = hyperedges
    for family, required in (("nodes", ("id",)), ("links", ("source", "target"))):
        records = data.get(family, [])
        if not isinstance(records, list) or any(
            not isinstance(r, dict) or any(k not in r for k in required)
            for r in records
        ):
            raise GraphStorageError(f"{family} must contain complete record objects")
        if family == "nodes":
            data[family] = sorted(records, key=lambda r: (str(r["id"]), _json_bytes(r)))
        else:
            data[family] = sorted(
                records,
                key=lambda r: (
                    str(r["source"]),
                    str(r["target"]),
                    str(r.get("relation", "")),
                    _json_bytes(r),
                ),
            )
    return data


def _shards(records: list, family: str, cap: int):
    prefix = b'{"kind":' + json.dumps(family).encode() + b',"records":['
    suffix = b"]}\n"
    current = bytearray(prefix)
    count = 0
    for record in records:
        encoded = _json_bytes(record)[:-1]
        if len(prefix) + len(encoded) + len(suffix) > cap:
            raise GraphStorageError(
                f"one {family} record exceeds the {cap}-byte file cap; previous graph unchanged"
            )
        if count and len(current) + 1 + len(encoded) + len(suffix) > cap:
            yield bytes(current) + suffix, count
            current, count = bytearray(prefix), 0
        if count:
            current.extend(b",")
        current.extend(encoded)
        count += 1
    if count:
        yield bytes(current) + suffix, count


def _atomic_write(path: Path, content: bytes) -> None:
    path = _plain_path(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _plain_path(path.parent, path.name)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def shard_names(manifest_path: Path | str) -> frozenset[str]:
    """Return the shard file names (``<sha256>.json``) a manifest references.

    The read is capped at ``DEFAULT_MAX_FILE_BYTES`` so a large plain graph is
    never loaded just to learn it is not a manifest. A missing, oversized,
    undecodable or plain file references nothing; any other ``OSError``
    propagates. Shards are not opened or verified.
    """
    path = Path(manifest_path)
    try:
        data = _decode(_read_bytes(path, max_bytes=DEFAULT_MAX_FILE_BYTES), path)
    except (FileNotFoundError, GraphStorageError):
        return frozenset()
    shards = data.get("shards")
    if data.get("format") != _FORMAT or not isinstance(shards, list):
        return frozenset()
    names: set[str] = set()
    for descriptor in shards:
        relative = descriptor.get("path") if isinstance(descriptor, dict) else None
        if not isinstance(relative, str):
            continue
        directory, _, name = relative.partition("/")
        if directory == _PARTS_DIR and _SHARD_NAME_RE.fullmatch(name):
            names.add(name)
    return frozenset(names)


def _touch(path: Path) -> None:
    """Refresh a reused shard's mtime so a concurrent pruner's grace covers it."""
    try:
        if os.utime in os.supports_follow_symlinks:
            os.utime(path, follow_symlinks=False)
        else:
            os.utime(path)
    except OSError:
        pass  # Best effort: a missing shard is written next, and grace is advisory.


def _shard_is_current(shard: Path, content: bytes) -> bool:
    try:
        if shard.lstat().st_size != len(content):
            return False
        return _read_bytes(shard, max_bytes=len(content)) == content
    except (FileNotFoundError, GraphStorageError):
        # Unsafe paths are rejected again by the atomic rewrite that follows.
        return False


def _prune_shards(path: Path, keep: frozenset[str]) -> None:
    """Delete aged shards outside the current generation; warn, never raise."""
    parts = path.parent / _PARTS_DIR
    failures: list[str] = []
    try:
        try:
            info = parts.lstat()
        except FileNotFoundError:
            return
        if _is_linked(info) or not stat.S_ISDIR(info.st_mode):
            return
        # Re-read the live manifest so a concurrent writer's generation survives.
        protected = keep | shard_names(path)
        now = time.time()
        with os.scandir(parts) as scan:
            entries = list(scan)
        remaining = len(entries)
        for entry in entries:
            if not _SHARD_NAME_RE.fullmatch(entry.name) or entry.name in protected:
                continue
            try:
                info = entry.stat(follow_symlinks=False)
                if (
                    _is_linked(info)
                    or not stat.S_ISREG(info.st_mode)
                    or now - info.st_mtime < SHARD_GRACE_SECONDS
                ):
                    continue
                os.unlink(entry.path)
            except FileNotFoundError:
                pass  # Removed concurrently; it no longer occupies the directory.
            except OSError as exc:
                failures.append(f"{entry.name}: {exc}")
                continue
            remaining -= 1
        if not remaining:
            try:
                os.rmdir(parts)
            except FileNotFoundError:
                pass
            except OSError as exc:
                if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    failures.append(f"{parts}: {exc}")
    except (OSError, GraphStorageError) as exc:
        failures.append(f"{parts}: {exc}")
    if failures:
        shown = "; ".join(failures[:_REPORTED_FAILURES])
        more = len(failures) - _REPORTED_FAILURES
        warnings.warn(
            f"graph shard pruning left {len(failures)} item(s) in {parts}: {shown}"
            + (f"; ... and {more} more" if more > 0 else ""),
            UserWarning,
            stacklevel=2,
        )


def write_graph_payload(
    payload: Mapping[str, Any],
    output_path: Path | str,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> None:
    """Publish a complete bounded generation, or leave the previous one readable.

    An individually oversized record or manifest is rejected before publishing
    any file. After a successful publish, shards outside the new generation are
    pruned once older than ``SHARD_GRACE_SECONDS``; a failed publish deletes
    nothing, and unreferenced shards it leaves are swept by a later publish.
    """
    if (
        not isinstance(max_file_bytes, int)
        or isinstance(max_file_bytes, bool)
        or max_file_bytes < 1
    ):
        raise GraphStorageError("graph file cap must be a positive integer")
    path = Path(output_path)
    _plain_path(path.parent, path.name)
    data = _canonical_payload(payload)
    encoded = _json_bytes(data)
    if len(encoded) <= max_file_bytes:
        _atomic_write(path, encoded)
        _prune_shards(path, frozenset())
        return
    graph_hash = _sha256(encoded)
    del encoded
    descriptors: list[dict] = []
    contents: dict[str, bytes] = {}
    for family in _FAMILIES:
        for content, count in _shards(data[family], family, max_file_bytes):
            digest = _sha256(content)
            relative = f"{_PARTS_DIR}/{digest}.json"
            contents[relative] = content
            descriptors.append(
                {
                    "kind": family,
                    "path": relative,
                    "sha256": digest,
                    "bytes": len(content),
                    "count": count,
                }
            )
    manifest = {
        "format": _FORMAT,
        "version": _VERSION,
        "max_file_bytes": max_file_bytes,
        "graph_sha256": graph_hash,
        "counts": {family: len(data[family]) for family in _FAMILIES},
        "metadata": {key: value for key, value in data.items() if key not in _FAMILIES},
        "shards": descriptors,
    }
    encoded_manifest = _json_bytes(manifest)
    if len(encoded_manifest) > max_file_bytes:
        raise GraphStorageError(
            f"graph manifest exceeds the {max_file_bytes}-byte file cap; previous graph unchanged"
        )
    # Validate every destination before writing any new generation content.
    targets = {relative: _plain_path(path.parent, relative) for relative in contents}
    for relative, content in contents.items():
        shard = targets[relative]
        _touch(shard)
        if not _shard_is_current(shard, content):
            # The hash name proves the intended bytes: repair a damaged shard.
            _atomic_write(shard, content)
    # Publish only after every shard holds its named content, then retire the
    # shards no current generation references (current-generation retention).
    _atomic_write(path, encoded_manifest)
    _prune_shards(path, frozenset(PurePosixPath(r).name for r in contents))


def _integer(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _read_manifest(
    data: dict[str, Any], path: Path, content_size: int
) -> dict[str, Any]:
    if data.get("version") != _VERSION or isinstance(data.get("version"), bool):
        raise GraphStorageError("unsupported graph storage version")
    cap = data.get("max_file_bytes")
    if not _integer(cap, minimum=1) or content_size > cap:
        raise GraphStorageError("invalid graph manifest byte cap")
    counts, metadata, shards = (
        data.get("counts"),
        data.get("metadata"),
        data.get("shards"),
    )
    if (
        not isinstance(counts, dict)
        or set(counts) != set(_FAMILIES)
        or not all(_integer(v) for v in counts.values())
    ):
        raise GraphStorageError("invalid graph manifest record counts")
    if (
        not isinstance(metadata, dict)
        or any(k in metadata for k in (*_FAMILIES, "edges"))
        or not isinstance(shards, list)
    ):
        raise GraphStorageError("invalid graph manifest metadata or shard list")
    graph_hash = data.get("graph_sha256")
    if not isinstance(graph_hash, str) or not _HASH_RE.fullmatch(graph_hash):
        raise GraphStorageError("invalid graph payload hash")
    result = dict(metadata)
    result.update({family: [] for family in _FAMILIES})
    for descriptor in shards:
        if not isinstance(descriptor, dict):
            raise GraphStorageError("invalid graph shard descriptor")
        family, digest = descriptor.get("kind"), descriptor.get("sha256")
        relative, size, count = (
            descriptor.get("path"),
            descriptor.get("bytes"),
            descriptor.get("count"),
        )
        if (
            family not in _FAMILIES
            or not isinstance(digest, str)
            or not _HASH_RE.fullmatch(digest)
        ):
            raise GraphStorageError("invalid graph shard family or hash")
        if (
            relative != f"{_PARTS_DIR}/{digest}.json"
            or not _integer(size, minimum=1)
            or size > cap
            or not _integer(count, minimum=1)
        ):
            raise GraphStorageError("invalid graph shard path, size or count")
        shard_path = _plain_path(path.parent, relative)
        try:
            content = _read_bytes(shard_path, max_bytes=cap)
        except FileNotFoundError as exc:
            raise GraphStorageError(
                f"graph shard missing: {shard_path}; "
                "run `dummyindex context rebuild --changed`"
            ) from exc
        if len(content) != size or _sha256(content) != digest:
            raise GraphStorageError(f"graph shard hash/size mismatch: {shard_path}")
        shard = _decode(content, shard_path)
        records = shard.get("records")
        if (
            shard.get("kind") != family
            or not isinstance(records, list)
            or len(records) != count
        ):
            raise GraphStorageError(
                f"graph shard record count or family mismatch: {shard_path}"
            )
        result[family].extend(records)
    if any(len(result[family]) != counts[family] for family in _FAMILIES):
        raise GraphStorageError("graph manifest total record count mismatch")
    if _sha256(_json_bytes(result)) != graph_hash:
        raise GraphStorageError("assembled graph payload hash mismatch")
    return result


def read_graph_payload(path: Path | str) -> dict[str, Any]:
    """Read legacy node-link JSON or verify and assemble one sharded generation.

    Legacy partial objects retain their shape so each consumer can preserve its
    existing strict/tolerant policy. Missing/corrupt shards never return a
    partially assembled graph.
    """
    path = Path(path)
    content = _read_bytes(path)
    data = _decode(content, path)
    if data.get("format") == _FORMAT:
        return _read_manifest(data, path, len(content))
    if "links" not in data and "edges" in data:
        data["links"] = data.pop("edges")
    return data
