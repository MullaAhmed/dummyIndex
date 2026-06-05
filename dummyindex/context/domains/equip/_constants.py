"""Package-private constants for `context/equip/`.

Kept out of `enums.py` because schema version is a tunable,
not a closed-alphabet enum.
"""
from __future__ import annotations

SCHEMA_VERSION = 2

# Sentinel embedded in equip's PostToolUse format-hook command string, so
# install/refresh/uninstall can recognise our settings.json entry among the
# user's other hooks. Distinct from the auto-refresh hook's
# ``DUMMYINDEX_AUTO_REFRESH`` so the two coexist and uninstall independently.
EQUIP_SENTINEL = "DUMMYINDEX_EQUIP"

# Shared capability vocabulary. One keyword table maps free-text tokens (found
# in an agent file stem, or harvested from a proposal's plan/checklist) to a
# canonical capability. Used by adoption (infer a project agent's coverage from
# its stem) and proposal scoping (extract needed capabilities). First match in
# iteration order wins per capability; a stem/text can yield several.
#
# capability -> the substring tokens that imply it.
_CAPABILITY_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("database", ("database", "db", "data", "migration", "sql")),
    ("security", ("security", "auth", "secret")),
    ("frontend", ("frontend", "ui", "css", "react", "vue", "svelte")),
    ("performance", ("performance", "perf", "optimi")),
    ("docs", ("docs", "documentation", "doc")),
    ("test", ("test", "qa")),
    ("review", ("review", "audit")),
    ("implement", ("implement", "build", "feature")),
)
