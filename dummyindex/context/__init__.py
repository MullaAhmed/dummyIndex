"""dummyIndex v2 .context/ context engine package.

See BRIEF.md and V0_SCOPE.md at the repo root for design intent.
"""
from __future__ import annotations

from dummyindex.context.bootstrap import (
    BEGIN_MARKER,
    END_MARKER,
    UnbalancedMarkersError,
    bootstrap_claude_md,
    generate_managed_block,
)
from dummyindex.context.conventions import (
    NamingRule,
    NamingRules,
    analyze_naming,
    classify_casing,
    write_naming_json,
    write_naming_md,
)
from dummyindex.context.docs import (
    generate_index_md,
    generate_project_md,
    write_index_md,
    write_project_md,
)
from dummyindex.context.maps import (
    FileEntry,
    FilesMap,
    SymbolEntry,
    SymbolsMap,
    build_maps,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.meta import (
    SCHEMA_VERSION,
    Meta,
    new_meta,
    read_meta,
    write_meta,
)
from dummyindex.context.tree import (
    Tree,
    TreeNode,
    build_tree,
    iter_nodes,
    write_tree,
)

__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "FileEntry",
    "FilesMap",
    "Meta",
    "NamingRule",
    "NamingRules",
    "SCHEMA_VERSION",
    "SymbolEntry",
    "SymbolsMap",
    "Tree",
    "TreeNode",
    "UnbalancedMarkersError",
    "analyze_naming",
    "bootstrap_claude_md",
    "build_maps",
    "build_tree",
    "classify_casing",
    "generate_index_md",
    "generate_managed_block",
    "generate_project_md",
    "iter_nodes",
    "new_meta",
    "read_meta",
    "write_files_map",
    "write_index_md",
    "write_meta",
    "write_naming_json",
    "write_naming_md",
    "write_project_md",
    "write_symbols_map",
    "write_tree",
]
