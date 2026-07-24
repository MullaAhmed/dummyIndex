"""Narrow Python dispatch-idiom resolver (post-pass over per-file results).

Closes two callers-of / dead-code blind spots that every reference tool in
the 2026-07 bakeoff shared (proposal `graph-consumption-upgrade`, item A4):

- **Enum-keyed dispatch dicts** — ``{ContextSubcommand.SCAN_CHECK: scan.run}``
  now yields a ``calls`` edge from the mapping's enclosing scope (file,
  class, or function node) to the referenced handler symbol.
- **Function-body imports** — ``from X import Y`` inside a function body now
  yields an ``imports_from`` edge attributed to the enclosing function's
  module (previously only module-level imports were seen).

Precision over recall: a dict value resolves only when it matches a known
extracted symbol AND (for ``module.attr`` values) the object name is bound
by an import in the same file. A ``(stem, name)`` claimed by more than one
source file is ambiguous and skipped — no guessing across packages. New
edges carry the existing indirect-edge grade: ``INFERRED`` with a
``confidence_score`` below the implicit 1.0 of explicit EXTRACTED calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dummyindex.pipeline.enums import ConfidenceLevel

from ..io.cache import read_source_bytes
from .common import _make_id, _read_text
from .imports import _import_python

# Grade for edges inferred from indirect references — matches the raw-call
# resolution grade in `extract()` (INFERRED, score 0.8) and sits below the
# implicit 1.0 of explicit EXTRACTED call edges.
_INDIRECT_CONFIDENCE_SCORE = 0.8


@dataclass(frozen=True)
class _FileScan:
    """Per-file resolution state threaded through the AST walk.

    ``new_edges`` and ``seen`` are shared accumulators owned by the caller;
    they are appended to, never reassigned.
    """

    source: bytes
    str_path: str
    stem: str
    file_nid: str
    file_node_ids: frozenset[str]
    local_syms: dict[str, str]
    bound_names: frozenset[str]
    from_stems: dict[str, str]
    symbol_index: dict[tuple[str, str], str]
    ambiguous: frozenset[tuple[str, str]]
    new_edges: list[dict] = field(default_factory=list)
    seen: set[tuple[str, str, str]] = field(default_factory=set)


def _symbol_name_from_label(label: str) -> str | None:
    """Extract the addressable symbol name from a node label.

    Function labels are ``name()``, class labels are bare names. Method
    stubs (``.name()``) and file nodes (``*.py``) are not module attributes
    and return None.
    """
    if not label or label.startswith(".") or label.endswith(".py"):
        return None
    name = label[:-2] if label.endswith("()") else label
    return name or None


def _build_symbol_index(
    per_file: list[dict],
) -> tuple[dict[tuple[str, str], str], frozenset[tuple[str, str]]]:
    """Map ``(module stem, symbol name)`` → node id across all Python files.

    A key claimed by more than one source file (or more than one node id)
    is recorded as ambiguous so callers skip it — precision over recall.
    """
    index: dict[tuple[str, str], str] = {}
    owners: dict[tuple[str, str], str] = {}
    ambiguous: set[tuple[str, str]] = set()
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            src = node.get("source_file", "")
            nid = node.get("id", "")
            name = _symbol_name_from_label(node.get("label", ""))
            if not src or not nid or name is None:
                continue
            key = (Path(src).stem, name)
            if key in index and (index[key] != nid or owners[key] != src):
                ambiguous.add(key)
                continue
            index[key] = nid
            owners[key] = src
    return index, frozenset(ambiguous)


def _local_symbols(file_result: dict, str_path: str) -> dict[str, str]:
    """Map symbol name → node id for classes/functions defined in this file."""
    out: dict[str, str] = {}
    for node in file_result.get("nodes", []):
        if node.get("source_file") != str_path:
            continue
        nid = node.get("id", "")
        name = _symbol_name_from_label(node.get("label", ""))
        if nid and name is not None:
            out[name] = nid
    return out


def _collect_bindings(root, source: bytes) -> tuple[frozenset[str], dict[str, str]]:
    """Collect names bound by imports anywhere in the file.

    Returns ``(bound_names, from_import_stems)``: every import-bound name
    (module objects and from-imported symbols alike), plus name → source
    module stem for plain ``from X import name`` bindings. A name from-
    imported from two different modules is dropped as ambiguous. Aliased
    from-imports bind the alias but resolve no stem (the lookup name would
    differ from the extracted symbol's name).
    """
    bound: set[str] = set()
    from_stems: dict[str, str] = {}
    ambiguous_names: set[str] = set()

    def _record_from(name: str, module_stem: str) -> None:
        prev = from_stems.get(name)
        if prev is not None and prev != module_stem:
            ambiguous_names.add(name)
        else:
            from_stems[name] = module_stem

    def walk(node) -> None:
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    bound.add(_read_text(child, source).split(".")[0])
                elif child.type == "aliased_import":
                    alias = child.child_by_field_name("alias")
                    if alias is not None:
                        bound.add(_read_text(alias, source))
        elif node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module_stem: str | None = None
            if module_node is not None:
                raw = _read_text(module_node, source)
                module_stem = raw.split(".")[-1] or None
            past_import = False
            for child in node.children:
                if child.type == "import":
                    past_import = True
                    continue
                if not past_import:
                    continue
                if child.type == "dotted_name":
                    name = _read_text(child, source)
                    bound.add(name)
                    if module_stem:
                        _record_from(name, module_stem)
                elif child.type == "aliased_import":
                    alias = child.child_by_field_name("alias")
                    if alias is not None:
                        bound.add(_read_text(alias, source))
        for child in node.children:
            walk(child)

    walk(root)
    for name in ambiguous_names:
        from_stems.pop(name, None)
    return frozenset(bound), from_stems


def _resolve_dict_value(scan: _FileScan, value) -> str | None:
    """Node id for a dict value that references a known extracted symbol."""
    if value.type == "attribute":
        obj = value.child_by_field_name("object")
        attr = value.child_by_field_name("attribute")
        if obj is None or attr is None or obj.type != "identifier":
            return None  # nested a.b.c / call results: no guessing
        obj_name = _read_text(obj, scan.source)
        if obj_name not in scan.bound_names:
            return None
        key = (obj_name, _read_text(attr, scan.source))
        if key in scan.ambiguous:
            return None
        return scan.symbol_index.get(key)
    if value.type == "identifier":
        name = _read_text(value, scan.source)
        local = scan.local_syms.get(name)
        if local is not None:
            return local
        src_stem = scan.from_stems.get(name)
        if src_stem is None:
            return None
        key = (src_stem, name)
        if key in scan.ambiguous:
            return None
        return scan.symbol_index.get(key)
    return None


def _emit(
    scan: _FileScan, src_nid: str, tgt_nid: str, relation: str, line: int
) -> None:
    dedup_key = (src_nid, tgt_nid, relation)
    if dedup_key in scan.seen:
        return
    scan.seen.add(dedup_key)
    scan.new_edges.append(
        {
            "source": src_nid,
            "target": tgt_nid,
            "relation": relation,
            "confidence": ConfidenceLevel.INFERRED,
            "confidence_score": _INDIRECT_CONFIDENCE_SCORE,
            "source_file": scan.str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
    )


def _emit_function_body_import(scan: _FileScan, node) -> None:
    """Re-run the module-level import handler on an in-function ``from X
    import Y`` and re-grade its ``imports_from`` edges as INFERRED."""
    module_edges: list[dict] = []
    _import_python(
        node, scan.source, scan.file_nid, scan.stem, module_edges, scan.str_path
    )
    for edge in module_edges:
        if edge.get("relation") != "imports_from":
            continue
        dedup_key = (scan.file_nid, edge["target"], "imports_from")
        if dedup_key in scan.seen:
            continue
        scan.seen.add(dedup_key)
        scan.new_edges.append(
            {
                **edge,
                "confidence": ConfidenceLevel.INFERRED,
                "confidence_score": _INDIRECT_CONFIDENCE_SCORE,
            }
        )


def _walk_file(scan: _FileScan, node, scope_nid: str, fn_depth: int) -> None:
    """Recursive AST walk mirroring generic.py's node-id scheme.

    ``scope_nid`` is the nearest enclosing scope that has an extracted node;
    a def whose candidate id has no node (e.g. a nested function) keeps it.
    """
    t = node.type

    if t in ("class_definition", "function_definition"):
        name_node = node.child_by_field_name("name")
        name = _read_text(name_node, scan.source) if name_node is not None else ""
        if t == "class_definition":
            candidate = _make_id(scan.stem, name) if name else ""
        else:
            prefix = scan.stem if scope_nid == scan.file_nid else scope_nid
            candidate = _make_id(prefix, name) if name else ""
        effective = candidate if candidate in scan.file_node_ids else scope_nid
        next_depth = fn_depth + 1 if t == "function_definition" else fn_depth
        for child in node.children:
            _walk_file(scan, child, effective, next_depth)
        return

    if t == "import_from_statement":
        if fn_depth > 0:
            _emit_function_body_import(scan, node)
        return

    if t == "dictionary":
        for pair in node.children:
            if pair.type != "pair":
                continue
            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")
            if key_node is None or value_node is None or key_node.type != "attribute":
                continue  # enum-keyed mappings only — the narrow idiom
            tgt_nid = _resolve_dict_value(scan, value_node)
            if tgt_nid is None or tgt_nid == scope_nid:
                continue
            _emit(scan, scope_nid, tgt_nid, "calls", value_node.start_point[0] + 1)
        # keep walking: values may contain nested dictionaries
        for child in node.children:
            _walk_file(scan, child, scope_nid, fn_depth)
        return

    for child in node.children:
        _walk_file(scan, child, scope_nid, fn_depth)


def _resolve_python_dispatch(per_file: list[dict], paths: list[Path]) -> list[dict]:
    """Resolve dispatch-dict handler references and function-body imports.

    Returns new edges (``calls`` for enum-keyed dict values, ``imports_from``
    for in-function ``from X import Y``), all INFERRED. The caller is
    expected to dedup against already-extracted edges.
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    parser = Parser(Language(tspython.language()))
    symbol_index, ambiguous = _build_symbol_index(per_file)

    new_edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for file_result, path in zip(per_file, paths, strict=True):
        str_path = str(path)
        file_nid = _make_id(str_path)
        file_node_ids = frozenset(n.get("id", "") for n in file_result.get("nodes", []))
        if file_nid not in file_node_ids:
            continue  # cached result keyed to another path shape: no guessing

        try:
            source = read_source_bytes(path)
            tree = parser.parse(source)
        except Exception:
            continue

        bound_names, from_stems = _collect_bindings(tree.root_node, source)
        scan = _FileScan(
            source=source,
            str_path=str_path,
            stem=path.stem,
            file_nid=file_nid,
            file_node_ids=file_node_ids,
            local_syms=_local_symbols(file_result, str_path),
            bound_names=bound_names,
            from_stems=from_stems,
            symbol_index=symbol_index,
            ambiguous=ambiguous,
            new_edges=new_edges,
            seen=seen,
        )
        _walk_file(scan, tree.root_node, scope_nid=file_nid, fn_depth=0)

    return new_edges
