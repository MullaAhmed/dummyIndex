"""graphify - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so `graphify install` works before heavy deps are in place.
    _map = {
        "extract": ("graphify.pipeline.extract", "extract"),
        "collect_files": ("graphify.pipeline.extract", "collect_files"),
        "build_from_json": ("graphify.pipeline.build", "build_from_json"),
        "cluster": ("graphify.analysis.cluster", "cluster"),
        "score_all": ("graphify.analysis.cluster", "score_all"),
        "cohesion_score": ("graphify.analysis.cluster", "cohesion_score"),
        "god_nodes": ("graphify.analysis.analyze", "god_nodes"),
        "surprising_connections": ("graphify.analysis.analyze", "surprising_connections"),
        "suggest_questions": ("graphify.analysis.analyze", "suggest_questions"),
        "generate": ("graphify.analysis.report", "generate"),
        "to_json": ("graphify.pipeline.export", "to_json"),
        "to_html": ("graphify.pipeline.export", "to_html"),
        "to_svg": ("graphify.pipeline.export", "to_svg"),
        "to_canvas": ("graphify.pipeline.export", "to_canvas"),
        "to_wiki": ("graphify.analysis.wiki", "to_wiki"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'graphify' has no attribute {name!r}")
