"""Top-down hierarchy (folder -> file -> class -> function/method/global) with cross-edges.

This is a standalone builder. It reads the legacy extraction dict (produced by
`pipeline.extract`) plus the code file list, and returns a pure Python dict
describing the structure graph. It never mutates the extraction, never builds a
NetworkX graph, and never touches graph.json / graph.html / GRAPH_REPORT.md.

The returned shape is:

    {
        "schema_version": "2.0",
        "root_id": <folder id>,
        "root_label": <human label>,
        "nodes": [
            {
                "id": str,
                "label": str,
                "kind": "folder"|"file"|"class"|"function"|"method"|"global",
                "parent": str | None,
                "source_file": str,              # rel-to-root, posix; "" for folders above files
                "source_location": str | None,   # e.g. "L13"
                "child_count": int,
            },
            ...
        ],
        "hierarchy_edges": [
            {"source": str, "target": str, "relation": "folder_contains"|"contains"|"method"},
            ...
        ],
        "cross_edges": [
            {"source": str, "target": str, "relation": str,
             "confidence": str, "source_file": str, "source_location": str},
            ...
        ],
    }
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

from collections import defaultdict
from pathlib import Path, PurePosixPath

from .common import _rel_path
from .references import _derive_textual_references, _discover_extra_source_files


SCHEMA_VERSION = "2.0"

HIERARCHY_RELATIONS = frozenset({"folder_contains", "contains", "method"})


def build_structure(
    extraction: dict,
    code_files: list[Path],
    root: Path,
    *,
    include_extras: bool = True,
) -> dict:
    """Assemble the structure graph payload. See module docstring for shape.

    ``include_extras`` (default True for backward compatibility): walk the
    repo and add every non-code file (READMEs, configs, docs, ...) as a
    leaf node in the structure. The v2 ``.context/`` flow passes
    ``include_extras=False`` because `tree.json` is for symbol navigation
    only — non-code files belong in `files.json`, not in the navigable tree.
    """
    root_abs = root.resolve() if root.is_absolute() else (Path.cwd() / root).resolve()

    if include_extras:
        # Start with dummyindex's detected code files, then augment with HTML,
        # ipynb, config, and other source-adjacent files under root so the
        # tree reflects the full source layout. These extras appear as leaf
        # file nodes because the AST extractor doesn't parse them — but they
        # do appear.
        effective_files = list(code_files) + _discover_extra_source_files(root_abs, code_files)
    else:
        effective_files = list(code_files)

    # The structure tree lists every file in ``effective_files`` as a leaf, but
    # only nodes extracted from *code* files (Python classes, functions, etc.)
    # become internal AST children. Concepts/documents/image nodes extracted
    # from PDFs or other non-code inputs stay out of the classifier — they
    # remain first-class citizens in graph.json.
    code_file_rels = {_rel_path(str(p), root_abs) for p in effective_files}
    code_file_rels.discard("")
    raw_nodes = [n for n in extraction.get("nodes", []) if isinstance(n, dict) and "id" in n]
    source_nodes = [
        n for n in raw_nodes
        if n.get("file_type", "code") == "code"
        and _rel_path(str(n.get("source_file", "") or ""), root_abs) in code_file_rels
    ]
    code_node_ids = {n["id"] for n in source_nodes}
    source_edges = [
        e for e in extraction.get("edges", [])
        if isinstance(e, dict)
        and e.get("source") in code_node_ids
        and e.get("target") in code_node_ids
    ]

    file_node_by_rel, unit_nodes = _classify_nodes(source_nodes, source_edges, root_abs)

    nodes: dict[str, dict] = {}
    hierarchy_edges: list[dict] = []

    for file_node in file_node_by_rel.values():
        nodes[file_node["id"]] = file_node
    for unit in unit_nodes:
        nodes[unit["id"]] = unit

    _add_hierarchy_from_existing_edges(source_edges, nodes, hierarchy_edges)

    file_ids_by_rel = {rel: fn["id"] for rel, fn in file_node_by_rel.items()}
    _ensure_files_for_all_paths(effective_files, root_abs, nodes, file_ids_by_rel)

    root_id, root_label = _add_folders(effective_files, root_abs, nodes, file_ids_by_rel, hierarchy_edges)

    _backfill_parents(nodes, hierarchy_edges)

    cross_edges = _filter_cross_edges(source_edges, nodes)
    # P2: reuse the bytes the extraction already read (keyed by str(path)) so the
    # textual-reference pass does not re-read source files from disk. Extra
    # (non-code) files not present in the map fall back to reading inside
    # ``_derive_textual_references``.
    file_bytes = extraction.get("file_bytes") if isinstance(extraction, dict) else None
    _derive_textual_references(
        effective_files,
        root_abs,
        file_ids_by_rel,
        cross_edges,
        file_bytes=file_bytes if isinstance(file_bytes, dict) else None,
    )

    _compute_child_counts(nodes, hierarchy_edges)

    sorted_nodes = sorted(nodes.values(), key=lambda n: n["id"])
    sorted_hierarchy = sorted(
        hierarchy_edges,
        key=lambda e: (e["source"], e["target"], e["relation"]),
    )
    sorted_cross = sorted(
        cross_edges,
        key=lambda e: (e["source"], e["target"], e["relation"], e.get("source_location", "")),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "root_id": root_id,
        "root_label": root_label,
        "nodes": sorted_nodes,
        "hierarchy_edges": sorted_hierarchy,
        "cross_edges": sorted_cross,
    }


def _classify_nodes(
    source_nodes: list[dict],
    source_edges: list[dict],
    root_abs: Path,
) -> tuple[dict[str, dict], list[dict]]:
    """Split extraction nodes into file-level nodes (by rel path) and unit nodes.

    Returns ``(file_nodes_by_rel, unit_nodes)``.
    """
    method_targets: set[str] = set()
    method_sources: set[str] = set()
    contains_parents: set[str] = set()
    for edge in source_edges:
        rel = edge.get("relation")
        src = edge.get("source")
        tgt = edge.get("target")
        if rel == "method" and src and tgt:
            method_sources.add(src)
            method_targets.add(tgt)
        if rel == "contains" and src:
            contains_parents.add(src)

    file_nodes_by_rel: dict[str, dict] = {}
    unit_nodes: list[dict] = []

    for raw in source_nodes:
        src_file = raw.get("source_file") or ""
        rel = _rel_path(src_file, root_abs)
        label = str(raw.get("label", ""))
        looks_like_file = bool(src_file and rel and label and label == Path(src_file).name)

        if looks_like_file:
            file_nodes_by_rel[rel] = {
                "id": raw["id"],
                "label": label,
                "kind": "file",
                "parent": None,
                "source_file": rel,
                "source_location": raw.get("source_location"),
                "child_count": 0,
            }
            continue

        kind = _classify_unit_kind(raw, method_sources, method_targets, contains_parents)
        unit_nodes.append({
            "id": raw["id"],
            "label": label,
            "kind": kind,
            "parent": None,
            "source_file": rel or src_file,
            "source_location": raw.get("source_location"),
            "child_count": 0,
        })

    return file_nodes_by_rel, unit_nodes


def _classify_unit_kind(
    node: dict,
    method_sources: set[str],
    method_targets: set[str],
    contains_parents: set[str],
) -> str:
    node_id = node["id"]
    label = str(node.get("label", ""))
    if node_id in method_targets:
        return "method"
    if node_id in method_sources:
        return "class"
    if label.endswith("()"):
        return "function"
    if node_id in contains_parents:
        return "class"
    return "function"


def _add_hierarchy_from_existing_edges(
    source_edges: list[dict],
    nodes: dict[str, dict],
    hierarchy_edges: list[dict],
) -> None:
    """Carry `contains` and `method` edges into the structure hierarchy."""
    for edge in source_edges:
        rel = edge.get("relation")
        if rel not in ("contains", "method"):
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if not src or not tgt:
            continue
        if src not in nodes or tgt not in nodes:
            continue
        hierarchy_edges.append({"source": src, "target": tgt, "relation": rel})


def _ensure_files_for_all_paths(
    code_files: list[Path],
    root_abs: Path,
    nodes: dict[str, dict],
    file_ids_by_rel: dict[str, str],
) -> None:
    """Add a synthetic file node for any source file that had no extraction nodes."""
    for path in code_files:
        rel = _rel_path(str(path), root_abs)
        if not rel:
            continue
        if rel in file_ids_by_rel:
            continue
        file_id = _synth_id("file", rel)
        if file_id in nodes:
            continue
        nodes[file_id] = {
            "id": file_id,
            "label": Path(rel).name,
            "kind": "file",
            "parent": None,
            "source_file": rel,
            "source_location": "L1",
            "child_count": 0,
        }
        file_ids_by_rel[rel] = file_id


def _add_folders(
    code_files: list[Path],
    root_abs: Path,
    nodes: dict[str, dict],
    file_ids_by_rel: dict[str, str],
    hierarchy_edges: list[dict],
) -> tuple[str, str]:
    """Create folder nodes and folder_contains edges. Returns (root_id, root_label)."""
    rel_paths = sorted({_rel_path(str(p), root_abs) for p in code_files if _rel_path(str(p), root_abs)})
    root_label = root_abs.name or "."
    root_id = _synth_id("folder", "")

    nodes.setdefault(root_id, {
        "id": root_id,
        "label": root_label,
        "kind": "folder",
        "parent": None,
        "source_file": "",
        "source_location": None,
        "child_count": 0,
    })

    seen: set[tuple[str, str]] = set()

    def link(src_id: str, tgt_id: str) -> None:
        key = (src_id, tgt_id)
        if key in seen:
            return
        seen.add(key)
        hierarchy_edges.append({"source": src_id, "target": tgt_id, "relation": "folder_contains"})

    for rel_path in rel_paths:
        parts = PurePosixPath(rel_path).parts
        if not parts:
            continue
        parent_id = root_id
        parent_rel = ""
        for part in parts[:-1]:
            folder_rel = f"{parent_rel}/{part}" if parent_rel else part
            folder_id = _synth_id("folder", folder_rel)
            nodes.setdefault(folder_id, {
                "id": folder_id,
                "label": part,
                "kind": "folder",
                "parent": parent_id,
                "source_file": folder_rel,
                "source_location": None,
                "child_count": 0,
            })
            link(parent_id, folder_id)
            parent_id = folder_id
            parent_rel = folder_rel
        file_id = file_ids_by_rel.get(rel_path)
        if file_id and file_id in nodes:
            link(parent_id, file_id)

    return root_id, root_label


def _backfill_parents(nodes: dict[str, dict], hierarchy_edges: list[dict]) -> None:
    """Set each node's ``parent`` from its incoming hierarchy edge."""
    incoming: dict[str, str] = {}
    for edge in hierarchy_edges:
        incoming.setdefault(edge["target"], edge["source"])
    for node_id, parent_id in incoming.items():
        node = nodes.get(node_id)
        if node is not None and node.get("parent") is None:
            node["parent"] = parent_id


