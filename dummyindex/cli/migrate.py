"""One-shot in-place migrations for older `.context/` layouts.

Called by the ``refresh-indexes`` command. Pre-v0.10 stored
``graph/graph.json`` and ``CLAUDE.md`` at different paths; this brings a
project forward without forcing a full rebuild.
"""

from __future__ import annotations

import sys
from pathlib import Path


def migrate_legacy_layout(context_dir: Path, out_root: Path) -> None:
    """One-shot migrations for projects that were ingested by pre-v0.6 dummyindex.

    - `.context/graph/` (pyvis HTML + graph.json + GRAPH_REPORT.md) is gone.
      Move what's salvageable into `.context/features/` and delete the folder.
    - CLAUDE.md managed block was 40+ lines; shrink to the v0.6 3-line pointer.
    """
    legacy_graph = context_dir / "graph"
    if legacy_graph.is_dir():
        features_dir = context_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)

        # Migrate legacy graph.json → features/symbol-graph.json. If the new
        # location is already populated (a v0.7 rebuild ran first), the
        # legacy file is just stale — delete it.
        old_json = legacy_graph / "graph.json"
        new_json = features_dir / "symbol-graph.json"
        if old_json.exists():
            if new_json.exists():
                old_json.unlink()
            else:
                old_json.replace(new_json)

        # Migrate legacy GRAPH_REPORT.md → features/COMMUNITIES.md. Same rule.
        old_report = legacy_graph / "GRAPH_REPORT.md"
        new_report = features_dir / "COMMUNITIES.md"
        if old_report.exists():
            if new_report.exists():
                old_report.unlink()
            else:
                old_report.replace(new_report)

        # Drop the pyvis HTML — it's the hairball v0.6 dropped.
        legacy_html = legacy_graph / "graph.html"
        if legacy_html.exists():
            legacy_html.unlink()

        # Remove the folder if it's empty now.
        try:
            for leftover in legacy_graph.iterdir():
                print(
                    f"  migration: leaving unexpected file in legacy graph/: "
                    f"{leftover.name}",
                    file=sys.stderr,
                )
                break
            else:
                legacy_graph.rmdir()
                print(
                    f"  migration: dropped legacy {legacy_graph} "
                    f"(symbol-graph + COMMUNITIES moved to features/)"
                )
        except OSError as exc:
            print(f"  migration warning: {exc}", file=sys.stderr)

    # Shrink an oversized CLAUDE.md managed block and relocate the file from
    # the project root (pre-v0.7.2) to .claude/CLAUDE.md (current).
    migrate_claude_md_location(out_root)


def migrate_claude_md_location(out_root: Path) -> None:
    """Fold a legacy root ``CLAUDE.md`` into the canonical ``.claude/CLAUDE.md``.

    Wire-only CLI wrapper over the domain helper
    :func:`dummyindex.context.output.claude_md.reconcile_claude_md`: the helper
    does all the folding/stripping/atomic-write/delete work and returns a
    structured :class:`ClaudeMdReconcileResult`; this function only prints a
    user-facing line derived from that result. Invoked from
    :func:`migrate_legacy_layout` (and thereby ``refresh-indexes``).
    """
    from dummyindex.context.output.claude_md import reconcile_claude_md

    result = reconcile_claude_md(out_root)
    print(f"  migration: {result.message}")
    for warning in result.warnings:
        print(f"  migration warning: {warning}", file=sys.stderr)
