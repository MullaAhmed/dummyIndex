"""Cross-file import resolution.

`extract()` runs the per-file pass first, then calls these to upgrade
file-level imports into class-level INFERRED edges. Currently:

- `_resolve_cross_file_imports` — Python (uses tree-sitter-python directly
  to re-parse classes referenced from `from x import Y` statements).
- `_resolve_cross_file_java_imports` — Java (resolves `import foo.bar.Baz`
  references to the actual `Baz` class node).
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel
from pathlib import Path
from .common import _make_id, _read_text
from ..io.cache import read_source_bytes


def _resolve_cross_file_imports(
    per_file: list[dict],
    paths: list[Path],
) -> list[dict]:
    """
    Two-pass import resolution: turn file-level imports into class-level edges.

    Pass 1 - build a global map: class/function name → node_id, per stem.
    Pass 2 - for each `from .module import Name`, look up Name in the global
              map and add a direct INFERRED edge from each class in the
              importing file to the imported entity.

    This turns:
        auth.py --imports_from--> models.py          (obvious, filtered out)
    Into:
        DigestAuth --uses--> Response  [INFERRED]    (cross-file, interesting!)
        BasicAuth  --uses--> Request   [INFERRED]
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    language = Language(tspython.language())
    parser = Parser(language)

    # Pass 1: name → node_id across all files
    # Map: stem → {ClassName: node_id}
    stem_to_entities: dict[str, dict[str, str]] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            src = node.get("source_file", "")
            if not src:
                continue
            stem = Path(src).stem
            label = node.get("label", "")
            nid = node.get("id", "")
            # Only index real classes/functions (not file nodes, not method stubs)
            if label and not label.endswith((")", ".py")) and "_" not in label[:1]:
                stem_to_entities.setdefault(stem, {})[label] = nid

    # Pass 2: for each file, find `from .X import A, B, C` and resolve
    new_edges: list[dict] = []

    for file_result, path in zip(per_file, paths):
        stem = path.stem
        str_path = str(path)

        # Find all classes defined in this file (the importers)
        local_classes = [
            n["id"] for n in file_result.get("nodes", [])
            if n.get("source_file") == str_path
            and not n["label"].endswith((")", ".py"))
            and n["id"] != _make_id(stem)  # exclude file-level node
        ]
        if not local_classes:
            continue

        # Parse imports from this file
        try:
            source = read_source_bytes(path)
            tree = parser.parse(source)
        except Exception:
            continue

        def walk_imports(node) -> None:
            if node.type == "import_from_statement":
                # Find the module name - handles both absolute and relative imports.
                # Relative: `from .models import X` → relative_import → dotted_name
                # Absolute: `from models import X`  → module_name field
                target_stem: str | None = None
                for child in node.children:
                    if child.type == "relative_import":
                        # Dig into relative_import → dotted_name → identifier
                        for sub in child.children:
                            if sub.type == "dotted_name":
                                raw = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                                target_stem = raw.split(".")[-1]
                                break
                        break
                    if child.type == "dotted_name" and target_stem is None:
                        raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        target_stem = raw.split(".")[-1]

                if not target_stem or target_stem not in stem_to_entities:
                    return

                # Collect imported names: dotted_name children of import_from_statement
                # that come AFTER the 'import' keyword token.
                imported_names: list[str] = []
                past_import_kw = False
                for child in node.children:
                    if child.type == "import":
                        past_import_kw = True
                        continue
                    if not past_import_kw:
                        continue
                    if child.type == "dotted_name":
                        imported_names.append(
                            source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        )
                    elif child.type == "aliased_import":
                        # `import X as Y` - take the original name
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            imported_names.append(
                                source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                            )

                line = node.start_point[0] + 1
                for name in imported_names:
                    tgt_nid = stem_to_entities[target_stem].get(name)
                    if tgt_nid:
                        for src_class_nid in local_classes:
                            new_edges.append({
                                "source": src_class_nid,
                                "target": tgt_nid,
                                "relation": "uses",
                                "confidence": ConfidenceLevel.INFERRED,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 0.8,
                            })
            for child in node.children:
                walk_imports(child)

        walk_imports(tree.root_node)

    return new_edges


def _resolve_cross_file_java_imports(
    per_file: list[dict],
    paths: list[Path],
) -> list[dict]:
    """Two-pass Java import resolution.

    Pass 1: build a global index {ClassName: [node_id, ...]} across all Java nodes.
    Pass 2: re-parse each Java file; for every `import a.b.C;`, resolve C against
    the index. Wildcard and stdlib imports produce no edge.
    """
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    language = Language(tsjava.language())
    parser = Parser(language)

    # Pass 1: class-name → node_id index (only internal, uppercase-starting names)
    name_to_ids: dict[str, list[str]] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            label = node.get("label", "")
            nid = node.get("id", "")
            src = node.get("source_file", "")
            if not label or not nid or not src:
                continue
            if label.endswith(")") or label.endswith(".java"):
                continue
            if not label[0].isalpha() or not label[0].isupper():
                continue
            name_to_ids.setdefault(label, []).append(nid)

    # Pass 2: resolve imports to real node IDs
    new_edges: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for path in paths:
        file_nid = _make_id(path.stem)
        try:
            source = read_source_bytes(path)
            tree = parser.parse(source)
        except Exception:
            continue

        def walk(n) -> None:
            if n.type == "import_declaration":
                raw = _read_text(n, source).strip()
                body = raw[len("import"):].strip().rstrip(";").strip()
                if body.startswith("static "):
                    body = body[len("static "):].strip()
                if body.endswith(".*"):
                    return
                parts = body.split(".")
                if not parts:
                    return
                last = parts[-1]
                if last and last[0].islower() and len(parts) >= 2:
                    last = parts[-2]
                at_line = n.start_point[0] + 1
                for tgt_nid in name_to_ids.get(last, []):
                    if tgt_nid == file_nid:
                        continue
                    key = (file_nid, tgt_nid)
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    new_edges.append({
                        "source": file_nid,
                        "target": tgt_nid,
                        "relation": "imports",
                        "confidence": ConfidenceLevel.EXTRACTED,
                        "confidence_score": 1.0,
                        "source_file": str(path),
                        "source_location": f"L{at_line}",
                        "weight": 1.0,
                    })
            for child in n.children:
                walk(child)

        walk(tree.root_node)

    return new_edges

