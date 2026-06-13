"""Package-private constants for `context/equip/`.

Kept out of `enums.py` because schema version is a tunable,
not a closed-alphabet enum.
"""
from __future__ import annotations

from .enums import Capability

# v4: EquipmentKind gained PLUGIN (native marketplace installs were recorded as
# kind "agent" before). Older manifests still load tolerantly; older CLIs
# reading a v4 manifest with a "plugin" item raise — the bump documents that.
SCHEMA_VERSION = 4

# Sentinel embedded in equip's PostToolUse format-hook command string, so
# install/refresh/uninstall can recognise our settings.json entry among the
# user's other hooks. Distinct from the managed session hooks'
# ``DUMMYINDEX_AUTO_REFRESH`` sentinel so the two coexist and uninstall
# independently.
EQUIP_SENTINEL = "DUMMYINDEX_EQUIP"

# Shared capability vocabulary. One keyword table maps free-text tokens (found
# in an agent file stem, or harvested from a proposal's plan/checklist) to a
# canonical capability. Used by adoption (infer a project agent's coverage from
# its stem) and proposal scoping (extract needed capabilities). First match in
# iteration order wins per capability; a stem/text can yield several.
#
# capability -> the substring tokens that imply it.
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

# Per-proposal capability scoping (spec §6). A DELIBERATELY NARROWER table than
# ``_CAPABILITY_TOKENS``: only the *specialist* capabilities a proposal can ask
# equip to cover (by generating a template-backed specialist, or — when no
# template exists — adopting one). The broad test/review/implement tokens are
# excluded on purpose — those words appear in essentially every plan.md, and
# including them would pull in a specialist on every proposal.
#
# The security row carries the tenant-isolation vocabulary (``rls`` / ``tenant``
# / ``isolation`` / ``rbac``) so a migration plan whose criticals say "enforce
# RLS" or "tenant isolation" — without the literal word "security" — still
# surfaces the security specialist. (Whole-word "security" already catches
# "row-level security" / "get_advisors security", and the "auth" prefix catches
# authorization/authentication.) capability -> the tokens that imply it.
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
)

# Marker embedded in every vendored `.claude/**.md`, distinct from
# GENERATED_SENTINEL: a vendored file is a verbatim upstream copy, not our
# render. Greppable so refresh/uninstall recognise (and never clobber) it.
VENDORED_SENTINEL = "<!-- dummyindex:installed -->"

# Capability inference for *discovered* plugins: free-text tokens (plugin name,
# description, keywords, category) -> a canonical Capability. Broader than the
# proposal table — discovery WANTS implement/test/review hits because the user
# explicitly asked to find tools. First match in iteration order wins per
# capability; one plugin can yield several. capability -> the tokens that imply
# it. Tokens are matched as WHOLE WORDS (plugins/discover.py), so the bare
# 'auth' row carries the spelled-out forms too; 'audit' lives in REVIEW (a
# "design audit toolkit" is a review tool, not a security one — evidence 27).
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
