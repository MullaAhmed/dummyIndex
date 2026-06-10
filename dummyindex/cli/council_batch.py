"""`dummyindex context council-batch --next` — the parallel-council frontier.

Wire-only: parse flags, call the `council_batch` domain, print. The council
twin of `build --next-wave`. Reads non-trivial feature ids from
`features/INDEX.json`; the JSON payload carries `complete` + the stage + one
entry per dispatch-unit (feature, role, subagent_type, framework) so the
council skill can launch a parallel Task per unit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def _load_feature_ids(features_dir: Path) -> list[str]:
    """Non-trivial feature ids from INDEX.json (every entry is non-trivial)."""
    index_path = features_dir / "INDEX.json"
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not parse {index_path}: {exc}") from exc
    return [f["feature_id"] for f in data.get("features", []) if f.get("feature_id")]


def run(args: list[str]) -> int:
    from dummyindex.context.domains.council_batch import CouncilMode, next_batch

    # take_positional=False: this verb has no positional path, so the *value*
    # of `--mode`/`--cap` must not be mistaken for a scope argument (matches
    # council.py). Root is passed via `--root DIR`.
    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    # `--next` and `--tree-enrich` and `--json` are bare flags; strip them out
    # before kv parsing so they aren't mistaken for `--key value` pairs.
    bare = {"--next", "--json", "--tree-enrich"}
    flags = {a for a in rest if a in bare}
    rest = [a for a in rest if a not in bare]
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(f"error: unknown argument(s) for `council-batch`: {leftover}", file=sys.stderr)
        return 2

    if "--next" not in flags:
        print("error: council-batch requires --next", file=sys.stderr)
        return 2

    as_json = "--json" in flags
    tree_enrich = "--tree-enrich" in flags
    mode_raw = parsed.get("mode", "standard")
    try:
        mode = CouncilMode(mode_raw)
    except ValueError:
        print(f"error: --mode must be light|standard|deep, got {mode_raw!r}", file=sys.stderr)
        return 2
    try:
        cap = int(parsed.get("cap", "8"))
    except ValueError:
        print(f"error: --cap must be an integer, got {parsed.get('cap')!r}", file=sys.stderr)
        return 2

    repo_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = repo_root / ".context" / "features"
    if not (features_dir / "INDEX.json").is_file():
        print(
            f"error: {features_dir / 'INDEX.json'} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        feature_ids = tuple(_load_feature_ids(features_dir))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        batch = next_batch(
            features_dir, repo_root, feature_ids,
            mode=mode, cap=cap, tree_enrich=tree_enrich,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps({
            "complete": batch.complete,
            "stage": int(batch.stage) if batch.stage is not None else None,
            "mode": mode.value,
            "cap": cap,
            "units": [u.to_dict() for u in batch.units],
        }, indent=2))
        return 0

    if batch.complete:
        print("council-batch: all features complete for this mode.")
        return 0
    plural = "s" if len(batch.units) != 1 else ""
    print(
        f"council-batch: stage {int(batch.stage)} — {len(batch.units)} parallel "
        f"unit{plural} (dispatch concurrently, barrier, then re-run --next):"
    )
    for u in batch.units:
        fw = f" [{u.framework}]" if u.framework else ""
        print(f"  {u.feature_id}: {u.role} → {u.subagent_type}{fw}")
    return 0
