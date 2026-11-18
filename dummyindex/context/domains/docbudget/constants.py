"""Package-private constants for the docbudget domain.

Ceilings live in code, not config. A doc with no ratchet entry must fit its
ceiling; a recorded doc may not grow past its recorded size.
"""

from __future__ import annotations

__all__ = [
    "CONTEXT_CEILING",
    "CONTEXT_RATCHET_REL",
    "SKILLS_CEILING",
    "SKILLS_RATCHET_REL",
    "STE_RULESET_VERSION",
    "STYLE_CEILING",
    "STYLE_RATCHET_REL",
    "RATCHET_SEPARATOR",
]

# Word ceiling for an unrecorded authored `.context/` doc.
CONTEXT_CEILING = 1500
# Word ceiling for an unrecorded packaged SKILL.md.
SKILLS_CEILING = 2500

CONTEXT_RATCHET_REL = ".context/doc-budget.txt"
SKILLS_RATCHET_REL = "tests/data/skill-budget.txt"

# Style-violation ceiling for an unrecorded doc: zero, no free violations.
STYLE_CEILING = 0
STYLE_RATCHET_REL = ".context/style-budget.txt"
# Bump when a strict rule or the standard text changes; stale style ratchets re-seed.
STE_RULESET_VERSION = 1

# One ratchet line is `path<TAB>words`.
RATCHET_SEPARATOR = "\t"
