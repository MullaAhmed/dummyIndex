"""`dummyindex context council-batch --next` — the parallel-council frontier.

Wire-only: parse flags, call the `council_batch` domain, print. The council
twin of `build --next-wave`. Reads feature ids from `features/INDEX.json`
(Outcome-C standalone entries are exempted by the domain); the JSON payload
carries `complete` + the stage + one entry per dispatch-unit (feature, role,
subagent_type, framework) so the council skill can launch a parallel Task per
unit. `--feature ID` (repeatable) scopes the frontier; `--feature ID --force`
starts a forced re-council for already-complete scoped features (kick-off is
idempotent mid-run, so the loop converges).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import (
    parse_kv_flags,
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
)


def _warn_if_backfill_needed(
    features_dir: Path, feature_ids: tuple[str, ...]
) -> None:
    """One-line stderr pointer when most logs predate the batch convention.

    A pre-v0.20 index (enrichment artifacts on disk, empty council logs) makes
    the frontier reschedule EVERY stage — the plan.md-clobber hazard. Surfaced
    here so the orchestrator runs `council-log backfill` instead of
    misdiagnosing drift signals.
    """
    from dummyindex.context.domains.council import needs_artifact_backfill

    if not feature_ids:
        return
    pending = sum(
        1 for fid in feature_ids if needs_artifact_backfill(features_dir, fid)
    )
    if pending * 2 > len(feature_ids):
        print(
            f"warning: {pending} of {len(feature_ids)} features have enrichment "
            f"artifacts but empty council logs — run `dummyindex context "
            f"council-log backfill` once before dispatching, or the council "
            f"will re-run (and overwrite) already-curated docs.",
            file=sys.stderr,
        )


def _load_feature_ids(features_dir: Path) -> list[str]:
    """Every feature id in INDEX.json (incl. Outcome-C standalone entries —
    the domain frontier exempts those via their stage-0 council-log note)."""
    index_path = features_dir / "INDEX.json"
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not parse {index_path}: {exc}") from exc
    return [f["feature_id"] for f in data.get("features", []) if f.get("feature_id")]


def run(args: list[str]) -> int:
    from dummyindex.context.domains.council_batch import (
        CouncilMode,
        force_recouncil,
        next_batch,
    )

    # take_positional=False: this verb has no positional path, so the *value*
    # of `--mode`/`--cap` must not be mistaken for a scope argument (matches
    # council.py). Root is passed via `--root DIR`.
    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    feature_values, rest = pull_repeatable_flag(rest, "feature")
    # `--next`, `--tree-enrich`, `--json` and `--force` are bare flags; strip
    # them out before kv parsing so they aren't mistaken for `--key value`.
    bare = {"--next", "--json", "--tree-enrich", "--force"}
    flags = {a for a in rest if a in bare}
    rest = [a for a in rest if a not in bare]
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(f"error: unknown argument(s) for `council-batch`: {leftover}", file=sys.stderr)
        return 2

    if "--next" not in flags:
        print("error: council-batch requires --next", file=sys.stderr)
        return 2

    force = "--force" in flags
    if force and not feature_values:
        print(
            "error: --force requires at least one --feature <id> "
            "(a forced re-council is always scoped)",
            file=sys.stderr,
        )
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
        all_ids = tuple(_load_feature_ids(features_dir))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if feature_values:
        unknown = sorted(set(feature_values) - set(all_ids))
        if unknown:
            print(
                f"error: unknown --feature id(s): {', '.join(unknown)} "
                f"(not in features/INDEX.json)",
                file=sys.stderr,
            )
            return 2
        feature_ids = tuple(fid for fid in all_ids if fid in set(feature_values))
    else:
        feature_ids = all_ids

    _warn_if_backfill_needed(features_dir, feature_ids)

    forced: tuple[str, ...] = ()
    if force:
        from dummyindex.context.domains.council import CouncilLogError

        try:
            forced = force_recouncil(
                features_dir, feature_ids, mode=mode, tree_enrich=tree_enrich
            )
        except CouncilLogError as exc:
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
            "forced": list(forced),
            "units": [u.to_dict() for u in batch.units],
        }, indent=2))
        return 0

    if forced:
        print(f"council-batch: forced re-council for: {', '.join(forced)}")
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
