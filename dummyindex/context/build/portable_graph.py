"""Make extraction paths and filename-derived identities portable within one repo."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable
from functools import cache
from pathlib import Path, PurePosixPath, PureWindowsPath

from dummyindex.pipeline.extract.common import _make_id

_EDGE_REFS = ("source", "target", "from", "to", "_src", "_tgt")
_SOURCE_REFS = frozenset({"source", "from", "_src"})
_LOCAL_RELATIONS = frozenset({"contains", "method", "rationale_for", "folder_contains"})


def normalize_extraction_paths(extraction: dict, root: Path) -> dict:
    """Return a new extraction with repo-relative source paths and matching IDs.

    Only declared paths and node references change. Opaque attributes and the
    filesystem-keyed ``file_bytes`` cache remain untouched.
    """
    root = root.resolve()

    @cache
    def relative_path(value: str) -> str:
        return _relative_path(value, root)

    nodes, aliases, ambiguities = _identity_plan(
        extraction.get("nodes", []), relative_path
    )
    placeholders: dict[str, dict] = {}

    def resolve(value: object, source: object = None) -> object:
        if not isinstance(value, str) or value not in aliases:
            return value
        candidates = aliases[value]
        if len(candidates) == 1:
            return candidates[0]["node"]["id"]
        local = [row for row in candidates if source and row["path"] == source]
        if len(local) == 1:
            return local[0]["node"]["id"]
        original = _ambiguity_id(value, candidates)
        description = ambiguities[original]
        placeholders[original] = {
            "id": original,
            "label": f"Ambiguous {original}: {len(description['candidates'])} definitions",
            "file_type": "ambiguity",
            "resolution": "ambiguous",
            "original_id": original,
            "candidate_ids": [row["id"] for row in description["candidates"]],
            "candidates": description["candidates"],
        }
        return original

    def references(record: dict, fields: tuple[str, ...] = _EDGE_REFS) -> dict:
        record = _paths(record, relative_path)
        local = record.get("source_file")
        target = record.get("target_source_file") or record.get("target_file")
        if isinstance(target, str):
            target = relative_path(target)
        if record.get("relation") in _LOCAL_RELATIONS:
            target = target or local
        return {
            **record,
            **{
                field: resolve(
                    record[field], local if field in _SOURCE_REFS else target
                )
                for field in fields
                if field in record
            },
        }

    result = dict(extraction)
    if "nodes" in extraction:
        result["nodes"] = nodes
    for field in ("edges", "links"):
        if field in extraction:
            result[field] = [
                references(edge) if isinstance(edge, dict) else edge
                for edge in extraction[field]
            ]
    if "hyperedges" in extraction:
        result["hyperedges"] = [
            _hyperedge(edge, relative_path, resolve, references)
            if isinstance(edge, dict)
            else edge
            for edge in extraction["hyperedges"]
        ]
    if placeholders:
        result["nodes"].extend(placeholders[key] for key in sorted(placeholders))
    if ambiguities:
        existing = extraction.get("identity_ambiguities", [])
        if not isinstance(existing, list):
            raise ValueError("identity_ambiguities must be a list")
        merged = {row["original_id"]: row for row in existing}
        merged.update(ambiguities)
        result["identity_ambiguities"] = [merged[key] for key in sorted(merged)]
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
    fields = ("source_file", "path", "target_file", "target_source_file")
    if node and "source_file" not in record:
        fields += ("source",)
    for field in fields:
        if isinstance(record.get(field), str):
            result[field] = relative_path(record[field])
    return result


def _internal_source(value: object) -> bool:
    return bool(
        isinstance(value, str)
        and value
        and "://" not in value
        and not Path(value).is_absolute()
        and not PureWindowsPath(value).anchor
        and ".." not in PurePosixPath(value).parts
    )


def _portable_id(node: dict, relative_path: Callable[[str], str]) -> str:
    source = node.get("source_file") or node.get("source") or node.get("path")
    if not isinstance(source, str):
        return node["id"]
    relative = relative_path(source)
    if not _internal_source(relative):
        return node["id"]
    old_id = node["id"]
    parts = PurePosixPath(source.replace("\\", "/")).parts
    suffix_ids = {_make_id("/".join(parts[i:])) for i in range(len(parts))}
    if node.get("label") == PurePosixPath(relative).name and old_id in suffix_ids:
        return _make_id(relative)
    if old_id == _make_id(source):
        return _make_id(relative)
    if isinstance(node.get("label"), str) and old_id == _make_id(source, node["label"]):
        return _make_id(relative, node["label"])
    return old_id


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _ambiguity_id(alias: str, rows: list[dict]) -> str:
    bases = {row["base"] for row in rows}
    return next(iter(bases)) if len(bases) == 1 else alias


def _identity_plan(
    nodes: list, relative_path: Callable[[str], str]
) -> tuple[list, dict, dict]:
    """Keep distinct source records; legacy aliases never select arbitrary definitions."""
    records: dict[str, dict] = {}
    old_groups: dict[str, set[str]] = defaultdict(set)
    base_groups: dict[str, set[str]] = defaultdict(set)
    order: list[tuple[bool, object]] = []
    for raw in nodes:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            order.append((False, raw))
            continue
        node = {
            **_paths(raw, relative_path, node=True),
            "id": _portable_id(raw, relative_path),
        }
        key = _canonical(node)
        if key not in records:
            path = node.get("source_file") or node.get("source") or node.get("path")
            records[key] = {
                "node": node,
                "base": node["id"],
                "path": path,
                "aliases": set(),
            }
            order.append((True, key))
        records[key]["aliases"].add(raw["id"])
        old_groups[raw["id"]].add(key)
        base_groups[node["id"]].add(key)

    affected: set[str] = set()
    for groups in (old_groups, base_groups):
        for keys in groups.values():
            if len(keys) <= 1:
                continue
            if any(not _internal_source(records[key]["path"]) for key in keys):
                raise ValueError(
                    "Portable graph node ID collision has an opaque/external definition"
                )
            affected.update(keys)
    path_counts = Counter(
        (records[key]["base"], records[key]["path"]) for key in affected
    )
    for key in affected:
        row = records[key]
        seed = row["path"] if path_counts[row["base"], row["path"]] == 1 else key
        suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        row["node"] = {**row["node"], "id": row["base"] + "__" + suffix}
        row["node"].setdefault("original_id", row["base"])

    owners: dict[str, str] = {}
    aliases: dict[str, list[dict]] = defaultdict(list)
    for key, row in records.items():
        new_id = row["node"]["id"]
        if new_id in owners and owners[new_id] != key:
            raise ValueError(f"Portable graph node ID collision: {new_id!r}")
        owners[new_id] = key
        for alias in row["aliases"] | {row["base"]}:
            aliases[alias].append(row)
    ambiguity_rows: dict[str, dict[str, dict]] = defaultdict(dict)
    for alias, rows in aliases.items():
        if len(rows) > 1:
            original = _ambiguity_id(alias, rows)
            if original in owners:
                raise ValueError(
                    f"Portable graph ambiguity ID collides with a definition: {original!r}"
                )
            for row in rows:
                ambiguity_rows[original][row["node"]["id"]] = row
    ambiguities = {
        original: {
            "original_id": original,
            "candidates": [
                {
                    "id": row["node"]["id"],
                    "path": row["path"],
                    **(
                        {"source_location": row["node"]["source_location"]}
                        if "source_location" in row["node"]
                        else {}
                    ),
                }
                for _, row in sorted(rows.items())
            ],
            "reason": "Multiple distinct source definitions share a legacy identifier; uncertain references stay ambiguous.",
        }
        for original, rows in sorted(ambiguity_rows.items())
    }
    return (
        [records[item]["node"] if known else item for known, item in order],
        aliases,
        ambiguities,
    )


def _hyperedge(
    edge: dict,
    relative_path: Callable[[str], str],
    resolve: Callable,
    references: Callable,
) -> dict:
    result = _paths(edge, relative_path)
    if isinstance(edge.get("nodes"), list):
        result["nodes"] = [resolve(n) for n in edge["nodes"]]
    for field, refs in (("members", ("node_id",)), ("sequence", _EDGE_REFS)):
        if isinstance(edge.get(field), list):
            result[field] = [
                (
                    {
                        **_paths(row, relative_path),
                        "node_id": resolve(
                            row["node_id"],
                            relative_path(row["source_file"])
                            if isinstance(row.get("source_file"), str)
                            else None,
                        ),
                    }
                    if "node_id" in row and refs == ("node_id",)
                    else references(row, refs)
                )
                if isinstance(row, dict)
                else row
                for row in edge[field]
            ]
    return result
