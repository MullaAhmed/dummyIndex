"""dummyIndex v2 .context/ context engine package.

See docs/guide/ (01-purpose … 12-retrieval) for design intent.
"""

from __future__ import annotations

from dummyindex.context.build.conventions import (
    NamingRule,
    NamingRules,
    analyze_naming,
    classify_casing,
    write_naming_json,
    write_naming_md,
)
from dummyindex.context.build.incremental import (
    ChangeSet,
    IncrementalResult,
    rebuild_changed,
)
from dummyindex.context.build.maps import (
    FileEntry,
    FilesMap,
    SymbolEntry,
    SymbolsMap,
    build_maps,
    files_map_from_paths,
    symbols_map_from_structure,
    write_files_map,
    write_symbols_map,
)
from dummyindex.context.build.meta import (
    SCHEMA_VERSION,
    Meta,
    new_meta,
    read_meta,
    write_meta,
)
from dummyindex.context.build.runner import BuildResult, build_all
from dummyindex.context.build.tree import (
    Tree,
    TreeNode,
    build_tree,
    iter_nodes,
    tree_from_structure,
    write_tree,
)
from dummyindex.context.output.bootstrap import (
    BEGIN_MARKER,
    END_MARKER,
    UnbalancedMarkersError,
    bootstrap_claude_md,
    generate_managed_block,
)
from dummyindex.context.output.docs import (
    generate_index_md,
    generate_project_md,
    write_index_md,
    write_project_md,
)
from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    generate_architecture_overview_md,
    generate_how_to_use_md,
    generate_playbook_md,
    write_architecture_overview_md,
    write_how_to_use_md,
    write_playbook_md,
)

# Re-exported from the pipeline so the CLI boundary (__main__) can detect
# git repos without importing `pipeline` directly — the layering table
# grants __main__ the `context` public surface, not `pipeline`.
from dummyindex.pipeline.io import is_git_repo

__all__ = [
    "BEGIN_MARKER",
    "BuildResult",
    "ChangeSet",
    "END_MARKER",
    "FileEntry",
    "FilesMap",
    "IncrementalResult",
    "Meta",
    "NamingRule",
    "NamingRules",
    "PLAYBOOK_IDS",
    "SCHEMA_VERSION",
    "SymbolEntry",
    "SymbolsMap",
    "Tree",
    "TreeNode",
    "UnbalancedMarkersError",
    "analyze_naming",
    "bootstrap_claude_md",
    "build_all",
    "build_maps",
    "build_tree",
    "classify_casing",
    "files_map_from_paths",
    "generate_architecture_overview_md",
    "generate_how_to_use_md",
    "generate_index_md",
    "generate_managed_block",
    "generate_playbook_md",
    "generate_project_md",
    "is_git_repo",
    "iter_nodes",
    "new_meta",
    "read_meta",
    "rebuild_changed",
    "symbols_map_from_structure",
    "tree_from_structure",
    "write_architecture_overview_md",
    "write_files_map",
    "write_how_to_use_md",
    "write_index_md",
    "write_meta",
    "write_naming_json",
    "write_naming_md",
    "write_playbook_md",
    "write_project_md",
    "write_symbols_map",
    "write_tree",
]
