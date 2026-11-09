"""Package-private constants for `context/equip/`.

Kept out of `enums.py` because schema version is a tunable,
not a closed-alphabet enum.
"""

from __future__ import annotations

from .enums import Capability

# v4 added EquipmentKind.PLUGIN. Older manifests still load; an older CLI reading
# a v4 manifest with a "plugin" item raises, which the bump documents.
SCHEMA_VERSION = 4

# Sentinel in equip's PostToolUse format-hook command, so install/refresh/uninstall
# can find our settings.json entry among the user's hooks. Distinct from the session
# hooks' ``DUMMYINDEX_AUTO_REFRESH`` so the two coexist and uninstall independently.
EQUIP_SENTINEL = "DUMMYINDEX_EQUIP"

# Adoption's keyword table: capability -> lowercase substrings of a project agent's
# file stem that imply it (generate/adopt.py). A stem can yield several.
_CAPABILITY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (Capability.DATABASE, ("database", "db", "data", "migration", "sql")),
    (Capability.SECURITY, ("security", "auth", "secret")),
    (Capability.FRONTEND, ("frontend", "ui", "css", "react", "vue", "svelte")),
    (Capability.PERFORMANCE, ("performance", "perf", "optimi")),
    (Capability.DOCS, ("docs", "documentation", "doc")),
    (Capability.TEST, ("test", "qa")),
    (Capability.REVIEW, ("review", "audit")),
    (Capability.IMPLEMENT, ("implement", "build", "feature")),
)

# Per-proposal scoping (spec §6): specialist capabilities only. test/review/implement
# are left out on purpose: nearly every plan.md uses those words. Security carries the
# tenant-isolation words so "enforce RLS" without "security" still finds the specialist.
# Matched as a whole word or word prefix (generate/proposal.py).
_PROPOSAL_CAPABILITY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (Capability.DATABASE, ("database", "migration", "sql")),
    (
        Capability.SECURITY,
        ("security", "auth", "secret", "rls", "tenant", "tenancy", "isolation", "rbac"),
    ),
    (Capability.FRONTEND, ("frontend", "ui", "css", "react")),
    (Capability.PERFORMANCE, ("performance", "optimi")),
    (Capability.DOCS, ("docs", "documentation")),
    (Capability.SEARCH, ("search", "embedding", "vector", "rag", "semantic")),
    (Capability.API, ("api", "endpoint", "openapi", "graphql", "restful")),
    (Capability.MIGRATION, ("migrate", "backfill", "alembic", "rollback")),
    (Capability.CI, ("cicd", "workflow", "github", "gitlab", "jenkins")),
)

# Marker embedded in every vendored `.claude/**.md`, distinct from
# GENERATED_SENTINEL: a vendored file is a verbatim upstream copy, not our
# render. Greppable so refresh/uninstall recognise (and never clobber) it.
VENDORED_SENTINEL = "<!-- dummyindex:installed -->"

# Discovered-plugin inference (name/description/keywords/category). Broader than the
# proposal table: the user asked to find tools, so implement/test/review hits count.
# Whole word or plural only, bar the optimi/profil stems (plugins/discover.py), so
# 'auth' spells out its long forms; 'audit' is REVIEW (a design audit is not security).
_PLUGIN_CAPABILITY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (Capability.DATABASE, ("database", "db", "sql", "postgres", "migration", "orm")),
    (
        Capability.SECURITY,
        ("security", "auth", "authentication", "authorization", "secret", "vuln"),
    ),
    (Capability.FRONTEND, ("frontend", "ui", "css", "react", "vue", "svelte")),
    (Capability.PERFORMANCE, ("performance", "perf", "optimi", "profil", "benchmark")),
    (Capability.DOCS, ("docs", "documentation", "readme")),
    (Capability.SEARCH, ("search", "embedding", "vector", "rag", "semantic")),
    (Capability.DATA, ("data", "etl", "pipeline", "analytics")),
    (Capability.TEST, ("test", "qa", "coverage")),
    (Capability.REVIEW, ("review", "lint", "audit")),
    (Capability.IMPLEMENT, ("implement", "scaffold", "generator")),
)
