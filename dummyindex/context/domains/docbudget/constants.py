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
    "RATCHET_SEPARATOR",
]

# Word ceiling for an unrecorded authored `.context/` doc.
CONTEXT_CEILING = 1500
# Word ceiling for an unrecorded packaged SKILL.md.
SKILLS_CEILING = 2500

CONTEXT_RATCHET_REL = ".context/doc-budget.txt"
SKILLS_RATCHET_REL = "tests/data/skill-budget.txt"

# One ratchet line is `path<TAB>words`.
RATCHET_SEPARATOR = "\t"
