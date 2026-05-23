"""Build .context/tree.json — PageIndex-style hierarchical reasoning tree.

Project → dir → file → class → method/function hierarchy. Deterministic in v0:
abstracts are name-based stubs; docstring extraction lands in a later PR.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dummyindex.pipeline.detect import detect
from dummyindex.pipeline.extract import extract
from dummyindex.pipeline.structure import build_structure

SCHEMA_VERSION = 1

_HIERARCHY_RELATIONS = frozenset({"contains", "method"})
_TREE_KINDS_FROM_STRUCTURE: dict[str, str] = {
    "file": "file",
    "class": "class",
    "function": "function",
    "method": "method",
}


@dataclass(frozen=True)
class TreeNode:
    node_id: str
    kind: str
    title: str
    path: Optional[str] = None
    range: Optional[tuple[int, int]] = None
    abstract: str = ""
    overview_ref: Optional[str] = None
    detail_ref: Optional[str] = None
    confidence: str = "EXTRACTED"
    labels: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    children: tuple["TreeNode", ...] = ()


@dataclass(frozen=True)
class Tree:
    schema_version: int
    root: TreeNode


def build_tree(
    root: Path,
    *,
    cache_root: Optional[Path] = None,
) -> Tree:
    """Run detect → extract → build_structure on `root` and assemble a Tree.

    Convenience wrapper. For shared-pipeline builds, call
    `tree_from_structure` on a structure already computed by the
    orchestrator (see `runner.build_all`).
    """
    root = root.resolve()
    cache = (cache_root or root).resolve()

    detection = detect(root)
    code_files = [Path(p) for p in detection.get("files", {}).get("code", [])]
    extraction = extract(code_files, cache_root=cache)
    structure = build_structure(extraction, code_files, root)

    return _assemble(structure, root)


def tree_from_structure(structure: dict, root: Path) -> Tree:
    """Build a Tree from a precomputed structure-graph dict."""
    return _assemble(structure, root.resolve())


def _assemble(structure: dict, root: Path) -> Tree:
    nodes_by_id = {n["id"]: n for n in structure.get("nodes", []) if "id" in n}
    children_by_parent: dict[str, list[str]] = {}
    for edge in structure.get("hierarchy_edges", []):
        if edge.get("relation") in _HIERARCHY_RELATIONS:
            src, tgt = edge.get("source"), edge.get("target")
            if src and tgt:
                children_by_parent.setdefault(src, []).append(tgt)

    file_id_by_path: dict[str, str] = {}
    for n in nodes_by_id.values():
        if n.get("kind") == "file":
            rel = n.get("source_file") or ""
            if rel:
                file_id_by_path[rel] = n["id"]

    dir_paths = _collect_dir_paths(file_id_by_path.keys())

    root_node = _build_dir_or_project(
        dir_rel=None,
        root_name=root.name,
        dir_paths=dir_paths,
        file_id_by_path=file_id_by_path,
        nodes_by_id=nodes_by_id,
        children_by_parent=children_by_parent,
    )
    return Tree(schema_version=SCHEMA_VERSION, root=root_node)


def _collect_dir_paths(file_paths: Any) -> frozenset[str]:
    paths: set[str] = set()
    for rel in file_paths:
        parts = rel.split("/")
        for i in range(1, len(parts)):
            paths.add("/".join(parts[:i]))
    return frozenset(paths)


def _build_dir_or_project(
    *,
    dir_rel: Optional[str],
    root_name: str,
    dir_paths: frozenset[str],
    file_id_by_path: dict[str, str],
    nodes_by_id: dict[str, dict],
    children_by_parent: dict[str, list[str]],
) -> TreeNode:
    if dir_rel is None:
        prefix = ""
        title = root_name
        node_id = _project_id(root_name)
        kind = "project"
        path = "."
    else:
        prefix = dir_rel + "/"
        title = dir_rel.split("/")[-1]
        node_id = _dir_id(dir_rel)
        kind = "dir"
        path = dir_rel

    subdirs = sorted(
        p for p in dir_paths
        if p.startswith(prefix) and "/" not in p[len(prefix):] and p != dir_rel
    ) if prefix or dir_rel is None else []
    files_here = sorted(
        rel for rel in file_id_by_path
        if rel.startswith(prefix) and "/" not in rel[len(prefix):]
    )

    children: list[TreeNode] = []
    for sd in subdirs:
        children.append(
            _build_dir_or_project(
                dir_rel=sd,
                root_name=root_name,
                dir_paths=dir_paths,
                file_id_by_path=file_id_by_path,
                nodes_by_id=nodes_by_id,
                children_by_parent=children_by_parent,
            )
        )
    for rel in files_here:
        children.append(
            _build_file(
                rel=rel,
                file_id=file_id_by_path[rel],
                nodes_by_id=nodes_by_id,
                children_by_parent=children_by_parent,
            )
        )

    if kind == "project":
        abstract = f"Codebase rooted at {root_name}."
    else:
        abstract = f"Directory at {dir_rel}/ ({len(children)} immediate children)."

    return TreeNode(
        node_id=node_id,
        kind=kind,
        title=title,
        path=path,
        abstract=abstract,
        confidence="EXTRACTED",
        children=tuple(children),
    )


def _build_file(
    *,
    rel: str,
    file_id: str,
    nodes_by_id: dict[str, dict],
    children_by_parent: dict[str, list[str]],
) -> TreeNode:
    child_ids = children_by_parent.get(file_id, [])
    children = tuple(
        _build_symbol(cid, nodes_by_id, children_by_parent, parent_path=rel)
        for cid in sorted(child_ids)
        if cid in nodes_by_id
    )
    language = _language_for_path(rel)
    abstract = f"{language or 'source'} file at {rel} ({len(children)} top-level definitions)."
    return TreeNode(
        node_id=file_id,
        kind="file",
        title=Path(rel).name,
        path=rel,
        abstract=abstract,
        confidence="EXTRACTED",
        children=children,
    )


def _build_symbol(
    sid: str,
    nodes_by_id: dict[str, dict],
    children_by_parent: dict[str, list[str]],
    *,
    parent_path: str,
) -> TreeNode:
    node = nodes_by_id[sid]
    structure_kind = node.get("kind") or "function"
    kind = _TREE_KINDS_FROM_STRUCTURE.get(structure_kind, "function")
    name = _clean_name(str(node.get("label") or ""))
    start = _parse_source_location(node.get("source_location"))
    rng = (start, start) if start is not None else None

    child_ids = children_by_parent.get(sid, [])
    children = tuple(
        _build_symbol(cid, nodes_by_id, children_by_parent, parent_path=parent_path)
        for cid in sorted(child_ids)
        if cid in nodes_by_id
    )

    if kind == "class":
        abstract = f"Class {name} at {parent_path}" + (f":{start}" if start else "") + "."
    elif kind == "method":
        abstract = f"Method {name} at {parent_path}" + (f":{start}" if start else "") + "."
    else:
        abstract = f"Function {name} at {parent_path}" + (f":{start}" if start else "") + "."

    return TreeNode(
        node_id=sid,
        kind=kind,
        title=name,
        path=parent_path,
        range=rng,
        abstract=abstract,
        confidence="EXTRACTED",
        children=children,
    )


# ----- ID helpers ------------------------------------------------------------


def _project_id(name: str) -> str:
    return f"n-prj-{_slugify(name)}"


def _dir_id(dir_rel: str) -> str:
    return f"n-dir-{_slugify(dir_rel)}"


_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value).strip("-").lower() or "x"


# ----- Misc parsing ----------------------------------------------------------


_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}


def _language_for_path(rel: str) -> Optional[str]:
    return _LANG_BY_EXT.get(Path(rel).suffix.lower())


def _clean_name(raw_label: str) -> str:
    return raw_label.rstrip("()").lstrip(".") or raw_label


def _parse_source_location(loc: Any) -> Optional[int]:
    if not isinstance(loc, str):
        return None
    s = loc.strip().lstrip("L")
    if "-" in s:
        s = s.split("-", 1)[0].lstrip("L")
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


# ----- Writers ---------------------------------------------------------------


def write_tree(path: Path, tree: Tree) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": tree.schema_version,
        "root": _node_to_json(tree.root),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _node_to_json(node: TreeNode) -> dict[str, Any]:
    out: dict[str, Any] = {
        "node_id": node.node_id,
        "kind": node.kind,
        "title": node.title,
    }
    if node.path is not None:
        out["path"] = node.path
    out["range"] = list(node.range) if node.range else None
    out["abstract"] = node.abstract
    out["overview_ref"] = node.overview_ref
    out["detail_ref"] = node.detail_ref
    out["confidence"] = node.confidence
    out["labels"] = list(node.labels)
    out["evidence"] = list(node.evidence)
    out["children"] = [_node_to_json(c) for c in node.children]
    return out


# Helper exposed for tests / callers that have a Tree in memory
def iter_nodes(node: TreeNode):
    yield node
    for child in node.children:
        yield from iter_nodes(child)
