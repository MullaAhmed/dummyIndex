"""dummyindex — Claude Code skill + `.context/` context engine.

Public API is intentionally narrow. Most callers will use the CLI
(`dummyindex install`, `dummyindex ingest`, `dummyindex context …`). The
exported symbols below are the ones the `/dummyindex` skill and the
context-engine internals load lazily.
"""

from __future__ import annotations


def __getattr__(name: str):
    # Lazy imports so `dummyindex install` doesn't trigger heavy
    # tree-sitter / networkx loading.
    _map = {
        # Core deterministic pipeline (powers `dummyindex ingest`).
        "detect": ("dummyindex.pipeline.io", "detect"),
        "extract": ("dummyindex.pipeline.extract", "extract"),
        "collect_files": ("dummyindex.pipeline.extract", "collect_files"),
        "build_from_json": ("dummyindex.pipeline.build", "build_from_json"),
        "build_structure": ("dummyindex.pipeline.build", "build_structure"),
        # Clustering + export reused by `dummyindex.context.build.graph`.
        "cluster": ("dummyindex.analysis.cluster", "cluster"),
        "to_json": ("dummyindex.export", "to_json"),
    }
    if name in _map:
        import importlib

        mod_name, attr = _map[name]
        return getattr(importlib.import_module(mod_name), attr)
    raise AttributeError(f"module 'dummyindex' has no attribute {name!r}")
