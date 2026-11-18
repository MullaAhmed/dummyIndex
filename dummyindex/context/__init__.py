"""dummyIndex v2 .context/ context engine package.

See docs/guide/ (01-purpose … 12-retrieval) for design intent.

Public names load lazily (PEP 562). Importing a sibling such as
``dummyindex.context.usage`` or ``dummyindex.context.shared`` must not pull in
the whole engine (networkx, tree-sitter, the build runner).
"""

from __future__ import annotations

# module -> public names it provides
_EXPORTS: dict[str, tuple[str, ...]] = {
    "dummyindex.context.build.conventions": (
        "NamingRule",
        "NamingRules",
        "analyze_naming",
        "classify_casing",
        "write_naming_json",
        "write_naming_md",
    ),
    "dummyindex.context.build.incremental": (
        "ChangeSet",
        "IncrementalResult",
        "rebuild_changed",
    ),
    "dummyindex.context.build.maps": (
        "FileEntry",
        "FilesMap",
        "SymbolEntry",
        "SymbolsMap",
        "build_maps",
        "files_map_from_paths",
        "symbols_map_from_structure",
        "write_files_map",
        "write_symbols_map",
    ),
    "dummyindex.context.build.meta": (
        "SCHEMA_VERSION",
        "Meta",
        "new_meta",
        "read_meta",
        "write_meta",
    ),
    "dummyindex.context.build.runner": ("BuildResult", "build_all"),
    "dummyindex.context.build.tree": (
        "Tree",
        "TreeNode",
        "build_tree",
        "iter_nodes",
        "tree_from_structure",
        "write_tree",
    ),
    "dummyindex.context.output.bootstrap": (
        "BEGIN_MARKER",
        "END_MARKER",
        "UnbalancedMarkersError",
        "bootstrap_claude_md",
        "generate_managed_block",
    ),
    "dummyindex.context.output.docs": (
        "generate_index_md",
        "generate_project_md",
        "write_index_md",
        "write_project_md",
    ),
    "dummyindex.context.output.instructions": (
        "PLAYBOOK_IDS",
        "generate_architecture_overview_md",
        "generate_how_to_use_md",
        "generate_playbook_md",
        "write_architecture_overview_md",
        "write_how_to_use_md",
        "write_playbook_md",
    ),
    # Re-exported from the pipeline so the CLI boundary (__main__) can detect
    # git repos without importing `pipeline` directly — the layering table
    # grants __main__ the `context` public surface, not `pipeline`.
    "dummyindex.context.pipeline.io": ("is_git_repo",),
}

_LAZY = {name: mod for mod, names in _EXPORTS.items() for name in names}


def __getattr__(name: str):
    mod_name = _LAZY.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(mod_name), name)
    globals()[name] = value  # cache: later lookups skip __getattr__
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


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
