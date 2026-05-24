"""`dummyindex context <subcommand>` dispatch.

Wired in from `dummyindex/__main__.py`. Subcommands:

- `init`           run the full deterministic backbone build + CLAUDE.md bootstrap
- `rebuild`        re-run the backbone (use `--changed` for incremental)
- `bootstrap`      regenerate the CLAUDE.md managed block only
- `enrich-plan`    emit `.context/_enrich_plan.json` listing tree.json stub
                   nodes (the work-list for the /dummyindex skill)
- `enrich-apply`   merge a `{node_id: abstract}` JSON file into tree.json,
                   bumping each touched node's confidence to INFERRED
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

_USAGE = """\
Usage: dummyindex context <subcommand> [args]

Subcommands:
  init [path]                       Initialize .context/ in the target repo (default: cwd)
  rebuild [--changed] [path]        Rebuild .context/ (use --changed for incremental)
  bootstrap [path]                  Write/regenerate the CLAUDE.md managed block
  enrich-plan [path]                Emit .context/_enrich_plan.json (work-list)
  enrich-apply [path] --from-json FILE
                                    Merge {node_id: abstract} JSON into tree.json
"""


def dispatch(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    subcmd, rest = argv[0], argv[1:]
    handler = _HANDLERS.get(subcmd)
    if handler is None:
        print(f"error: unknown context subcommand '{subcmd}'", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    return handler(rest)


def _cmd_init(args: list[str]) -> int:
    from dummyindex.context.runner import build_all

    target = Path(args[0]) if args and not args[0].startswith("--") else Path(".")
    try:
        from importlib.metadata import version
        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"
    result = build_all(target, bootstrap=True, dummyindex_version=di_version)
    print(f"context init: wrote {len(result.written)} files to {result.context_dir}")
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    if result.languages:
        print(f"  languages: {', '.join(result.languages)}")
    if result.bootstrapped:
        print(f"  CLAUDE.md  ->  managed block written")
    return 0


def _cmd_rebuild(args: list[str]) -> int:
    changed_only = "--changed" in args
    # Allow `rebuild [--changed] [path]` in either order
    path_args = [a for a in args if not a.startswith("--")]
    target = Path(path_args[0]) if path_args else Path(".")
    try:
        from importlib.metadata import version
        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    if changed_only:
        from dummyindex.context.incremental import rebuild_changed
        result = rebuild_changed(target, dummyindex_version=di_version)
        if result.skipped:
            print("context rebuild: no source files changed; .context/ unchanged.")
            return 0
        ch = result.changes
        print(
            f"context rebuild: {len(ch.added)} added, {len(ch.modified)} modified, "
            f"{len(ch.removed)} removed → rebuilt {result.build_result.context_dir}"
            if result.build_result else "rebuild ran"
        )
        return 0
    from dummyindex.context.runner import build_all
    result = build_all(target, dummyindex_version=di_version)
    print(f"context rebuild: wrote {len(result.written)} files to {result.context_dir}")
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    return 0


def _cmd_bootstrap(args: list[str]) -> int:
    from dummyindex.context.bootstrap import (
        UnbalancedMarkersError,
        bootstrap_claude_md,
    )

    target = Path(args[0]) if args else Path(".")
    claude_md = target / "CLAUDE.md"
    try:
        bootstrap_claude_md(claude_md)
    except UnbalancedMarkersError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(f"CLAUDE.md  ->  managed block written: {claude_md.resolve()}")
    return 0


def _cmd_enrich_plan(args: list[str]) -> int:
    from dummyindex.context.enrich import build_plan, write_plan

    target = Path(args[0]) if args and not args[0].startswith("--") else Path(".")
    context_dir = (target / ".context").resolve()
    if not context_dir.exists():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest {target}` first.",
            file=sys.stderr,
        )
        return 2
    try:
        plan = build_plan(context_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = context_dir / "_enrich_plan.json"
    write_plan(out_path, plan)
    stats = plan.stats
    print(
        f"context enrich-plan: wrote {out_path.relative_to(target.resolve())}"
        if target.resolve() in out_path.parents or target.resolve() == out_path.parent
        else f"context enrich-plan: wrote {out_path}"
    )
    print(
        f"  total nodes: {stats['total_nodes']}  stubs: {stats['stub_nodes']}  "
        f"by_kind: {stats['by_kind']}"
    )
    print(f"  batches: {len(plan.batches)}")
    return 0


def _cmd_enrich_apply(args: list[str]) -> int:
    from dummyindex.context.enrich import apply_updates

    # Parse args: optional positional path, required `--from-json FILE`.
    target = Path(".")
    from_json: Path | None = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--from-json" and i + 1 < len(args):
            from_json = Path(args[i + 1])
            i += 2
        elif a.startswith("--from-json="):
            from_json = Path(a.split("=", 1)[1])
            i += 1
        elif not a.startswith("--"):
            target = Path(a)
            i += 1
        else:
            print(f"error: unknown flag {a!r}", file=sys.stderr)
            return 2

    if from_json is None:
        print(
            "error: --from-json FILE is required (JSON mapping {node_id: abstract})",
            file=sys.stderr,
        )
        return 2
    if not from_json.exists():
        print(f"error: {from_json} not found", file=sys.stderr)
        return 2

    context_dir = (target / ".context").resolve()
    if not (context_dir / "tree.json").exists():
        print(
            f"error: {context_dir}/tree.json not found. Run `dummyindex ingest {target}` first.",
            file=sys.stderr,
        )
        return 2

    payload = json.loads(from_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in payload.items()
    ):
        print(
            f"error: {from_json} must be a JSON object mapping string node_id -> string abstract",
            file=sys.stderr,
        )
        return 2

    result = apply_updates(context_dir, payload)
    print(
        f"context enrich-apply: updated {len(result.updated)} abstract(s) in "
        f"{context_dir / 'tree.json'}"
    )
    if result.unknown:
        print(
            f"  warning: {len(result.unknown)} node_id(s) not found in tree.json:",
            file=sys.stderr,
        )
        for nid in result.unknown:
            print(f"    - {nid}", file=sys.stderr)
        return 1
    return 0


_HANDLERS: dict[str, Callable[[list[str]], int]] = {
    "init": _cmd_init,
    "rebuild": _cmd_rebuild,
    "bootstrap": _cmd_bootstrap,
    "enrich-plan": _cmd_enrich_plan,
    "enrich-apply": _cmd_enrich_apply,
}
