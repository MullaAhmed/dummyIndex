"""Refresh structural navigation without discarding authored annotations."""

from __future__ import annotations

import json
import re
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.source_docs import DocCatalog
from dummyindex.context.output.docs import generate_project_md
from dummyindex.context.output.instructions import generate_architecture_overview_md

from .maps import FilesMap, SymbolsMap
from .meta import Meta
from .tree import _node_to_json, tree_from_structure


def _nodes(node: dict):
    yield node
    for child in node.get("children", []):
        yield from _nodes(child)


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Invalid navigation data; preserved: {path}")
    return value


def refresh_tree(
    context_dir: Path, structure: dict, root: Path, files_map: FilesMap
) -> None:
    """Rebuild children/ranges; carry annotated matching nodes and flag drift."""
    path = context_dir / "tree.json"
    old = _read(path).get("root", {})
    old_hashes = {
        entry["path"]: entry.get("sha256")
        for entry in _read(context_dir / "map/files.json").get("files", [])
    }
    new_hashes = {entry.path: entry.sha256 for entry in files_map.files}
    changed_paths = {
        p
        for p in old_hashes.keys() | new_hashes.keys()
        if not old_hashes.get(p) or old_hashes.get(p) != new_hashes.get(p)
    }
    old_nodes = list(_nodes(old)) if old else []
    by_id = {n.get("node_id"): n for n in old_nodes}
    by_location = {(n.get("kind"), n.get("path"), n.get("title")): n for n in old_nodes}
    tree = tree_from_structure(structure, root)
    fresh = _node_to_json(tree.root)
    for node in _nodes(fresh):
        previous = by_id.get(node["node_id"]) or by_location.get(
            (node.get("kind"), node.get("path"), node.get("title"))
        )
        if not previous:
            continue
        changed = previous.get("range") != node.get("range") or {
            (c.get("kind"), c.get("path"), c.get("title"))
            for c in previous.get("children", [])
        } != {
            (c.get("kind"), c.get("path"), c.get("title"))
            for c in node.get("children", [])
        }
        node_path = node.get("path")
        changed = changed or any(
            not node_path
            or node_path == "."
            or p == node_path
            or p.startswith(node_path.rstrip("/") + "/")
            for p in changed_paths
        )
        annotated = (
            previous.get("abstract") != node.get("abstract")
            or previous.get("confidence") == "INFERRED"
        )
        for key in (
            "abstract",
            "overview_ref",
            "detail_ref",
            "confidence",
            "labels",
            "evidence",
        ):
            if key in previous:
                node[key] = previous[key]
        if changed and annotated:
            node["labels"] = list(
                dict.fromkeys([*node.get("labels", []), "source-stale"])
            )
    write_text_atomic(
        path,
        json.dumps({"schema_version": tree.schema_version, "root": fresh}, indent=2)
        + "\n",
    )


def _sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    parts = re.split(r"(?m)(?=^## )", text)
    return parts[0], [(part.splitlines()[0][3:].strip(), part) for part in parts[1:]]


def _refresh_sections(path: Path, generated: str, names: tuple[str, ...]) -> None:
    """Replace mechanical sections only; retain other project notes verbatim."""
    try:
        old = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        write_text_atomic(path, generated)
        return
    prefix, sections = _sections(old)
    new_prefix, fresh = _sections(generated)
    fresh = dict(fresh)
    version = re.search(r"(?m)^_Version [^\n]+$", new_prefix)
    if version:
        prefix = re.sub(r"(?m)^_Version [^\n]+$", lambda _: version.group(), prefix)
    seen: set[str] = set()
    output: list[str] = []
    for name, section in sections:
        output.append(
            fresh[name]
            if name in names and name in fresh and name not in seen
            else section
        )
        seen.add(name)
    output.extend(fresh[name] for name in names if name not in seen and name in fresh)
    write_text_atomic(path, (prefix + "".join(output)).rstrip() + "\n")


def refresh_summaries(
    context_dir: Path,
    root: Path,
    meta: Meta,
    files_map: FilesMap,
    symbols_map: SymbolsMap,
    doc_catalog: DocCatalog,
) -> None:
    _refresh_sections(
        context_dir / "PROJECT.md",
        generate_project_md(root, meta, doc_catalog=doc_catalog),
        ("At a glance", "Entry points", "Existing documentation"),
    )
    _refresh_sections(
        context_dir / "architecture/overview.md",
        generate_architecture_overview_md(
            root, files_map, symbols_map, meta, doc_catalog=doc_catalog
        ),
        ("Stack", "Top-level layout", "Documented architecture"),
    )
