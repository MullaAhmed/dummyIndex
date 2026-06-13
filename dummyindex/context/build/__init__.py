"""Build lifecycle: source → on-disk ``.context/`` index.

Public surface (the test + caller boundary). Submodules import each other
via full paths; these re-exports are the stable names the rest of the
package and the test-suite depend on.
"""
from dummyindex.context.build.git_delta import (
    ChangedPaths,
    changed_paths,
    head_commit,
)
from dummyindex.context.build.incremental import (
    ChangeSet,
    EnrichedIndexStatus,
    IncrementalResult,
    enriched_index_status,
    is_enriched_index,
    rebuild_changed,
)
from dummyindex.context.build.enriched_refresh import (
    RefreshResult,
    refresh_deterministic_artifacts,
)
from dummyindex.context.build.reconcile import (
    ReconcileReport,
    compute_reconcile_report,
)
from dummyindex.context.build.runner import BuildResult, build_all

__all__ = [
    "BuildResult",
    "build_all",
    "ChangeSet",
    "EnrichedIndexStatus",
    "IncrementalResult",
    "enriched_index_status",
    "is_enriched_index",
    "rebuild_changed",
    "ChangedPaths",
    "changed_paths",
    "head_commit",
    "RefreshResult",
    "refresh_deterministic_artifacts",
    "ReconcileReport",
    "compute_reconcile_report",
]
