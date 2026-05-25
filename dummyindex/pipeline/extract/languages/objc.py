"""Objective-C extractor — tree-sitter, custom walk.

Classes, categories, protocols, methods, and imports become nodes +
edges. Both .m and .mm files (Objective-C++) route here.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel
from pathlib import Path
from typing import Any
from .._common import _make_id


def extract_objc(path: Path) -> dict:
    """Extract interfaces, implementations, protocols, methods, and imports from .m/.mm/.h files."""
    try:
        import tree_sitter_objc as tsobjc
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_objc not installed"}

    try:
        language = Language(tsobjc.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    method_bodies: list[tuple[str, Any]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = ConfidenceLevel.EXTRACTED, weight: float = 1.0) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": confidence, "source_file": str_path,
                      "source_location": f"L{line}", "weight": weight})

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _read(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_name(node, field: str) -> str | None:
        n = node.child_by_field_name(field)
        return _read(n) if n else None

    def walk(node, parent_nid: str | None = None) -> None:
        t = node.type
        line = node.start_point[0] + 1

        if t == "preproc_include":
            # #import <Foundation/Foundation.h> or #import "MyClass.h"
            for child in node.children:
                if child.type == "system_lib_string":
                    raw = _read(child).strip("<>")
                    module = raw.split("/")[-1].replace(".h", "")
                    if module:
                        tgt_nid = _make_id(module)
                        add_edge(file_nid, tgt_nid, "imports", line)
                elif child.type == "string_literal":
                    # recurse into string_literal to find string_content
                    for sub in child.children:
                        if sub.type == "string_content":
                            raw = _read(sub)
                            module = raw.split("/")[-1].replace(".h", "")
                            if module:
                                tgt_nid = _make_id(module)
                                add_edge(file_nid, tgt_nid, "imports", line)
            return

        if t == "class_interface":
            # @interface ClassName : SuperClass <Protocols>
            # children: @interface, identifier(name), ':', identifier(super), parameterized_arguments, ...
            identifiers = [c for c in node.children if c.type == "identifier"]
            if not identifiers:
                for child in node.children:
                    walk(child, parent_nid)
                return
            name = _read(identifiers[0])
            cls_nid = _make_id(stem, name)
            add_node(cls_nid, name, line)
            add_edge(file_nid, cls_nid, "contains", line)
            # superclass is second identifier after ':'
            colon_seen = False
            for child in node.children:
                if child.type == ":":
                    colon_seen = True
                elif colon_seen and child.type == "identifier":
                    super_nid = _make_id(_read(child))
                    add_edge(cls_nid, super_nid, "inherits", line)
                    colon_seen = False
                elif child.type == "parameterized_arguments":
                    # protocols adopted
                    for sub in child.children:
                        if sub.type == "type_name":
                            for s in sub.children:
                                if s.type == "type_identifier":
                                    proto_nid = _make_id(_read(s))
                                    add_edge(cls_nid, proto_nid, "imports", line)
                elif child.type == "method_declaration":
                    walk(child, cls_nid)
            return

        if t == "class_implementation":
            # @implementation ClassName
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = _read(child)
                    break
            if not name:
                for child in node.children:
                    walk(child, parent_nid)
                return
            impl_nid = _make_id(stem, name)
            if impl_nid not in seen_ids:
                add_node(impl_nid, name, line)
                add_edge(file_nid, impl_nid, "contains", line)
            for child in node.children:
                if child.type == "implementation_definition":
                    for sub in child.children:
                        walk(sub, impl_nid)
            return

        if t == "protocol_declaration":
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = _read(child)
                    break
            if name:
                proto_nid = _make_id(stem, name)
                add_node(proto_nid, f"<{name}>", line)
                add_edge(file_nid, proto_nid, "contains", line)
                for child in node.children:
                    walk(child, proto_nid)
            return

        if t in ("method_declaration", "method_definition"):
            container = parent_nid or file_nid
            # method name is the first identifier child (simple selector)
            # for compound selectors: identifier + method_parameter pairs
            parts = []
            for child in node.children:
                if child.type == "identifier":
                    parts.append(_read(child))
                elif child.type == "method_parameter":
                    for sub in child.children:
                        if sub.type == "identifier":
                            # selector keyword before ':'
                            pass
            method_name = "".join(parts) if parts else None
            if method_name:
                method_nid = _make_id(container, method_name)
                add_node(method_nid, f"-{method_name}", line)
                add_edge(container, method_nid, "method", line)
                if t == "method_definition":
                    method_bodies.append((method_nid, node))
            return

        for child in node.children:
            walk(child, parent_nid)

    walk(root)

    # Second pass: resolve calls inside method bodies
    all_method_nids = {n["id"] for n in nodes if n["id"] != file_nid}
    seen_calls: set[tuple[str, str]] = set()
    for caller_nid, body_node in method_bodies:
        def walk_calls(n) -> None:
            if n.type == "message_expression":
                # [receiver selector]
                for child in n.children:
                    if child.type in ("selector", "keyword_argument_list"):
                        sel = []
                        if child.type == "selector":
                            sel.append(_read(child))
                        else:
                            for sub in child.children:
                                if sub.type == "keyword_argument":
                                    for s in sub.children:
                                        if s.type == "selector":
                                            sel.append(_read(s))
                        method_name = "".join(sel)
                        for candidate in all_method_nids:
                            if candidate.endswith(_make_id("", method_name).lstrip("_")):
                                pair = (caller_nid, candidate)
                                if pair not in seen_calls and caller_nid != candidate:
                                    seen_calls.add(pair)
                                    add_edge(caller_nid, candidate, "calls", body_node.start_point[0] + 1,
                                             confidence=ConfidenceLevel.EXTRACTED, weight=1.0)
            for child in n.children:
                walk_calls(child)
        walk_calls(body_node)

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}
