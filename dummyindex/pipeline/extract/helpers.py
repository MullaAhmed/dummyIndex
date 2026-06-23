"""Per-language name-resolution and grammar-quirk helpers.

`_get_c_func_name` / `_get_cpp_func_name` unwrap declarator nests for C
and C++ function definitions. `_<lang>_extra_walk` functions are called
by `_extract_generic` for grammar nodes that don't fit the generic
class/function dispatch (JS/TS arrow functions, C# namespaces, Swift
enum cases).
"""

from __future__ import annotations

from .common import _make_id, _read_text


def _get_c_func_name(node, source: bytes) -> str | None:
    """Recursively unwrap declarator to find the innermost identifier (C)."""
    if node.type == "identifier":
        return _read_text(node, source)
    decl = node.child_by_field_name("declarator")
    if decl:
        return _get_c_func_name(decl, source)
    for child in node.children:
        if child.type == "identifier":
            return _read_text(child, source)
    return None


def _get_cpp_func_name(node, source: bytes) -> str | None:
    """Recursively unwrap declarator to find the innermost identifier (C++)."""
    if node.type == "identifier":
        return _read_text(node, source)
    if node.type == "qualified_identifier":
        name_node = node.child_by_field_name("name")
        if name_node:
            return _read_text(name_node, source)
    decl = node.child_by_field_name("declarator")
    if decl:
        return _get_cpp_func_name(decl, source)
    for child in node.children:
        if child.type == "identifier":
            return _read_text(child, source)
    return None


# ── JS/TS extra walk for arrow functions ──────────────────────────────────────


def _js_extra_walk(
    node,
    source: bytes,
    file_nid: str,
    stem: str,
    str_path: str,
    nodes: list,
    edges: list,
    seen_ids: set,
    function_bodies: list,
    parent_class_nid: str | None,
    add_node_fn,
    add_edge_fn,
) -> bool:
    """Handle lexical_declaration (arrow functions) for JS/TS. Returns True if handled."""
    if node.type == "lexical_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                value = child.child_by_field_name("value")
                if value and value.type == "arrow_function":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        func_name = _read_text(name_node, source)
                        line = child.start_point[0] + 1
                        func_nid = _make_id(stem, func_name)
                        add_node_fn(func_nid, f"{func_name}()", line)
                        add_edge_fn(file_nid, func_nid, "contains", line)
                        body = value.child_by_field_name("body")
                        if body:
                            function_bodies.append((func_nid, body))
        return True
    return False


# ── C# extra walk for namespace declarations ──────────────────────────────────


def _csharp_extra_walk(
    node,
    source: bytes,
    file_nid: str,
    stem: str,
    str_path: str,
    nodes: list,
    edges: list,
    seen_ids: set,
    function_bodies: list,
    parent_class_nid: str | None,
    add_node_fn,
    add_edge_fn,
    walk_fn,
) -> bool:
    """Handle namespace_declaration for C#. Returns True if handled."""
    if node.type == "namespace_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            ns_name = _read_text(name_node, source)
            ns_nid = _make_id(stem, ns_name)
            line = node.start_point[0] + 1
            add_node_fn(ns_nid, ns_name, line)
            add_edge_fn(file_nid, ns_nid, "contains", line)
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                walk_fn(child, parent_class_nid)
        return True
    return False


# ── Swift extra walk for enum cases ──────────────────────────────────────────


def _swift_extra_walk(
    node,
    source: bytes,
    file_nid: str,
    stem: str,
    str_path: str,
    nodes: list,
    edges: list,
    seen_ids: set,
    function_bodies: list,
    parent_class_nid: str | None,
    add_node_fn,
    add_edge_fn,
) -> bool:
    """Handle enum_entry for Swift. Returns True if handled."""
    if node.type == "enum_entry" and parent_class_nid:
        for child in node.children:
            if child.type == "simple_identifier":
                case_name = _read_text(child, source)
                case_nid = _make_id(parent_class_nid, case_name)
                line = node.start_point[0] + 1
                add_node_fn(case_nid, case_name, line)
                add_edge_fn(parent_class_nid, case_nid, "case_of", line)
        return True
    return False
