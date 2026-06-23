"""Python-specific post-pass: extract docstrings + rationale comments.

Called by `extract_python` after the generic pass. Augments the result
in-place with `rationale` nodes (one per docstring + one per
`# NOTE:` / `# IMPORTANT:` / etc.) and `rationale_for` edges.
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.pipeline.enums import ConfidenceLevel

from ..io.cache import read_source_bytes
from .common import _make_id

# Debt markers shared with the debt harvester (importable). Every entry is also
# a rationale prefix below, so a debt comment is extracted as rationale too.
DEBT_PREFIXES = ("# TODO:", "# FIXME:", "# HACK:", "# DEBT:")

# Non-debt rationale prefixes, then the debt subset spread in — no duplicates.
_NON_DEBT_RATIONALE_PREFIXES = ("# NOTE:", "# IMPORTANT:", "# WHY:", "# RATIONALE:")
_RATIONALE_PREFIXES = (*_NON_DEBT_RATIONALE_PREFIXES, *DEBT_PREFIXES)


def _extract_python_rationale(path: Path, result: dict) -> None:
    """Post-pass: extract docstrings and rationale comments from Python source.
    Mutates result in-place by appending to result['nodes'] and result['edges'].
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser

        language = Language(tspython.language())
        parser = Parser(language)
        source = read_source_bytes(path)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception:
        return

    stem = path.stem
    str_path = str(path)
    nodes = result["nodes"]
    edges = result["edges"]
    seen_ids = {n["id"] for n in nodes}
    file_nid = _make_id(str(path))

    def _get_docstring(body_node) -> tuple[str, int] | None:
        if not body_node:
            return None
        for child in body_node.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type in ("string", "concatenated_string"):
                        text = source[sub.start_byte : sub.end_byte].decode(
                            "utf-8", errors="replace"
                        )
                        text = text.strip()
                        for delimiter in ('"""', "'''", '"', "'"):
                            if (
                                len(text) >= 2 * len(delimiter)
                                and text.startswith(delimiter)
                                and text.endswith(delimiter)
                            ):
                                text = text[len(delimiter) : -len(delimiter)].strip()
                                break
                        if len(text) > 20:
                            return text, child.start_point[0] + 1
            break
        return None

    def _add_rationale(text: str, line: int, parent_nid: str) -> None:
        label = (
            text[:80].replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
        )
        rid = _make_id(stem, "rationale", str(line))
        if rid not in seen_ids:
            seen_ids.add(rid)
            nodes.append(
                {
                    "id": rid,
                    "label": label,
                    "file_type": "rationale",
                    "source_file": str_path,
                    "source_location": f"L{line}",
                }
            )
        edges.append(
            {
                "source": rid,
                "target": parent_nid,
                "relation": "rationale_for",
                "confidence": ConfidenceLevel.EXTRACTED,
                "source_file": str_path,
                "source_location": f"L{line}",
                "weight": 1.0,
            }
        )

    # Module-level docstring
    ds = _get_docstring(root)
    if ds:
        _add_rationale(ds[0], ds[1], file_nid)

    # Class and function docstrings
    def walk_docstrings(node, parent_nid: str) -> None:
        t = node.type
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node and body:
                class_name = source[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                nid = _make_id(stem, class_name)
                ds = _get_docstring(body)
                if ds:
                    _add_rationale(ds[0], ds[1], nid)
                for child in body.children:
                    walk_docstrings(child, nid)
            return
        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            if name_node and body:
                func_name = source[name_node.start_byte : name_node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                nid = (
                    _make_id(parent_nid, func_name)
                    if parent_nid != file_nid
                    else _make_id(stem, func_name)
                )
                ds = _get_docstring(body)
                if ds:
                    _add_rationale(ds[0], ds[1], nid)
            return
        for child in node.children:
            walk_docstrings(child, parent_nid)

    walk_docstrings(root, file_nid)

    # Rationale comments (# NOTE:, # IMPORTANT:, etc.)
    source_text = source.decode("utf-8", errors="replace")
    for lineno, line_text in enumerate(source_text.splitlines(), start=1):
        stripped = line_text.strip()
        if any(stripped.startswith(p) for p in _RATIONALE_PREFIXES):
            _add_rationale(stripped, lineno, file_nid)
