"""dummyindex - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so `dummyindex install` works before heavy deps are in place.
    _map = {
        "extract": ("dummyindex.pipeline.extract", "extract"),
        "collect_files": ("dummyindex.pipeline.extract", "collect_files"),
        "build_from_json": ("dummyindex.pipeline.build", "build_from_json"),
        "build_structure": ("dummyindex.pipeline.structure", "build_structure"),
        "cluster": ("dummyindex.analysis.cluster", "cluster"),
        "score_all": ("dummyindex.analysis.cluster", "score_all"),
        "cohesion_score": ("dummyindex.analysis.cluster", "cohesion_score"),
        "god_nodes": ("dummyindex.analysis.analyze", "god_nodes"),
        "surprising_connections": ("dummyindex.analysis.analyze", "surprising_connections"),
        "suggest_questions": ("dummyindex.analysis.analyze", "suggest_questions"),
        "generate": ("dummyindex.analysis.report", "generate"),
        "to_json": ("dummyindex.pipeline.export", "to_json"),
        "to_structure_json": ("dummyindex.pipeline.export", "to_structure_json"),
        "to_html": ("dummyindex.pipeline.export", "to_html"),
        "to_structure_html": ("dummyindex.pipeline.export", "to_structure_html"),
        "to_svg": ("dummyindex.pipeline.export", "to_svg"),
        "to_canvas": ("dummyindex.pipeline.export", "to_canvas"),
        "to_wiki": ("dummyindex.analysis.wiki", "to_wiki"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'dummyindex' has no attribute {name!r}")
