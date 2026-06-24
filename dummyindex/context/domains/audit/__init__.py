"""On-demand argue-and-audit panel: scaffold + log surface.

``dummyindex context audit start --describe "..."`` turns a free-text request
into a ``.context/audits/<slug>/`` workspace (``audit.json`` + ``description.md``
+ ``catalog.json`` + ``findings/``). The ``/dummyindex-audit`` skill then picks a
task-relevant panel from the catalog, runs a rebuttal loop (capped at
``MAX_REBUTTAL_ROUNDS``, stopping early on agreement), and writes ``report.md``.

This package is deterministic plumbing only — the auditing itself is the agents,
orchestrated by the skill markdown. There is no audit "computation" here.

Public surface (the CLI + test import target):

- ``AuditConfig``, ``PersonaCard``, ``AuditStart``, ``RosterAgent`` — frozen
  dataclasses
- ``LogEntry`` — one debate-log row
- ``LogStatus``, ``MAX_REBUTTAL_ROUNDS``, ``SCHEMA_VERSION``
- ``AUDITS_REL``, ``audit_dir``, ``audits_root``, ``ensure_audit``, ``read_audit``,
  ``report_written``, ``resolve_model``, ``resolve_mode``, ``slugify``,
  ``validate_slug``
- ``default_personas_dir``, ``load_catalog``, ``parse_persona``,
  ``collect_roster``, ``resolve_catalog`` (persona → installed-roster resolution)
- ``append_log``, ``read_log``, ``is_round_complete``, ``completed_rounds``,
  ``latest_status``
- ``AuditError``, ``AuditSlugError``, ``AuditExistsError``, ``AuditNotFoundError``,
  ``ModelRequiredError``, ``AuditLogError``
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
