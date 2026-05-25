"""`dummyindex context rebuild` — re-run the backbone (use --changed for incremental)."""
from __future__ import annotations
import sys
from pathlib import Path
from ._common import (
    _parse_path_and_root,
    _pull_repeatable_flag,
    _resolve_context_root,
    _resolve_doc_paths,
)


def _cmd_rebuild(args: list[str]) -> int:
    scope, explicit_root, rest = _parse_path_and_root(args)
    doc_values, rest = _pull_repeatable_flag(rest, "docs")
    changed_only = "--changed" in rest
    rest = [a for a in rest if a != "--changed"]
    if rest:
        print(f"error: unknown argument(s) for `rebuild`: {rest}", file=sys.stderr)
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    extra_doc_roots = _resolve_doc_paths(doc_values, base=Path.cwd())

    try:
        from importlib.metadata import version

        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    if changed_only:
        from dummyindex.context.build.incremental import rebuild_changed

        result = rebuild_changed(
            out_root,
            dummyindex_version=di_version,
            extra_doc_roots=extra_doc_roots,
        )
        if result.skipped:
            print("context rebuild: no source files changed; .context/ unchanged.")
            return 0
        ch = result.changes
        print(
            f"context rebuild: {len(ch.added)} added, {len(ch.modified)} modified, "
            f"{len(ch.removed)} removed → rebuilt {result.build_result.context_dir}"
            if result.build_result
            else "rebuild ran"
        )
        return 0

    from dummyindex.context.build.runner import build_all

    result = build_all(
        scope,
        out_root=out_root,
        dummyindex_version=di_version,
        extra_doc_roots=extra_doc_roots,
    )
    print(
        f"context rebuild: wrote {len(result.written)} files to {result.context_dir}"
    )
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    return 0

