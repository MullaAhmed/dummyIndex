"""dummyIndex v2 .context/ context engine package.

See BRIEF.md and V0_SCOPE.md at the repo root for design intent.
"""
from __future__ import annotations

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
    "FileEntry",
    "FilesMap",
    "Meta",
    "SCHEMA_VERSION",
    "SymbolEntry",
    "SymbolsMap",
    "Tree",
    "TreeNode",
    "build_maps",
    "build_tree",
    "iter_nodes",
    "new_meta",
    "read_meta",
    "write_files_map",
    "write_meta",
    "write_symbols_map",
    "write_tree",
]
