"""One-shot in-place migrations for older `.context/` layouts.

Called by the ``refresh-indexes`` command. Pre-v0.10 stored
``graph/graph.json`` and ``CLAUDE.md`` at different paths; this brings a
project forward without forcing a full rebuild.
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional


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
    """Relocate the managed block from <root>/CLAUDE.md to <root>/.claude/CLAUDE.md.

    Pre-v0.7.2 installs wrote the managed block to ``<root>/CLAUDE.md``.
    Newer installs keep CLAUDE.md inside ``.claude/`` so the project root
    stays clean. This helper:

    1. Always (re)writes ``.claude/CLAUDE.md`` with a current managed block.
    2. Strips the legacy managed block from ``<root>/CLAUDE.md`` if present.
    3. Deletes ``<root>/CLAUDE.md`` if stripping leaves it effectively empty
       (no user content beyond whitespace).
    """
    from dummyindex.context.output.bootstrap import (
        BEGIN_MARKER,
        END_MARKER,
        bootstrap_claude_md,
    )

    new_path = out_root / ".claude" / "CLAUDE.md"
    legacy_path = out_root / "CLAUDE.md"

    legacy_had_managed_block = False
    legacy_residue: Optional[str] = None
    if legacy_path.exists():
        try:
            legacy_text = legacy_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  migration warning: cannot read {legacy_path}: {exc}", file=sys.stderr)
            return
        if BEGIN_MARKER in legacy_text and END_MARKER in legacy_text:
            legacy_had_managed_block = True
            begin = legacy_text.index(BEGIN_MARKER)
            end = legacy_text.index(END_MARKER) + len(END_MARKER)
            legacy_residue = (legacy_text[:begin] + legacy_text[end:]).strip()

    if not legacy_had_managed_block and new_path.exists():
        # Nothing to migrate; .claude/CLAUDE.md already exists. Skip the
        # bootstrap call so we don't churn its mtime on every refresh.
        return

    try:
        bootstrap_claude_md(new_path)
    except Exception as exc:
        print(f"  migration warning: writing {new_path} failed: {exc}", file=sys.stderr)
        return

    if not legacy_had_managed_block:
        print(f"  migration: wrote {new_path.relative_to(out_root)}")
        return

    try:
        if legacy_residue:
            legacy_path.write_text(legacy_residue + "\n", encoding="utf-8")
            print(
                f"  migration: relocated CLAUDE.md managed block to "
                f"{new_path.relative_to(out_root)} (user content preserved at "
                f"{legacy_path.relative_to(out_root)})"
            )
        else:
            legacy_path.unlink()
            print(
                f"  migration: relocated CLAUDE.md to "
                f"{new_path.relative_to(out_root)} (removed empty root file)"
            )
    except OSError as exc:
        print(f"  migration warning: cleaning {legacy_path} failed: {exc}", file=sys.stderr)

