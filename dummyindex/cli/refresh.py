"""`dummyindex context refresh-indexes` — rebuild INDEX.md from disk after enrichment."""
from __future__ import annotations
import sys
from .common import parse_path_and_root, resolve_context_root
from .migrate import migrate_legacy_layout


def run(args: list[str]) -> int:
    from dummyindex.context.output.docs import refresh_index_md
    from dummyindex.context.domains.features import (
        rebuild_features_graph,
        refresh_features_index_md,
    )

    scope, explicit_root, rest = parse_path_and_root(args)
    if rest:
        print(
            f"error: unknown argument(s) for `refresh-indexes`: {rest}",
            file=sys.stderr,
        )
        return 2
    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    # ----- v0.6+ migration: old `.context/graph/` and oversized CLAUDE.md ---
    migrate_legacy_layout(context_dir, out_root)

    rels = refresh_index_md(context_dir)
    print(
        f"context refresh-indexes: regenerated {context_dir / 'INDEX.md'} "
        f"({len(rels)} entries)"
    )

    features_dir = context_dir / "features"
    if features_dir.is_dir():
        try:
            refresh_features_index_md(features_dir)
            print(f"  + regenerated {features_dir / 'INDEX.md'}")
        except FileNotFoundError:
            # features/INDEX.json missing — nothing to refresh.
            pass
        try:
            graph_json, graph_html = rebuild_features_graph(features_dir)
            print(f"  + rebuilt    {graph_json} (folder · file · feature · flow)")
            print(f"  + rebuilt    {graph_html}")
        except FileNotFoundError:
            pass
    return 0

