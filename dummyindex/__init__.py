"""dummyindex - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so `dummyindex install` works before heavy deps are in place.
    _map = {
        "extract": ("dummyindex.pipeline.extract", "extract"),
        "collect_files": ("dummyindex.pipeline.extract", "collect_files"),
        "build_from_json": ("dummyindex.pipeline.build", "build_from_json"),
        "build_structure": ("dummyindex.pipeline.structure", "build_structure"),
        "synthesize_flows": ("dummyindex.analysis.flows", "synthesize_flows"),
        "detect_entry_points": ("dummyindex.analysis.flows", "detect_entry_points"),
        "derive_flow": ("dummyindex.analysis.flows", "derive_flow"),
        "merge_flows": ("dummyindex.analysis.flows", "merge_flows"),
        "overlap_index": ("dummyindex.analysis.flows", "overlap_index"),
        "FlowConfig": ("dummyindex.analysis.flows", "FlowConfig"),
        "prepare_naming_todo": ("dummyindex.analysis.flow_naming", "prepare_naming_todo"),
        "apply_named_results": ("dummyindex.analysis.flow_naming", "apply_named_results"),
        "load_cached_names": ("dummyindex.analysis.flow_naming", "load_cached_names"),
        "load_overrides": ("dummyindex.analysis.flow_naming", "load_overrides"),
        "synthesize_features": ("dummyindex.analysis.features", "synthesize_features"),
        "derive_feature_dependencies": ("dummyindex.analysis.features", "derive_feature_dependencies"),
        "feature_overlap_matrix": ("dummyindex.analysis.features", "overlap_matrix"),
        "detect_orphans": ("dummyindex.analysis.features", "detect_orphans"),
        "FeatureConfig": ("dummyindex.analysis.features", "FeatureConfig"),
        "prepare_feature_naming_todo": ("dummyindex.analysis.feature_naming", "prepare_feature_naming_todo"),
        "apply_feature_named_results": ("dummyindex.analysis.feature_naming", "apply_feature_named_results"),
        "apply_feature_overrides": ("dummyindex.analysis.feature_naming", "apply_feature_overrides"),
        "load_features_yaml": ("dummyindex.analysis.feature_naming", "load_features_yaml"),
        "write_features_yaml_starter": ("dummyindex.analysis.feature_naming", "write_features_yaml_starter"),
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
        "to_flow_json": ("dummyindex.pipeline.export", "to_flow_json"),
        "to_flow_html": ("dummyindex.pipeline.export", "to_flow_html"),
        "to_feature_json": ("dummyindex.pipeline.export", "to_feature_json"),
        "to_feature_html": ("dummyindex.pipeline.export", "to_feature_html"),
        "attach_hyperedges": ("dummyindex.pipeline.export", "attach_hyperedges"),
        "restore_hyperedges_from_disk": ("dummyindex.pipeline.export", "restore_hyperedges_from_disk"),
        "append_run": ("dummyindex.runtime.run_log", "append_run"),
        "aggregate_run_stats": ("dummyindex.runtime.run_log", "aggregate_run_stats"),
        "format_run_summary": ("dummyindex.runtime.run_log", "format_run_summary"),
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
