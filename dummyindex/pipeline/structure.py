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

from collections import defaultdict
from pathlib import Path, PurePosixPath


SCHEMA_VERSION = "2.0"

HIERARCHY_RELATIONS = frozenset({"folder_contains", "contains", "method"})

# The structure graph includes *every* file under root by default, except
# those matched by an ignore file or by the built-in junk list. Ignore files
# are read by name in priority order (first found wins). Syntax matches
# .dummyindexignore / .gitignore style patterns.
_STRUCTURE_IGNORE_FILES = (".codeindexignore", ".dummyindexignore")

# Directories always skipped, even without any ignore file. Kept in sync with
# pipeline.detect._SKIP_DIRS so the two pipelines agree on obvious junk.
_STRUCTURE_SKIP_DIRS = frozenset({
    "dummyindex-out",
    ".context",  # dummyindex v2 output; skip self-generated content
    ".claude",   # Claude Code skills/settings — agent config, not source
    ".cursor", ".aider", ".kiro", ".trae", ".trae-cn",  # other agent configs
    ".github", ".gitlab",
    ".git",
    "node_modules", "__pycache__",
    ".venv", "venv", "env", ".env",
    "dist", "build", "target", "out",
    ".next", ".nuxt", ".svelte-kit",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".eggs",
    "site-packages", "lib64",
    ".idea", ".vscode", ".vs",
})


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
    _derive_textual_references(effective_files, root_abs, file_ids_by_rel, cross_edges)

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
            "confidence": edge.get("confidence", "EXTRACTED"),
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


def _rel_path(source_file: str, root_abs: Path) -> str:
    """Return a forward-slash path relative to root_abs.

    Source paths reach this function in several shapes: absolute (from tree-sitter
    extraction before relativization), cwd-relative (from ``collect_files``), or
    root-relative (after watch.py's relativize step). Try each in turn and take
    the first that lands inside ``root_abs``. Fall back to the raw string as a
    last resort so the node still gets placed somewhere deterministic.
    """
    if not source_file:
        return ""
    raw = Path(source_file)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(Path.cwd() / raw)
        candidates.append(root_abs / raw)
    for candidate in candidates:
        try:
            rel = candidate.resolve().relative_to(root_abs)
        except (ValueError, OSError):
            continue
        return rel.as_posix()
    return raw.as_posix().lstrip("./")


def _synth_id(prefix: str, key: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in key)
    cleaned = "_".join(part for part in cleaned.split("_") if part).lower()
    return f"{prefix}__{cleaned}" if cleaned else f"{prefix}__root"


def _derive_textual_references(
    effective_files: list[Path],
    root_abs: Path,
    file_ids_by_rel: dict[str, str],
    cross_edges: list[dict],
) -> None:
    """Scan every source file for textual mentions of other source files.

    Emits a generic ``references`` cross-edge for every match, tagged
    ``INFERRED``. The match offset is recorded in ``source_location`` as
    ``offset:<n>`` so a downstream LLM enrichment pass can pull the
    surrounding context and replace the relation with something semantically
    meaningful (``renders_template``, ``loads_config``, ``packages_file``,
    etc.). This module stays language-agnostic — no hand-coded rules about
    what specific frameworks or file types mean.

    To limit false positives on short or common names, basenames shorter than
    5 characters are only accepted when the full relative path appears
    verbatim; colliding basenames are also rejected so only the full-path
    form counts.
    """
    if not effective_files:
        return

    rel_to_id: dict[str, str] = {}
    basename_to_rels: dict[str, list[str]] = {}
    for path in effective_files:
        rel = _rel_path(str(path), root_abs)
        file_id = file_ids_by_rel.get(rel)
        if not rel or not file_id:
            continue
        rel_to_id[rel] = file_id
        basename_to_rels.setdefault(Path(rel).name, []).append(rel)

    existing_edge_keys = {
        (e["source"], e["target"], e.get("relation", ""))
        for e in cross_edges
    }

    for path in effective_files:
        src_rel = _rel_path(str(path), root_abs)
        src_id = rel_to_id.get(src_rel)
        if not src_id:
            continue
        text = _read_text_safely(path)
        if not text:
            continue
        for tgt_rel, tgt_id in rel_to_id.items():
            if tgt_id == src_id:
                continue
            match_idx = _find_reference(text, tgt_rel, basename_to_rels)
            if match_idx < 0:
                continue
            key = (src_id, tgt_id, "references")
            if key in existing_edge_keys:
                continue
            existing_edge_keys.add(key)
            cross_edges.append({
                "source": src_id,
                "target": tgt_id,
                "relation": "references",
                "confidence": "INFERRED",
                "source_file": src_rel,
                "source_location": f"offset:{match_idx}",
            })


