"""On-demand argue-and-audit panel: scaffold + log surface (deterministic plumbing).

``context audit start --describe "..."`` turns a request into a
``.context/audits/<slug>/`` workspace (``audit.json``, ``description.md``,
``catalog.json``, ``findings/``). The ``/dummyindex-audit`` skill's agents then pick
a panel, run a rebuttal loop (capped at ``MAX_REBUTTAL_ROUNDS``, stopping early on
agreement) and write ``report.md``. ``__all__`` is the CLI + test import surface.
"""

from __future__ import annotations

from .catalog import (
    RosterAgent,
    collect_roster,
    default_personas_dir,
    load_catalog,
    parse_persona,
    resolve_catalog,
)
from .enums import MAX_REBUTTAL_ROUNDS, LogStatus
from .errors import (
    AuditError,
    AuditExistsError,
    AuditLogError,
    AuditNotFoundError,
    AuditSlugError,
    ModelRequiredError,
)
from .log import (
    LogEntry,
    append_log,
    completed_rounds,
    is_round_complete,
    latest_status,
    read_log,
)
from .models import SCHEMA_VERSION, AuditConfig, AuditStart, PersonaCard
from .workspace import (
    AUDITS_REL,
    audit_dir,
    audits_root,
    ensure_audit,
    read_audit,
    report_written,
    resolve_mode,
    resolve_model,
    slugify,
    validate_slug,
)

__all__ = [
    "AUDITS_REL",
    "MAX_REBUTTAL_ROUNDS",
    "SCHEMA_VERSION",
    "AuditConfig",
    "AuditError",
    "AuditExistsError",
    "AuditLogError",
    "AuditNotFoundError",
    "AuditSlugError",
    "AuditStart",
    "LogEntry",
    "LogStatus",
    "ModelRequiredError",
    "PersonaCard",
    "RosterAgent",
    "append_log",
    "audit_dir",
    "audits_root",
    "collect_roster",
    "completed_rounds",
    "default_personas_dir",
    "ensure_audit",
    "is_round_complete",
    "latest_status",
    "load_catalog",
    "parse_persona",
    "read_audit",
    "read_log",
    "report_written",
    "resolve_catalog",
    "resolve_mode",
    "resolve_model",
    "slugify",
    "validate_slug",
]
