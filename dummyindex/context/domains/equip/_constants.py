"""Package-private constants for `context/equip/`.

Kept out of `enums.py` because schema version is a tunable,
not a closed-alphabet enum.
"""
from __future__ import annotations

from .enums import Capability

SCHEMA_VERSION = 2

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
# ``_CAPABILITY_TOKENS``: only the five *specialist* capabilities a proposal can
# ask equip to adopt for. The broad test/review/implement tokens are excluded on
# purpose — those words appear in essentially every plan.md, and including them
# would adopt a generic specialist on every proposal. Mirrors spec §6's keyword
# list verbatim. capability -> the substring tokens that imply it.
_PROPOSAL_CAPABILITY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (Capability.DATABASE, ("database", "migration", "sql")),
    (Capability.SECURITY, ("security", "auth", "secret")),
    (Capability.FRONTEND, ("frontend", "ui", "css", "react")),
    (Capability.PERFORMANCE, ("performance", "optimi")),
    (Capability.DOCS, ("docs", "documentation")),
)