def _filter_cross_edges(source_edges: list[dict], nodes: dict[str, dict]) -> list[dict]:
    """Keep non-hierarchy edges whose endpoints exist in the structure graph."""
    cross: list[dict] = []
    for edge in source_edges:
        rel = edge.get("relation", "")
        if rel in HIERARCHY_RELATIONS:
            continue
        src = edge.get("source")
        tgt = edge.get("target")
        if not src or not tgt:
            continue
        if src not in nodes or tgt not in nodes:
            continue
        cross.append({
            "source": src,
            "target": tgt,
            "relation": rel,
            "confidence": edge.get("confidence", ConfidenceLevel.EXTRACTED),
            "source_file": edge.get("source_file", ""),
            "source_location": edge.get("source_location", ""),
        })
    return cross


def _compute_child_counts(nodes: dict[str, dict], hierarchy_edges: list[dict]) -> None:
    counts: dict[str, int] = defaultdict(int)
    for edge in hierarchy_edges:
        counts[edge["source"]] += 1
    for node_id, node in nodes.items():
        node["child_count"] = counts.get(node_id, 0)




def _synth_id(prefix: str, key: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in key)
    cleaned = "_".join(part for part in cleaned.split("_") if part).lower()
    return f"{prefix}__{cleaned}" if cleaned else f"{prefix}__root"

