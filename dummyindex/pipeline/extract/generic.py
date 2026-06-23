"""Generic AST extractor driven by `LanguageConfig`.

`_extract_generic(path, config)` is the workhorse: ~12 of the supported
languages delegate to it through thin wrappers in
`languages/wrappers.py`. It walks the tree-sitter parse, emits nodes
for classes / functions / methods, dispatches imports via
`config.import_handler`, and performs a second-pass call-graph walk
inside every function body.

The function is large (~600 lines) but indivisible — splitting it would
require threading too much state across modules. It sits in `extremis`
per docs/reference/01-conventions.md §4.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from dummyindex.pipeline.enums import ConfidenceLevel

from ..io.cache import read_source_bytes
from .common import _find_body, _make_id, _read_text
from .config import LanguageConfig
from .helpers import _csharp_extra_walk, _js_extra_walk, _swift_extra_walk


def _extract_generic(path: Path, config: LanguageConfig) -> dict:
    """Generic AST extractor driven by LanguageConfig."""
    try:
        mod = importlib.import_module(config.ts_module)
        from tree_sitter import Language, Parser

        lang_fn = getattr(mod, config.ts_language_fn, None)
        if lang_fn is None:
            # Fallback for PHP: try "language_php" then "language"
            lang_fn = getattr(mod, "language", None)
        if lang_fn is None:
            return {
                "nodes": [],
                "edges": [],
                "error": f"No language function in {config.ts_module}",
            }
        language = Language(lang_fn())
    except ImportError:
        return {"nodes": [], "edges": [], "error": f"{config.ts_module} not installed"}
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    try:
        parser = Parser(language)
        source = read_source_bytes(path)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = path.stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []
    pending_listen_edges: list[tuple[str, str, int]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "file_type": "code",
                    "source_file": str_path,
                    "source_location": f"L{line}",
                }
            )

    def add_edge(
        src: str,
        tgt: str,
        relation: str,
        line: int,
        confidence: str = ConfidenceLevel.EXTRACTED,
        weight: float = 1.0,
    ) -> None:
        edges.append(
            {
                "source": src,
                "target": tgt,
                "relation": relation,
                "confidence": confidence,
                "source_file": str_path,
                "source_location": f"L{line}",
                "weight": weight,
            }
        )

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        # Import types
        if t in config.import_types:
            if config.import_handler:
                config.import_handler(node, source, file_nid, stem, edges, str_path)
            return

        # Class types
        if t in config.class_types:
            # Resolve class name
            name_node = node.child_by_field_name(config.name_field)
            if name_node is None:
                for child in node.children:
                    if child.type in config.name_fallback_child_types:
                        name_node = child
                        break
            if not name_node:
                return
            class_name = _read_text(name_node, source)
            class_nid = _make_id(stem, class_name)
            line = node.start_point[0] + 1
            add_node(class_nid, class_name, line)
            add_edge(file_nid, class_nid, "contains", line)

            # Python-specific: inheritance
            if config.ts_module == "tree_sitter_python":
                args = node.child_by_field_name("superclasses")
                if args:
                    for arg in args.children:
                        if arg.type == "identifier":
                            base = _read_text(arg, source)
                            base_nid = _make_id(stem, base)
                            if base_nid not in seen_ids:
                                base_nid = _make_id(base)
                                if base_nid not in seen_ids:
                                    nodes.append(
                                        {
                                            "id": base_nid,
                                            "label": base,
                                            "file_type": "code",
                                            "source_file": "",
                                            "source_location": "",
                                        }
                                    )
                                    seen_ids.add(base_nid)
                            add_edge(class_nid, base_nid, "inherits", line)

            # Swift-specific: conformance / inheritance
            if config.ts_module == "tree_sitter_swift":
                for child in node.children:
                    if child.type == "inheritance_specifier":
                        for sub in child.children:
                            if sub.type in ("user_type", "type_identifier"):
                                base = _read_text(sub, source)
                                base_nid = _make_id(stem, base)
                                if base_nid not in seen_ids:
                                    base_nid = _make_id(base)
                                    if base_nid not in seen_ids:
                                        nodes.append(
                                            {
                                                "id": base_nid,
                                                "label": base,
                                                "file_type": "code",
                                                "source_file": "",
                                                "source_location": "",
                                            }
                                        )
                                        seen_ids.add(base_nid)
                                add_edge(class_nid, base_nid, "inherits", line)

            # C#-specific: inheritance / interface implementation via base_list
            if config.ts_module == "tree_sitter_c_sharp":
                for child in node.children:
                    if child.type == "base_list":
                        for sub in child.children:
                            if sub.type in ("identifier", "generic_name"):
                                if sub.type == "generic_name":
                                    name_child = sub.child_by_field_name("name")
                                    base = (
                                        _read_text(name_child, source)
                                        if name_child
                                        else _read_text(sub.children[0], source)
                                    )
                                else:
                                    base = _read_text(sub, source)
                                base_nid = _make_id(stem, base)
                                if base_nid not in seen_ids:
                                    base_nid = _make_id(base)
                                    if base_nid not in seen_ids:
                                        nodes.append(
                                            {
                                                "id": base_nid,
                                                "label": base,
                                                "file_type": "code",
                                                "source_file": "",
                                                "source_location": "",
                                            }
                                        )
                                        seen_ids.add(base_nid)
                                add_edge(class_nid, base_nid, "inherits", line)

            # Java-specific: extends (superclass) / implements (interfaces) / interface-extends
            if config.ts_module == "tree_sitter_java":

                def _emit_java_parent(base_name: str, rel: str, at_line: int) -> None:
                    if not base_name:
                        return
                    base_nid = _make_id(stem, base_name)
                    if base_nid not in seen_ids:
                        base_nid = _make_id(base_name)
                        if base_nid not in seen_ids:
                            nodes.append(
                                {
                                    "id": base_nid,
                                    "label": base_name,
                                    "file_type": "code",
                                    "source_file": "",
                                    "source_location": "",
                                }
                            )
                            seen_ids.add(base_nid)
                    add_edge(class_nid, base_nid, rel, at_line)

                sup = node.child_by_field_name("superclass")
                if sup is not None:
                    for sub in sup.children:
                        if sub.type == "type_identifier":
                            _emit_java_parent(_read_text(sub, source), "extends", line)
                            break

                ifs = node.child_by_field_name("interfaces")
                if ifs is not None:
                    for sub in ifs.children:
                        if sub.type == "type_list":
                            for tid in sub.children:
                                if tid.type == "type_identifier":
                                    _emit_java_parent(
                                        _read_text(tid, source), "implements", line
                                    )

                if t == "interface_declaration":
                    for child in node.children:
                        if child.type == "extends_interfaces":
                            for sub in child.children:
                                if sub.type == "type_list":
                                    for tid in sub.children:
                                        if tid.type == "type_identifier":
                                            _emit_java_parent(
                                                _read_text(tid, source), "extends", line
                                            )

            # Find body and recurse
            body = _find_body(node, config)
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        # Event listener property arrays: $listen = [Event::class => [Listener::class]]
        if (
            t == "property_declaration"
            and parent_class_nid
            and config.event_listener_properties
        ):
            for element in node.children:
                if element.type != "property_element":
                    continue
                prop_name: str | None = None
                array_node = None
                for c in element.children:
                    if c.type == "variable_name":
                        for sc in c.children:
                            if sc.type == "name":
                                prop_name = _read_text(sc, source)
                                break
                    elif c.type == "array_creation_expression":
                        array_node = c
                if (
                    prop_name is None
                    or prop_name not in config.event_listener_properties
                    or array_node is None
                ):
                    continue
                for entry in array_node.children:
                    if entry.type != "array_element_initializer":
                        continue
                    event_cls: str | None = None
                    listener_arr = None
                    for sub in entry.children:
                        if (
                            sub.type == "class_constant_access_expression"
                            and event_cls is None
                        ):
                            for sc in sub.children:
                                if sc.is_named and sc.type in (
                                    "name",
                                    "qualified_name",
                                ):
                                    event_cls = _read_text(sc, source)
                                    break
                        elif sub.type == "array_creation_expression":
                            listener_arr = sub
                    if not event_cls or listener_arr is None:
                        continue
                    for listener_entry in listener_arr.children:
                        if listener_entry.type != "array_element_initializer":
                            continue
                        for item in listener_entry.children:
                            if item.type != "class_constant_access_expression":
                                continue
                            for sc in item.children:
                                if sc.is_named and sc.type in (
                                    "name",
                                    "qualified_name",
                                ):
                                    listener_cls = _read_text(sc, source)
                                    line_no = item.start_point[0] + 1
                                    pending_listen_edges.append(
                                        (event_cls, listener_cls, line_no)
                                    )
                                    break
                            break
            return

        # Function types
        if t in config.function_types:
            # Swift deinit/subscript have no name field — resolve before generic fallback
            if t == "deinit_declaration":
                func_name: str | None = "deinit"
            elif t == "subscript_declaration":
                func_name = "subscript"
            elif config.resolve_function_name_fn is not None:
                # C/C++ style: use declarator
                declarator = node.child_by_field_name("declarator")
                func_name = None
                if declarator:
                    func_name = config.resolve_function_name_fn(declarator, source)
            else:
                name_node = node.child_by_field_name(config.name_field)
                if name_node is None:
                    for child in node.children:
                        if child.type in config.name_fallback_child_types:
                            name_node = child
                            break
                func_name = _read_text(name_node, source) if name_node else None

            if not func_name:
                return

            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line)
                add_edge(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)

            body = _find_body(node, config)
            if body:
                function_bodies.append((func_nid, body))
            return

        # JS/TS arrow functions and C# namespaces — language-specific extra handling
        if config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
            if _js_extra_walk(
                node,
                source,
                file_nid,
                stem,
                str_path,
                nodes,
                edges,
                seen_ids,
                function_bodies,
                parent_class_nid,
                add_node,
                add_edge,
            ):
                return

        if config.ts_module == "tree_sitter_c_sharp":
            if _csharp_extra_walk(
                node,
                source,
                file_nid,
                stem,
                str_path,
                nodes,
                edges,
                seen_ids,
                function_bodies,
                parent_class_nid,
                add_node,
                add_edge,
                walk,
            ):
                return

        if config.ts_module == "tree_sitter_swift":
            if _swift_extra_walk(
                node,
                source,
                file_nid,
                stem,
                str_path,
                nodes,
                edges,
                seen_ids,
                function_bodies,
                parent_class_nid,
                add_node,
                add_edge,
            ):
                return

        # Default: recurse
        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    # ── Call-graph pass ───────────────────────────────────────────────────────
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    seen_static_ref_pairs: set[tuple[str, str, str]] = set()
    seen_helper_ref_pairs: set[tuple[str, str, str]] = set()
    seen_bind_pairs: set[tuple[str, str, str]] = set()
    raw_calls: list[
        dict
    ] = []  # unresolved calls for cross-file resolution in extract()

    def _php_class_const_scope(n) -> str | None:
        scope = n.child_by_field_name("scope")
        if scope is None:
            for c in n.children:
                if c.is_named and c.type in ("name", "qualified_name", "identifier"):
                    scope = c
                    break
        if scope is None:
            return None
        return _read_text(scope, source)

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in config.function_boundary_types:
            return

        if node.type in config.call_types:
            callee_name: str | None = None

            # Special handling per language
            if config.ts_module == "tree_sitter_swift":
                # Swift: first child may be simple_identifier or navigation_expression
                first = node.children[0] if node.children else None
                if first:
                    if first.type == "simple_identifier":
                        callee_name = _read_text(first, source)
                    elif first.type == "navigation_expression":
                        for child in first.children:
                            if child.type == "navigation_suffix":
                                for sc in child.children:
                                    if sc.type == "simple_identifier":
                                        callee_name = _read_text(sc, source)
            elif config.ts_module == "tree_sitter_kotlin":
                # Kotlin: first child may be simple_identifier or navigation_expression
                first = node.children[0] if node.children else None
                if first:
                    if first.type == "simple_identifier":
                        callee_name = _read_text(first, source)
                    elif first.type == "navigation_expression":
                        for child in reversed(first.children):
                            if child.type == "simple_identifier":
                                callee_name = _read_text(child, source)
                                break
            elif config.ts_module == "tree_sitter_scala":
                # Scala: first child
                first = node.children[0] if node.children else None
                if first:
                    if first.type == "identifier":
                        callee_name = _read_text(first, source)
                    elif first.type == "field_expression":
                        field = first.child_by_field_name("field")
                        if field:
                            callee_name = _read_text(field, source)
                        else:
                            for child in reversed(first.children):
                                if child.type == "identifier":
                                    callee_name = _read_text(child, source)
                                    break
            elif (
                config.ts_module == "tree_sitter_c_sharp"
                and node.type == "invocation_expression"
            ):
                # C#: try name field, then first named child
                name_node = node.child_by_field_name("name")
                if name_node:
                    callee_name = _read_text(name_node, source)
                else:
                    for child in node.children:
                        if child.is_named:
                            raw = _read_text(child, source)
                            if "." in raw:
                                callee_name = raw.split(".")[-1]
                            else:
                                callee_name = raw
                            break
            elif config.ts_module == "tree_sitter_php":
                # PHP: distinguish call expression subtypes
                if node.type == "function_call_expression":
                    func_node = node.child_by_field_name("function")
                    if func_node:
                        callee_name = _read_text(func_node, source)
                elif node.type == "scoped_call_expression":
                    # Static method call: Helper::format() → callee = "Helper"
                    scope_node = node.child_by_field_name("scope")
                    if scope_node:
                        callee_name = _read_text(scope_node, source)
                else:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        callee_name = _read_text(name_node, source)
            elif config.ts_module == "tree_sitter_cpp":
                # C++: function field, then field_expression/qualified_identifier
                func_node = (
                    node.child_by_field_name(config.call_function_field)
                    if config.call_function_field
                    else None
                )
                if func_node:
                    if func_node.type == "identifier":
                        callee_name = _read_text(func_node, source)
                    elif func_node.type in ("field_expression", "qualified_identifier"):
                        name = func_node.child_by_field_name(
                            "field"
                        ) or func_node.child_by_field_name("name")
                        if name:
                            callee_name = _read_text(name, source)
            else:
                # Generic: get callee from call_function_field
                func_node = (
                    node.child_by_field_name(config.call_function_field)
                    if config.call_function_field
                    else None
                )
                if func_node:
                    if func_node.type == "identifier":
                        callee_name = _read_text(func_node, source)
                    elif func_node.type in config.call_accessor_node_types:
                        if config.call_accessor_field:
                            attr = func_node.child_by_field_name(
                                config.call_accessor_field
                            )
                            if attr:
                                callee_name = _read_text(attr, source)
                    else:
                        # Try reading the node directly (e.g. Java name field is the callee)
                        callee_name = _read_text(func_node, source)

            if callee_name:
                tgt_nid = label_to_nid.get(callee_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append(
                            {
                                "source": caller_nid,
                                "target": tgt_nid,
                                "relation": "calls",
                                "confidence": ConfidenceLevel.EXTRACTED,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            }
                        )
                elif callee_name and not tgt_nid:
                    # Callee not in this file — save for cross-file resolution in extract()
                    raw_calls.append(
                        {
                            "caller_nid": caller_nid,
                            "callee": callee_name,
                            "source_file": str_path,
                            "source_location": f"L{node.start_point[0] + 1}",
                        }
                    )

            # Helper function calls: config('foo.bar') → uses_config edge to "foo"
            if callee_name and callee_name in config.helper_fn_names:
                args_node = node.child_by_field_name("arguments")
                first_key: str | None = None
                if args_node:
                    for arg in args_node.children:
                        if arg.type != "argument":
                            continue
                        for inner in arg.children:
                            if inner.type == "string":
                                for sc in inner.children:
                                    if sc.type == "string_content":
                                        first_key = _read_text(sc, source)
                                        break
                                break
                        if first_key:
                            break
                if first_key:
                    segment = first_key.split(".")[0]
                    tgt_nid = label_to_nid.get(segment.lower()) or label_to_nid.get(
                        f"{segment}.php".lower()
                    )
                    if tgt_nid and tgt_nid != caller_nid:
                        relation = f"uses_{callee_name}"
                        pair3 = (caller_nid, tgt_nid, relation)
                        if pair3 not in seen_helper_ref_pairs:
                            seen_helper_ref_pairs.add(pair3)
                            line = node.start_point[0] + 1
                            edges.append(
                                {
                                    "source": caller_nid,
                                    "target": tgt_nid,
                                    "relation": relation,
                                    "confidence": ConfidenceLevel.EXTRACTED,
                                    "confidence_score": 1.0,
                                    "source_file": str_path,
                                    "source_location": f"L{line}",
                                    "weight": 1.0,
                                }
                            )

            # Service container bindings: $this->app->bind(Foo::class, Bar::class)
            if (
                node.type == "member_call_expression"
                and callee_name
                and callee_name in config.container_bind_methods
            ):
                args_node = node.child_by_field_name("arguments")
                class_args: list[str] = []
                if args_node:
                    for arg in args_node.children:
                        if arg.type != "argument":
                            continue
                        for inner in arg.children:
                            if inner.type == "class_constant_access_expression":
                                cls = _php_class_const_scope(inner)
                                if cls:
                                    class_args.append(cls)
                                break
                        if len(class_args) >= 2:
                            break
                if len(class_args) == 2:
                    contract_name, impl_name = class_args
                    contract_nid = label_to_nid.get(contract_name.lower())
                    impl_nid = label_to_nid.get(impl_name.lower())
                    if contract_nid and impl_nid and contract_nid != impl_nid:
                        pair3 = (contract_nid, impl_nid, "bound_to")
                        if pair3 not in seen_bind_pairs:
                            seen_bind_pairs.add(pair3)
                            line = node.start_point[0] + 1
                            edges.append(
                                {
                                    "source": contract_nid,
                                    "target": impl_nid,
                                    "relation": "bound_to",
                                    "confidence": ConfidenceLevel.EXTRACTED,
                                    "confidence_score": 1.0,
                                    "source_file": str_path,
                                    "source_location": f"L{line}",
                                    "weight": 1.0,
                                }
                            )

        # Static property access: Foo::$bar → uses_static_prop edge
        if node.type in config.static_prop_types:
            scope_node = node.child_by_field_name("scope")
            if scope_node is None:
                for child in node.children:
                    if child.is_named and child.type in (
                        "name",
                        "qualified_name",
                        "identifier",
                    ):
                        scope_node = child
                        break
            if scope_node is not None:
                class_name = _read_text(scope_node, source)
                tgt_nid = label_to_nid.get(class_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair3 = (caller_nid, tgt_nid, "uses_static_prop")
                    if pair3 not in seen_static_ref_pairs:
                        seen_static_ref_pairs.add(pair3)
                        line = node.start_point[0] + 1
                        edges.append(
                            {
                                "source": caller_nid,
                                "target": tgt_nid,
                                "relation": "uses_static_prop",
                                "confidence": ConfidenceLevel.EXTRACTED,
                                "confidence_score": 1.0,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            }
                        )

        # PHP class constant access: Foo::BAR → references_constant edge
        if (
            config.ts_module == "tree_sitter_php"
            and node.type == "class_constant_access_expression"
        ):
            class_name = _php_class_const_scope(node)
            if class_name:
                tgt_nid = label_to_nid.get(class_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair3 = (caller_nid, tgt_nid, "references_constant")
                    if pair3 not in seen_static_ref_pairs:
                        seen_static_ref_pairs.add(pair3)
                        line = node.start_point[0] + 1
                        edges.append(
                            {
                                "source": caller_nid,
                                "target": tgt_nid,
                                "relation": "references_constant",
                                "confidence": ConfidenceLevel.EXTRACTED,
                                "confidence_score": 1.0,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            }
                        )

        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    # ── Event listener pass ───────────────────────────────────────────────────
    seen_listen_pairs: set[tuple[str, str]] = set()
    for event_name, listener_name, line in pending_listen_edges:
        event_nid = label_to_nid.get(event_name.lower())
        listener_nid = label_to_nid.get(listener_name.lower())
        if not event_nid or not listener_nid or event_nid == listener_nid:
            continue
        pair2 = (event_nid, listener_nid)
        if pair2 in seen_listen_pairs:
            continue
        seen_listen_pairs.add(pair2)
        edges.append(
            {
                "source": event_nid,
                "target": listener_nid,
                "relation": "listened_by",
                "confidence": ConfidenceLevel.EXTRACTED,
                "confidence_score": 1.0,
                "source_file": str_path,
                "source_location": f"L{line}",
                "weight": 1.0,
            }
        )

    # ── Clean edges ───────────────────────────────────────────────────────────
    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (
            tgt in valid_ids or edge["relation"] in ("imports", "imports_from")
        ):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
