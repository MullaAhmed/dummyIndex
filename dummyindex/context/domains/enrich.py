"""Plan and apply LLM enrichment for `.context/tree.json` abstracts.

`build_plan` walks tree.json, finds nodes whose `confidence` is still
`EXTRACTED` (the deterministic-stub default), and emits a structured
JSON the Claude session running the `/dummyindex` skill can use as a
work-list. Nodes are ordered top-down (project → directories → files →
in-file symbols) and grouped into per-file batches so the skill can
write enriched abstracts back to `tree.json` one file at a time —
partial progress survives an interrupted session.

`apply_updates` merges a `{node_id: new_abstract}` mapping back into
`tree.json` and bumps each touched node's `confidence` from
`EXTRACTED` → `INFERRED`. Idempotent: re-applying the same updates is
a no-op once the abstracts already match.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EnrichNode:
    """One tree.json node still carrying a deterministic stub abstract."""

    node_id: str
    kind: str
    title: str
    path: Optional[str]
    range: Optional[list[int]]
    stub_abstract: str
    evidence_files: tuple[str, ...]


@dataclass(frozen=True)
class EnrichBatch:
    """A coherent unit of enrichment — usually one file's subtree."""

    name: str
    kind: str
    node_ids: tuple[str, ...]


@dataclass(frozen=True)
class EnrichPlan:
    schema_version: int
    generated_at: str
    context_dir: str
    tree_path: str
    stats: dict[str, Any]
    batches: tuple[EnrichBatch, ...]
    nodes: tuple[EnrichNode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "context_dir": self.context_dir,
            "tree_path": self.tree_path,
            "stats": dict(self.stats),
            "batches": [
                {
                    "name": b.name,
                    "kind": b.kind,
                    "node_ids": list(b.node_ids),
                }
                for b in self.batches
            ],
            "nodes": [
                {
                    "node_id": n.node_id,
                    "kind": n.kind,
                    "title": n.title,
                    "path": n.path,
                    "range": n.range,
                    "stub_abstract": n.stub_abstract,
                    "evidence_files": list(n.evidence_files),
                }
                for n in self.nodes
            ],
        }


def build_plan(
    context_dir: Path,
    *,
    now: Optional[_dt.datetime] = None,
) -> EnrichPlan:
    """Build an EnrichPlan from `<context_dir>/tree.json`.

    Raises FileNotFoundError if tree.json doesn't exist.
    """
    context_dir = context_dir.resolve()
    tree_path = context_dir / "tree.json"
    if not tree_path.exists():
        raise FileNotFoundError(
            f"{tree_path} not found. Run `dummyindex ingest <path>` first."
        )
    tree = json.loads(tree_path.read_text(encoding="utf-8"))

    nodes: list[EnrichNode] = []
    structural_ids: list[str] = []  # project + dir nodes
    by_file: dict[str, list[str]] = {}
    file_titles: dict[str, str] = {}
    by_kind: dict[str, int] = {}

    for node, current_file in _walk(tree["root"]):
        if node.get("confidence", ConfidenceLevel.EXTRACTED) != ConfidenceLevel.EXTRACTED:
            continue
        kind = node["kind"]
        by_kind[kind] = by_kind.get(kind, 0) + 1
        enriched = EnrichNode(
            node_id=node["node_id"],
            kind=kind,
            title=node.get("title", ""),
            path=node.get("path"),
            range=node.get("range"),
            stub_abstract=node.get("abstract", ""),
            evidence_files=(current_file,) if current_file else (),
        )
        nodes.append(enriched)
        if kind in ("project", "dir"):
            structural_ids.append(node["node_id"])
        elif kind == "file":
            by_file.setdefault(node["node_id"], []).append(node["node_id"])
            file_titles[node["node_id"]] = node.get("title", node["node_id"])
        elif current_file is not None:
            # Find the file's node_id by matching path. We carry the file
            # path as current_file; the file node was visited earlier in the
            # pre-order walk and recorded in by_file under its node_id.
            file_nid = _file_id_for_path(tree["root"], current_file)
            if file_nid:
                by_file.setdefault(file_nid, []).append(node["node_id"])
                file_titles.setdefault(file_nid, Path(current_file).name)

    batches: list[EnrichBatch] = []
    if structural_ids:
        batches.append(
            EnrichBatch(
                name="structure",
                kind="structure",
                node_ids=tuple(structural_ids),
            )
        )
    for file_nid, ids in by_file.items():
        batches.append(
            EnrichBatch(
                name=file_titles.get(file_nid, file_nid),
                kind="file_subtree",
                node_ids=tuple(ids),
            )
        )

    stats: dict[str, Any] = {
        "total_nodes": _count_nodes(tree["root"]),
        "stub_nodes": len(nodes),
        "by_kind": dict(by_kind),
    }
    generated_at = (now or _dt.datetime.now(_dt.timezone.utc)).isoformat(
        timespec="seconds"
    )

    return EnrichPlan(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at,
        context_dir=str(context_dir),
        tree_path="tree.json",
        stats=stats,
        batches=tuple(batches),
        nodes=tuple(nodes),
    )


