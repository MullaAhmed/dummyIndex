"""`dummyindex context council-log` — append a council-debate log row.

Also hosts the `council-log backfill` subverb: synthesize `complete` entries
for stages whose council-authored artifacts (spec.md / plan.md / concerns.md /
enriched flow narratives) predate the council-batch log convention, so the
frontier doesn't reschedule (and clobber) already-curated docs.
"""

from __future__ import annotations

import json
import sys

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    """Append a council-log entry for a (feature, stage, agent) triple."""
    from dummyindex.context.domains.council import CouncilLogError, append_log

    if args[:1] == ["backfill"]:
        return _run_backfill(args[1:])

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `council-log`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    stage = parsed.get("stage")
    agent = parsed.get("agent")
    log_status = parsed.get("status")
    note = parsed.get("note")
    if not all((feature_id, stage, agent, log_status)):
        print(
            "error: --feature <id>, --stage <n>, --agent <name>, --status <state> are all required",
            file=sys.stderr,
        )
        return 2

    try:
        stage_int = int(stage)
    except ValueError:
        print(f"error: --stage must be an integer, got {stage!r}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        entry = append_log(
            features_dir,
            feature_id=feature_id,
            stage=stage_int,
            agent=agent,
            status=log_status,
            note=note,
        )
    except CouncilLogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context council-log: {feature_id} stage={entry.stage} "
        f"agent={entry.agent} status={entry.status}"
    )
    return 0


def _run_backfill(args: list[str]) -> int:
    """`dummyindex context council-log backfill [--feature ID] [--root DIR]`.

    Scopes to one feature with `--feature`, else walks every entry in
    features/INDEX.json. Idempotent; never touches a stage that already has
    log entries.
    """
    from dummyindex.context.domains.council import (
        CouncilLogError,
        backfill_log_from_artifacts,
    )

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `council-log backfill`: {leftover}",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    index_path = features_dir / "INDEX.json"
    if not index_path.is_file():
        print(
            f"error: {index_path} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not parse {index_path}: {exc}", file=sys.stderr)
        return 2
    indexed = [f["feature_id"] for f in data.get("features", []) if f.get("feature_id")]

    feature_id = parsed.get("feature")
    if feature_id:
        if feature_id not in indexed:
            print(
                f"error: unknown --feature id: {feature_id} "
                f"(not in features/INDEX.json)",
                file=sys.stderr,
            )
            return 2
        targets = [feature_id]
    else:
        targets = indexed

    total = 0
    for fid in targets:
        try:
            stages = backfill_log_from_artifacts(features_dir, fid)
        except CouncilLogError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if stages:
            total += len(stages)
            print(
                f"context council-log backfill: {fid} → "
                f"stage(s) {', '.join(map(str, stages))}"
            )
    if total == 0:
        print("context council-log backfill: nothing to backfill (no-op)")
    return 0
