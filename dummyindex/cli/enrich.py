"""`dummyindex context enrich-plan` / `enrich-apply` — work-list + writeback for /dummyindex."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Optional
from .common import parse_path_and_root, resolve_context_root


def run_plan(args: list[str]) -> int:
    from dummyindex.context.domains.enrich import build_plan, write_plan

    scope, explicit_root, rest = parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `enrich-plan`: {rest}", file=sys.stderr)
        return 2
    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.exists():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest {out_root}` first.",
            file=sys.stderr,
        )
        return 2
    try:
        plan = build_plan(context_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Transient enrichment work-list — a local scratch artefact, not a
    # committed doc. Lives under cache/ (gitignored). write_plan creates the
    # parent dir, so a fresh tree without cache/ is fine.
    out_path = context_dir / "cache" / "_enrich_plan.json"
    write_plan(out_path, plan)
    stats = plan.stats
    try:
        rel = out_path.relative_to(Path.cwd().resolve())
        print(f"context enrich-plan: wrote {rel}")
    except ValueError:
        print(f"context enrich-plan: wrote {out_path}")
    print(
        f"  total nodes: {stats['total_nodes']}  stubs: {stats['stub_nodes']}  "
        f"by_kind: {stats['by_kind']}"
    )
    print(f"  batches: {len(plan.batches)}")
    return 0


def run_apply(args: list[str]) -> int:
    from dummyindex.context.domains.enrich import apply_updates

    scope, explicit_root, rest = parse_path_and_root(args)

    # Pull `--from-json` out of the remaining args.
    from_json: Optional[Path] = None
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--from-json" and i + 1 < len(rest):
            from_json = Path(rest[i + 1])
            i += 2
        elif a.startswith("--from-json="):
            from_json = Path(a.split("=", 1)[1])
            i += 1
        else:
            leftover.append(a)
            i += 1
    if leftover:
        print(f"error: unknown argument(s) for `enrich-apply`: {leftover}", file=sys.stderr)
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

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not (context_dir / "tree.json").exists():
        print(
            f"error: {context_dir}/tree.json not found. Run `dummyindex ingest {out_root}` first.",
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

