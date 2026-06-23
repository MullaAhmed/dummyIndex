"""`refresh-indexes` legacy-layout + CLAUDE.md consolidation (plan task 12).

The `refresh-indexes` command runs :func:`migrate_legacy_layout`, which does
TWO independent one-shot migrations:

1. The pre-v0.6 ``.context/graph/`` folder (``graph.json`` +
   ``GRAPH_REPORT.md`` + the pyvis ``graph.html`` hairball) is folded into
   ``.context/features/`` (``symbol-graph.json`` / ``COMMUNITIES.md``) and the
   legacy folder removed. This migration is **out of scope** for the
   onboarding-bug fix and must stay byte-for-byte unchanged.

2. A dangling root ``<root>/CLAUDE.md`` is consolidated into the canonical
   ``.claude/CLAUDE.md`` via the now-wire-only ``migrate_claude_md_location``
   wrapper over ``reconcile_claude_md``.

This module seeds a real pre-v0.10 layout under ``tmp_path`` and asserts BOTH
migrations fire from the single ``refresh-indexes`` invocation — the
regression guard that the consolidation rewrite left the legacy ``graph/``
migration intact.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER
from tests.paths import SAMPLE_REPO


def _ingested(tmp_path: Path, name: str) -> Path:
    """Copy SAMPLE_REPO into tmp_path and `init` it so `.context/` exists."""
    target = tmp_path / name
    shutil.copytree(SAMPLE_REPO, target)
    assert dispatch(["init", str(target)]) == 0
    return target


def _seed_legacy_graph(context_dir: Path) -> dict[str, str]:
    """Build a real pre-v0.6 ``.context/graph/`` folder with sentinel content.

    Returns the sentinel strings written so the test can assert the exact
    bytes survived the move into ``features/``.
    """
    legacy_graph = context_dir / "graph"
    legacy_graph.mkdir(parents=True, exist_ok=True)

    graph_json_body = '{"legacy": "graph.json sentinel"}'
    graph_report_body = "# Legacy GRAPH_REPORT\n\ncommunities sentinel\n"
    (legacy_graph / "graph.json").write_text(graph_json_body, encoding="utf-8")
    (legacy_graph / "GRAPH_REPORT.md").write_text(graph_report_body, encoding="utf-8")
    # The pyvis hairball the v0.6 migration drops on the floor.
    (legacy_graph / "graph.html").write_text("<html>hairball</html>", encoding="utf-8")

    return {"json": graph_json_body, "report": graph_report_body}


@pytest.mark.integration
def test_refresh_indexes_runs_graph_migration_and_claude_md_consolidation(
    tmp_path: Path,
) -> None:
    """One `refresh-indexes` invocation fires BOTH legacy migrations.

    - The legacy ``graph/`` folder is gone; its salvageable artifacts land at
      ``features/symbol-graph.json`` + ``features/COMMUNITIES.md``.
    - The dangling root ``./CLAUDE.md`` (user content) is consolidated into
      ``.claude/CLAUDE.md`` (user content preserved + exactly one managed
      block), and the root file is removed.
    """
    target = _ingested(tmp_path, "refresh_legacy_both")
    context_dir = target / ".context"
    features_dir = context_dir / "features"

    # --- Seed the legacy graph/ layout. To exercise the *move* branch (not the
    # "new location already populated → delete stale" branch), remove the
    # freshly-built destinations so the migration has to relocate the legacy
    # files into place.
    sentinels = _seed_legacy_graph(context_dir)
    (features_dir / "symbol-graph.json").unlink(missing_ok=True)
    (features_dir / "COMMUNITIES.md").unlink(missing_ok=True)

    # --- Seed the dangling root CLAUDE.md with hand-written user content
    # (no managed block) — the onboarding-dangling case.
    user_content = "# My project notes\n\nHand-written guidance that must survive."
    root_claude = target / "CLAUDE.md"
    root_claude.write_text(user_content + "\n", encoding="utf-8")

    # --- Run the real refresh-indexes migration path.
    assert dispatch(["refresh-indexes", str(target)]) == 0

    # === Assertion 1: the legacy graph/ migration ran ===
    legacy_graph = context_dir / "graph"
    assert not legacy_graph.exists(), (
        f"legacy graph/ dir should be removed once empty, leftover: "
        f"{[p.name for p in legacy_graph.iterdir()] if legacy_graph.exists() else '(removed)'}"
    )
    symbol_graph = features_dir / "symbol-graph.json"
    communities = features_dir / "COMMUNITIES.md"
    assert symbol_graph.exists(), (
        "graph.json should be moved to features/symbol-graph.json"
    )
    assert communities.exists(), (
        "GRAPH_REPORT.md should be moved to features/COMMUNITIES.md"
    )
    # Exact bytes survived the relocation. Neither symbol-graph.json nor
    # COMMUNITIES.md is rebuilt by refresh-indexes (it re-emits only the viewer
    # `graph.json`/`graph.html`), so these prove the legacy files were *moved*.
    assert symbol_graph.read_text(encoding="utf-8") == sentinels["json"]
    assert communities.read_text(encoding="utf-8") == sentinels["report"]
    # The legacy graph/ folder is gone in its entirety — the pyvis hairball
    # (graph/graph.html) was dropped, never carried into features/.
    # (`features/graph.html` is a *current* artifact the post-migration
    # `rebuild_features_graph` legitimately re-emits; the contract is only that
    # the legacy `graph/` dir and its hairball are removed.)
    assert not (legacy_graph / "graph.html").exists()

    # === Assertion 2: the CLAUDE.md consolidation ran ===
    canonical = target / ".claude" / "CLAUDE.md"
    assert canonical.exists(), ".claude/CLAUDE.md must exist after consolidation"
    assert not root_claude.exists(), (
        "root ./CLAUDE.md must be removed after consolidation"
    )

    canonical_text = canonical.read_text(encoding="utf-8")
    # User content preserved...
    assert "Hand-written guidance that must survive." in canonical_text
    # ...with exactly one managed block.
    assert canonical_text.count(BEGIN_MARKER) == 1
    assert canonical_text.count(END_MARKER) == 1
