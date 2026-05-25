"""`LanguageConfig` dataclass — the parametric driver for `_extract_generic`.

Every per-language extractor is either a thin wrapper that hands a
LanguageConfig to `_extract_generic`, or a custom walk that operates
without it (Julia, Go, Rust, etc.).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass
class LanguageConfig:
    ts_module: str                                   # e.g. "tree_sitter_python"
    ts_language_fn: str = "language"                 # attr to call: e.g. tslang.language()

    class_types: frozenset = frozenset()
    function_types: frozenset = frozenset()
    import_types: frozenset = frozenset()
    call_types: frozenset = frozenset()
    static_prop_types: frozenset = frozenset()
    helper_fn_names: frozenset = frozenset()
    container_bind_methods: frozenset = frozenset()
    event_listener_properties: frozenset = frozenset()

    # Name extraction
    name_field: str = "name"
    name_fallback_child_types: tuple = ()

    # Body detection
    body_field: str = "body"
    body_fallback_child_types: tuple = ()   # e.g. ("declaration_list", "compound_statement")

    # Call name extraction
    call_function_field: str = "function"           # field on call node for callee
    call_accessor_node_types: frozenset = frozenset()  # member/attribute nodes
    call_accessor_field: str = "attribute"          # field on accessor for method name

    # Stop recursion at these types in walk_calls
    function_boundary_types: frozenset = frozenset()

    # Import handler: called for import nodes instead of generic handling
    import_handler: Callable | None = None

    # Optional custom name resolver for functions (C, C++ declarator unwrapping)
    resolve_function_name_fn: Callable | None = None

    # Extra label formatting for functions: if True, functions get "name()" label
    function_label_parens: bool = True

    # Extra walk hook called after generic dispatch (for JS arrow functions, C# namespaces, etc.)
    extra_walk_fn: Callable | None = None

