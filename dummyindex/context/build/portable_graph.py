"""Make extraction paths and filename-derived identities portable within one repo."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path, PurePosixPath, PureWindowsPath

from dummyindex.pipeline.extract.common import _make_id

_EDGE_REFS = ("source", "target", "from", "to", "_src", "_tgt")


def normalize_extraction_paths(extraction: dict, root: Path) -> dict:
    """Return a new extraction with repo-relative source paths and matching IDs.

    Only declared paths and node references change. Opaque attributes and the
    filesystem-keyed ``file_bytes`` cache remain untouched.
    """
    root = root.resolve()

    @cache
    def relative_path(value: str) -> str:
        return _relative_path(value, root)

    nodes = extraction.get("nodes", [])
    id_map = _node_id_map(nodes, relative_path)
    result = dict(extraction)
    if "nodes" in extraction:
        result["nodes"] = [
            {
                **_paths(node, relative_path, node=True),
                **({"id": id_map[node["id"]]} if node.get("id") in id_map else {}),
            }
            if isinstance(node, dict)
            else node
            for node in nodes
        ]
    for field in ("edges", "links"):
        if field in extraction:
            result[field] = [
                _refs(_paths(edge, relative_path), id_map, _EDGE_REFS)
                if isinstance(edge, dict)
                else edge
                for edge in extraction[field]
            ]
    if "hyperedges" in extraction:
        result["hyperedges"] = [
            _hyperedge(edge, relative_path, id_map) if isinstance(edge, dict) else edge
            for edge in extraction["hyperedges"]
        ]
    return result


def _relative_path(value: str, root: Path) -> str:
    if not value or "://" in value:
        return value
    path = Path(value)
    # Do not reinterpret another platform's absolute path as a repo-relative one.
    if not path.is_absolute() and (
        PureWindowsPath(value).anchor or value.startswith("/")
    ):
        return value
    if not path.is_absolute():
        path = root / value.replace("\\", "/")
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return value


def _paths(
    record: dict, relative_path: Callable[[str], str], *, node: bool = False
) -> dict:
    result = dict(record)
    fields = ("source_file", "path")
    if node and "source_file" not in record:
        fields += ("source",)
    for field in fields:
        if isinstance(record.get(field), str):
            result[field] = relative_path(record[field])
    return result


def _node_id_map(nodes: list, relative_path: Callable[[str], str]) -> dict[str, str]:
    remap: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        source = node.get("source_file") or node.get("source") or node.get("path")
        if not isinstance(source, str):
            continue
        relative = relative_path(source)
        if (
            Path(relative).is_absolute()
            or PureWindowsPath(relative).anchor
            or relative.startswith("/")
            or ".." in PurePosixPath(relative).parts
        ):
            continue
        old_id = node["id"]
        source_parts = PurePosixPath(source.replace("\\", "/")).parts
        file_ids = {
            _make_id("/".join(source_parts[index:]))
            for index in range(len(source_parts))
        }
        if node.get("label") == PurePosixPath(relative).name and old_id in file_ids:
            # extract() may already have removed an inferred, scope-dependent prefix.
            remap[old_id] = _make_id(relative)
        elif old_id == _make_id(source):
            remap[old_id] = _make_id(relative)
        elif isinstance(node.get("label"), str) and old_id == _make_id(
            source, node["label"]
        ):
            # Dart's extractor also prefixes class/function IDs with the filename.
            remap[old_id] = _make_id(relative, node["label"])
    owners: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        old_id = node["id"]
        new_id = remap.get(old_id, old_id)
        if new_id in owners and owners[new_id] != old_id:
            raise ValueError(f"Portable graph node ID collision: {new_id!r}")
        owners[new_id] = old_id
    return remap


def _refs(record: dict, id_map: dict[str, str], fields: tuple[str, ...]) -> dict:
    return {
        **record,
        **{
            field: id_map[record[field]]
            for field in fields
            if isinstance(record.get(field), str) and record[field] in id_map
        },
    }


def _hyperedge(
    edge: dict, relative_path: Callable[[str], str], id_map: dict[str, str]
) -> dict:
    result = _paths(edge, relative_path)
    if isinstance(edge.get("nodes"), list):
        result["nodes"] = [
            id_map.get(n, n) if isinstance(n, str) else n for n in edge["nodes"]
        ]
    for field, refs in (("members", ("node_id",)), ("sequence", _EDGE_REFS)):
        if isinstance(edge.get(field), list):
            result[field] = [
                _refs(_paths(row, relative_path), id_map, refs)
                if isinstance(row, dict)
                else row
                for row in edge[field]
            ]
    return result
