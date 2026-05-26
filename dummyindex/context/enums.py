"""Cross-area enums for the `.context/` engine.

Closed-alphabet string constants used by multiple modules under
`dummyindex/context/`. Per-area enums (one feature/doc/cli concern) live
in `<area>/enums.py` inside that area's package.
"""
from __future__ import annotations

from enum import Enum


class DocConfidence(str, Enum):
    """Per-doc grading in the source-docs catalog.

    A doc's confidence is the model's view of how trustworthy the doc is
    as a source of truth for the current code. Drift detection (broken
    references to vanished symbols, etc.) can demote a doc to ``LOW``.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


DOC_CONFIDENCE_ORDER: dict[DocConfidence, int] = {
    DocConfidence.HIGH: 0,
    DocConfidence.MEDIUM: 1,
    DocConfidence.LOW: 2,
}


class ContextSubcommand(str, Enum):
    """`dummyindex context <subcommand>` — the closed dispatch alphabet.

    `ingest` is an alias for `init` handled at the top-level CLI, not in
    the context dispatcher; it does not appear here.
    """

    INIT = "init"
    REBUILD = "rebuild"
    BOOTSTRAP = "bootstrap"
    CHECK = "check"
    HOOKS = "hooks"
    ENRICH_PLAN = "enrich-plan"
    ENRICH_APPLY = "enrich-apply"
    FEATURES_RENAME = "features-rename"
    FEATURES_MERGE = "features-merge"
    FLOW_REMOVE = "flow-remove"
    SECTION_WRITE = "section-write"
    COUNCIL_LOG = "council-log"
    CONVENTIONS_WRITE = "conventions-write"
    REFRESH_INDEXES = "refresh-indexes"
    QUERY = "query"
    REALITY_CHECK = "reality-check"
    PLAN_UPDATE = "plan-update"
