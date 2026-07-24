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


class ScanNodeKind(str, Enum):
    """What a node in `features/graph.json` *is*.

    The scan is one map holding both halves of a codebase: the AI surface
    (`AGENT` / `MODEL` / `TOOL`) and the business logic the product is
    actually built from (`ENTRY` / `CRON` / `SERVICE` / `STORE` /
    `EXTERNAL`). A closed alphabet is what lets the viewer assign a shape,
    a colour, and a layout column per kind without special-casing.
    """

    ENTRY = "entry"  # route / page / CLI / webhook — something triggers it
    CRON = "cron"  # scheduled job, queue worker
    AGENT = "agent"  # an LLM loop the project owns
    MODEL = "model"  # a specific model an agent calls
    TOOL = "tool"  # something a model can call
    SERVICE = "service"  # internal business-logic module the project owns
    STORE = "store"  # DB / cache / index
    EXTERNAL = "external"  # 3rd-party API

    __str__ = str.__str__


class ScanEdgeKind(str, Enum):
    """What a scan edge *does*. Rendered quietly until a flow is traced."""

    CALLS = "calls"
    READS = "reads"
    WRITES = "writes"
    TRIGGERS = "triggers"

    __str__ = str.__str__


class ScanEvidence(str, Enum):
    """Where a scan node's claim comes from.

    ``EXTRACTED`` — kept verbatim from the deterministic seed; a rebuild
    could reproduce it. ``INFERRED`` — added or reshaped by the authoring
    council stage; judgment no re-extraction can recover.

    Deliberately not `pipeline.enums.ConfidenceLevel`: that enum grades
    whole artifacts, carries a third member (``AMBIGUOUS``) the scan wire
    format forbids, and does not pin ``__str__`` — the per-node field is a
    closed two-value alphabet.
    """

    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"

    __str__ = str.__str__


class ScanViolationSeverity(str, Enum):
    """How hard `scan-check` fails on a violation.

    ``ERROR`` breaks the contract and flips the exit code. ``WARNING``
    means the scan could not be fully checked (e.g. a `symbolRef` with no
    extraction artifact on disk to resolve it against) — reported, never
    fatal, because the scan itself is not wrong.
    """

    ERROR = "error"
    WARNING = "warning"

    __str__ = str.__str__


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
    SCAN_CHECK = "scan-check"
    QUERY = "query"
    GRAPH = "graph"
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
    MIGRATE_DOCS = "migrate-docs"
    GUARD_DOC_WRITE = "guard-doc-write"
