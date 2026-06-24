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

    # Render as the value ("low"), never the enum repr ("DocConfidence.LOW").
    # Python 3.11 changed Enum.__format__ to follow __str__, so a bare
    # `class X(str, Enum)` stringifies to the repr under f-strings on 3.11+
    # (it gave the value on <=3.10). The catalog stores these members directly
    # in DocEntry.confidence and renders them into source-docs/INDEX.md, so we
    # pin str/format to the str value on every interpreter.
    __str__ = str.__str__


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
    SCAFFOLD_FEATURE = "scaffold-feature"
    ASSIGN_FILES = "assign-files"
    UNASSIGN_FILES = "unassign-files"
    FEATURES_REMOVE = "features-remove"
    MARK_ENRICHED = "mark-enriched"
    RECONCILE = "reconcile"
    RECONCILE_STAMP = "reconcile-stamp"
    COUNCIL_LOG = "council-log"
    COUNCIL_BATCH = "council-batch"
    CONVENTIONS_WRITE = "conventions-write"
    REFRESH_INDEXES = "refresh-indexes"
    QUERY = "query"
    REALITY_CHECK = "reality-check"
    PLAN_UPDATE = "plan-update"
    RECONCILE_GATE = "reconcile-gate"
    DEV_PICK = "dev-pick"
    ONBOARD = "onboard"
    CONFIG = "config"
    PREFLIGHT = "preflight"
    DOC_REORG = "doc-reorg"
    MEMORY = "memory"
    PROPOSE = "propose"
    EQUIP = "equip"
    BUILD = "build"
    AUDIT = "audit"
    AUDIT_LOG = "audit-log"
    GC = "gc"
    STATUS = "status"
    WIRE = "wire"
    DEBT = "debt"
    STATUSLINE = "statusline"