def write_plan(path: Path, plan: EnrichPlan) -> None:
    """Atomically write the plan JSON to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(plan.to_dict(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of `apply_updates`.

    - `updated`: node_ids whose abstract changed (or whose confidence flipped
      to INFERRED).
    - `unknown`: node_ids in the input that don't match any node in tree.json
      — caller likely had a typo. The skill should surface these.
    """

    updated: tuple[str, ...]
    unknown: tuple[str, ...]


def apply_updates(context_dir: Path, updates: dict[str, str]) -> ApplyResult:
    """Merge `{node_id: new_abstract}` into tree.json.

    Updates each touched node's `abstract` and bumps `confidence` to
    `INFERRED`. Returns an ApplyResult with the touched ids and any
    ids in `updates` that didn't match a node in tree.json.
    """
    context_dir = context_dir.resolve()
    tree_path = context_dir / "tree.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8"))

    known_ids: set[str] = set()
    _collect_ids(tree["root"], known_ids)
    unknown = tuple(sorted(k for k in updates if k not in known_ids))

    updated = _apply(tree["root"], updates)

    tmp = tree_path.with_suffix(tree_path.suffix + ".tmp")
    tmp.write_text(json.dumps(tree, indent=2) + "\n", encoding="utf-8")
    tmp.replace(tree_path)
    return ApplyResult(updated=tuple(sorted(updated)), unknown=unknown)


# ----- internals -------------------------------------------------------------


def _walk(node: dict, current_file: Optional[str] = None) -> Iterator[tuple[dict, Optional[str]]]:
    """Pre-order traversal yielding (node, file_path_or_None_for_structural)."""
    next_file = current_file
    if node.get("kind") == "file":
        next_file = node.get("path") or current_file
    yield node, next_file if node.get("kind") not in ("project", "dir") else None
    for child in node.get("children", []):
        yield from _walk(child, next_file)


def _file_id_for_path(root: dict, file_path: str) -> Optional[str]:
    """Locate a file node by its `path` attribute."""
    stack = [root]
    while stack:
        n = stack.pop()
        if n.get("kind") == "file" and n.get("path") == file_path:
            return n["node_id"]
        stack.extend(n.get("children", []) or [])
    return None


def _count_nodes(node: dict) -> int:
    return 1 + sum(_count_nodes(c) for c in node.get("children", []) or [])


def _collect_ids(node: dict, out: set[str]) -> None:
    nid = node.get("node_id")
    if nid:
        out.add(nid)
    for child in node.get("children", []) or []:
        _collect_ids(child, out)


def _apply(node: dict, updates: dict[str, str]) -> list[str]:
    touched: list[str] = []
    nid = node.get("node_id")
    if nid and nid in updates:
        new_abstract = updates[nid]
        if (
            node.get("abstract") != new_abstract
            or node.get("confidence") != ConfidenceLevel.INFERRED
        ):
            node["abstract"] = new_abstract
            node["confidence"] = ConfidenceLevel.INFERRED
            touched.append(nid)
    for child in node.get("children", []) or []:
        touched.extend(_apply(child, updates))
    return touched
