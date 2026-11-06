"""Refresh structural navigation without discarding authored annotations."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.source_docs import DocCatalog
from dummyindex.context.output.docs import generate_project_md
from dummyindex.context.output.instructions import generate_architecture_overview_md

from .maps import FilesMap, SymbolsMap
from .meta import Meta
from .tree import _language_for_path, _node_to_json, tree_from_structure


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


def _mechanical_abstract(node: dict) -> bool:
    if node.get("confidence") != "EXTRACTED":
        return False
    kind, title, path = node.get("kind"), node.get("title"), node.get("path")
    count = len(node.get("children", []))
    if kind == "project":
        expected = f"Codebase rooted at {title}."
    elif kind == "dir":
        expected = f"Directory at {path}/ ({count} immediate children)."
    elif kind == "file" and isinstance(path, str):
        expected = f"{_language_for_path(path) or 'source'} file at {path} ({count} top-level definitions)."
    elif kind in {"class", "method", "function"}:
        start = (node.get("range") or [None])[0]
        expected = (
            f"{kind.capitalize()} {title} at {path}"
            + (f":{start}" if start else "")
            + "."
        )
    else:
        return False
    actual = node.get("abstract", "")
    if actual == expected:
        return True
    # Older refreshes could carry an obsolete generated count/line. Bind the
    # exact title and path; extra authored prose never matches this grammar.
    if kind in {"class", "method", "function"}:
        pattern = re.escape(f"{kind.capitalize()} {title} at {path}") + r"(?::\d+)?\."
    elif kind == "dir":
        pattern = re.escape(f"Directory at {path}/ ") + r"\(\d+ immediate children\)\."
    elif kind == "file" and isinstance(path, str):
        pattern = (
            re.escape(f"{_language_for_path(path) or 'source'} file at {path} ")
            + r"\(\d+ top-level definitions\)\."
        )
    else:
        return False
    return bool(re.fullmatch(pattern, actual))


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
    old_counts = Counter(n.get("node_id") for n in old_nodes)
    by_location = {(n.get("kind"), n.get("path"), n.get("title")): n for n in old_nodes}
    old_locations = Counter(
        (n.get("kind"), n.get("path"), n.get("title")) for n in old_nodes
    )
    tree = tree_from_structure(structure, root)
    fresh = _node_to_json(tree.root)
    new_counts = Counter(n.get("node_id") for n in _nodes(fresh))
    new_locations = Counter(
        (n.get("kind"), n.get("path"), n.get("title")) for n in _nodes(fresh)
    )
    for node in _nodes(fresh):
        location = (node.get("kind"), node.get("path"), node.get("title"))
        previous = (
            by_location.get(location)
            if old_locations[location] == new_locations[location] == 1
            else None
        )
        if (
            not previous
            and old_counts[node["node_id"]] == new_counts[node["node_id"]] == 1
        ):
            previous = by_id.get(node["node_id"])
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
        annotated = not _mechanical_abstract(previous)
        for key in (
            "abstract",
            "overview_ref",
            "detail_ref",
            "confidence",
            "labels",
            "evidence",
        ):
            if key in previous:
                if key == "abstract" and not annotated:
                    continue
                node[key] = previous[key]
        if not annotated:
            node["labels"] = [
                label for label in node.get("labels", []) if label != "source-stale"
            ]
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