def _find_reference(text: str, tgt_rel: str, basename_to_rels: dict[str, list[str]]) -> int:
    """Return the offset of the earliest textual mention of ``tgt_rel`` in
    ``text``, or -1 if none. Prefers the full relative path; falls back to the
    basename only when it's long and unambiguous.
    """
    idx = text.find(tgt_rel)
    if idx >= 0:
        return idx
    tgt_name = Path(tgt_rel).name
    if len(tgt_name) < 5:
        return -1
    collisions = basename_to_rels.get(tgt_name, [])
    if len(collisions) != 1:
        return -1
    return text.find(tgt_name)


def _read_text_safely(path: Path) -> str:
    """Return file text for scanning, empty string on any error or if too large."""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    # Skip files above 2MB — mostly vendored bundles we don't care about.
    if size > 2 * 1024 * 1024:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _discover_extra_source_files(root_abs: Path, code_files: list[Path]) -> list[Path]:
    """Walk ``root_abs`` and return every file not already in ``code_files``.

    Files and directories are excluded when they:
      * match a pattern in ``.codeindexignore`` (preferred) or ``.dummyindexignore``
      * are under a built-in junk directory (``_STRUCTURE_SKIP_DIRS``)
      * match a built-in ignore file itself (the ignore file doesn't index itself)

    No extension whitelist is applied — the tree reflects every real file in the
    source folder so downstream views are complete.
    """
    if not root_abs.exists() or not root_abs.is_dir():
        return []

    existing: set[str] = set()
    for path in code_files:
        rel = _rel_path(str(path), root_abs)
        if rel:
            existing.add(rel)

    ignore_matcher = _StructureIgnoreMatcher.load(root_abs)

    found: list[Path] = []
    stack: list[Path] = [root_abs]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            name = entry.name
            rel = _rel_path(str(entry), root_abs)
            if not rel:
                continue
            if entry.is_dir():
                if name in _STRUCTURE_SKIP_DIRS:
                    continue
                if ignore_matcher.matches(rel, is_dir=True):
                    continue
                stack.append(entry)
                continue
            if not entry.is_file():
                continue
            if name in _STRUCTURE_IGNORE_FILES:
                continue
            if ignore_matcher.matches(rel, is_dir=False):
                continue
            if rel in existing:
                continue
            existing.add(rel)
            found.append(entry)
    return found


class _StructureIgnoreMatcher:
    """Minimal gitignore-style matcher for the structure graph.

    Loads patterns from the first existing ``.codeindexignore`` or
    ``.dummyindexignore`` file at ``root``. Supports the common 95% of gitignore
    syntax: ``#`` comments, ``!`` negation, trailing ``/`` for directory-only,
    leading ``/`` for root-anchored, and ``*``/``?`` glob characters.
    """

    def __init__(self, rules: list[tuple[bool, str, bool, bool]]):
        # each rule: (negate, pattern, anchored, dir_only)
        self._rules = rules

    @classmethod
    def load(cls, root_abs: Path) -> "_StructureIgnoreMatcher":
        for name in _STRUCTURE_IGNORE_FILES:
            path = root_abs / name
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                return cls(cls._parse(content))
        return cls([])

    @staticmethod
    def _parse(content: str) -> list[tuple[bool, str, bool, bool]]:
        rules: list[tuple[bool, str, bool, bool]] = []
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = False
            if line.startswith("!"):
                negate = True
                line = line[1:].strip()
                if not line:
                    continue
            dir_only = False
            if line.endswith("/"):
                dir_only = True
                line = line.rstrip("/")
            anchored = False
            if line.startswith("/"):
                anchored = True
                line = line.lstrip("/")
            rules.append((negate, line, anchored, dir_only))
        return rules

    def matches(self, rel_path: str, is_dir: bool) -> bool:
        ignored = False
        for negate, pattern, anchored, dir_only in self._rules:
            if dir_only and not is_dir:
                continue
            if self._pattern_hits(pattern, rel_path, anchored):
                ignored = not negate
        return ignored

    @staticmethod
    def _pattern_hits(pattern: str, rel_path: str, anchored: bool) -> bool:
        import fnmatch
        # Normalize path separators for matching
        rel = rel_path
        if anchored:
            if fnmatch.fnmatch(rel, pattern):
                return True
            return fnmatch.fnmatch(rel, pattern + "/*")
        # If pattern has no slash, match the basename or any path segment
        if "/" not in pattern:
            if fnmatch.fnmatch(Path(rel).name, pattern):
                return True
            for part in rel.split("/"):
                if fnmatch.fnmatch(part, pattern):
                    return True
            return False
        # Pattern has slashes — match full rel path or any suffix / prefix
        if fnmatch.fnmatch(rel, pattern):
            return True
        if fnmatch.fnmatch(rel, pattern + "/*"):
            return True
        # Match at any depth via **
        if "**" in pattern:
            # crude: convert ** into * and re-check across segments
            flat = pattern.replace("**/", "").replace("/**", "")
            if fnmatch.fnmatch(rel, flat):
                return True
        return False
