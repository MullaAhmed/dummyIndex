"""`dummyindex context dev-pick --feature ID` — stack-aware author picker.

Thin CLI: resolves the feature's files + the repo's dependency tokens via the
`dev_pick` domain helpers, calls `pick_dev`, prints the JSON. Deterministic.
"""
from __future__ import annotations

import json
import sys

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    from dummyindex.context.domains.dev_pick import (
        harvest_dep_tokens,
        pick_dev,
        read_feature_files,
    )

    scope, explicit_root, rest = parse_path_and_root(args)
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(f"error: unknown argument(s) for `dev-pick`: {leftover}", file=sys.stderr)
        return 2
    feature_id = parsed.get("feature")
    if not feature_id:
        print("error: --feature <id> is required", file=sys.stderr)
        return 2

    repo_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = repo_root / ".context" / "features"

    try:
        feature_files = read_feature_files(features_dir, feature_id)
    except FileNotFoundError as exc:
        print(f"error: feature {feature_id} not found ({exc})", file=sys.stderr)
        return 2

    dep_tokens = harvest_dep_tokens(repo_root)
    pick = pick_dev(feature_files=feature_files, dep_tokens=dep_tokens)
    print(json.dumps(pick.to_dict()))
    return 0
