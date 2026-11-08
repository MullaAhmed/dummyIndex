"""Package-private constants for the docguard (managed-doc-home) domain.

Fixed rel-paths and the closed sets the path heuristics key on. The managed roots
are re-exported from the domains that own them (``proposals``/``audit``), never
re-declared, so "where proposals/audits live" has a single source of truth.
"""

from __future__ import annotations

from ..audit.workspace import AUDITS_REL
from ..proposals.store import PROPOSALS_REL

__all__ = [
    "AUDITS_REL",
    "AUDIT_SEGMENT",
    "CONTEXT_DIR_NAME",
    "DESIGN_SUFFIX",
    "DOCS_DIR_NAME",
    "EXCLUDED_DOCS_SUBTREES",
    "MARKDOWN_SUFFIX",
    "PLANNING_SEGMENTS",
    "PROPOSALS_REL",
    "ROOT_DOC_STEMS",
]

# Managed context dir at the repo root; anything under it is never a stray. A
# literal because the repo has no canonical ``.context`` constant to reuse.
CONTEXT_DIR_NAME = ".context"

# The user-facing published tree the location gate keys on: a planning doc is
# only ever a stray when its repo-relative path lives under this directory.
DOCS_DIR_NAME = "docs"

# Only markdown is ever classified as a planning doc.
MARKDOWN_SUFFIX = ".md"

# Suffix marking the *spec* member of a ``(directory, stem)`` pair:
# ``<stem>-design.md`` is the spec, ``<stem>.md`` is the plan.
DESIGN_SUFFIX = "-design"

# Directory segments (anywhere under ``docs/``) that mark an internal planning
# home — covers ``docs/specs``, ``docs/plans``, ``docs/superpowers/{plans,specs}``,
# ``docs/internal/audits``, etc.
PLANNING_SEGMENTS = frozenset({"plans", "specs", "proposals", "audits"})

# A planning doc under this segment routes to the AUDIT home; everything else
# routes to the PROPOSAL home.
AUDIT_SEGMENT = "audits"

# Published ``docs/`` subtrees that are never strays even though they hold
# ``.md`` (the user-facing guide / reference / generated source-doc index).
EXCLUDED_DOCS_SUBTREES = frozenset({"guide", "reference", "sources"})

# Root-level ``.md`` files that are project chrome, never planning docs.
ROOT_DOC_STEMS = frozenset({"readme", "changelog", "architecture", "security"})
