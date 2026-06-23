"""Deterministic consistency scan for a proposal title.

Reuses the ``query`` retrieval domain to surface features the title likely
touches, and lists the ``.context/conventions/*.md`` files a plan should
honor. **No LLM** — same machinery the agent could walk by hand.
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.context.domains.query import query

from .models import ConsistencyHits

# How many related features to surface. The proposal head is a navigation
# hint, not an exhaustive index — a handful is plenty.
_MAX_RELATED_FEATURES = 5

# Where convention docs live, relative to `.context/`.
_CONVENTIONS_REL = "conventions"


def scan_consistency(context_dir: Path, title: str) -> ConsistencyHits:
    """Score features by ``title`` and list existing convention docs.

    Degrades gracefully: if the features index hasn't been built yet
    (``query`` raises ``FileNotFoundError``), related features come back
    empty and only the conventions glob is returned.
    """
    related = _related_features(context_dir, title)
    conventions = _conventions(context_dir)
    return ConsistencyHits(related_features=related, conventions=conventions)


def _related_features(context_dir: Path, title: str) -> tuple[str, ...]:
    try:
        result = query(context_dir, title, top_k=_MAX_RELATED_FEATURES)
    except FileNotFoundError:
        # No features/INDEX.json yet — the repo hasn't been fully indexed.
        # A proposal can still be scaffolded; it just carries no related
        # features until the index exists.
        return ()
    return tuple(m.feature.feature_id for m in result.matches)


def _conventions(context_dir: Path) -> tuple[str, ...]:
    conv_dir = context_dir / _CONVENTIONS_REL
    if not conv_dir.is_dir():
        return ()
    paths = sorted(p.name for p in conv_dir.glob("*.md") if p.is_file())
    return tuple(f"{_CONVENTIONS_REL}/{name}" for name in paths)
