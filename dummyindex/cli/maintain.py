"""`dummyindex context maintain <verb>` — the one-command maintenance loop.

Sub-dispatches the first positional verb (``plan|begin|next|done|stamp|status``)
the same way ``cli/gc.py`` dispatches its verbs: parse this command's own flag
alphabet, lazy-import the domain inside ``run`` (the layering rule — ``cli``
imports the domain, never the reverse), call a fleet-domain function, print,
and return an exit code. No LLM calls live here: the host skill consumes
``next`` units and launches one subagent per unit, then reports back through
``done``/``stamp``. The loop's durable state is the committed
``.context/fleet/maintain-<ts>/`` run dir written by the fleet domain.

The six verbs:

- ``plan [--max-features N] [--json] [--root DIR]`` — read-only assembly:
  compute the reconcile report, list drifted features + awaiting-enrichment
  features (in that priority) with ``estimate:`` lines per feature, and note
  unassigned new files (placement work — they gate ``stamp`` but are not
  feature units). Exit 0.
- ``begin [--max-features N] [--all] [--json] [--root DIR]`` — write the run
  manifest + state under ``.context/fleet/maintain-<ts>/``. Requires either
  ``--max-features N`` or an explicit ``--all`` so an unbounded spend is
  never started silently.
- ``next [--run NAME] [--json] [--root DIR]`` — print the earliest incomplete
  unit (frontier semantics reused from ``council_batch.next_batch``) so the
  host skill launches exactly that unit.
- ``done --feature ID [--stage N] [--run NAME] [--root DIR]`` — mark a unit
  complete; without ``--stage`` the feature's earliest pending stage is taken.
- ``stamp --feature ID [--run NAME] [--force] [--to SHA] [--heal-orphaned]
  [--root DIR]`` — wrap ``reconcile-stamp`` for the finished feature and tick
  its units done in state on success; a refused stamp leaves state untouched.
- ``status [--run NAME] [--json] [--root DIR]`` — counts done/pending/skipped,
  elapsed, and the clearly-labelled heuristic remaining estimate.

Every verb accepts ``--run <name-or-dir>`` where relevant; the default is the
newest ``maintain-*`` run under ``.context/fleet/`` (prefix-scoped, so other
proposals' runs there are never picked up).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import resolve_context_root, usage_error

_MAINTAIN_USAGE = (
    "usage: dummyindex context maintain plan|begin|next|done|stamp|status ..."
)

_VERBS = ("plan", "begin", "next", "done", "stamp", "status")


def run(args: list[str]) -> int:
    """`dummyindex context maintain plan|begin|next|done|stamp|status ...`.

    ``-h``/``--help`` is intercepted at the dispatcher (``cli/__init__``), so
    it never reaches here.
    """
    if not args:
        print(f"error: {_MAINTAIN_USAGE}", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    if verb == "plan":
        return _maintain_plan(rest)
    if verb == "begin":
        return _maintain_begin(rest)
    if verb == "next":
        return _maintain_next(rest)
    if verb == "done":
        return _maintain_done(rest)
    if verb == "stamp":
        return _maintain_stamp(rest)
    if verb == "status":
        return _maintain_status(rest)
    print(
        f"error: unknown maintain verb {verb!r} "
        f"(expected plan|begin|next|done|stamp|status)",
        file=sys.stderr,
    )
    return 2


def _maintain_plan(args: list[str]) -> int:
    """`maintain plan [--max-features N] [--json] [--root DIR]` — read-only."""
    from dummyindex.context.build.reconcile import compute_reconcile_report

    values, flags, err = _parse_flags(
        args, value_keys={"max-features", "root"}, bool_keys={"json"}
    )
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain plan`)")
    max_features, err = _pull_max_features(values)
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain plan`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)
    root = context_dir.parent

    report = compute_reconcile_report(context_dir, root)
    work = work_list(report.drifted_features, report.awaiting_enrichment)
    truncated = max_features is not None and len(work) > max_features
    if max_features is not None:
        work = work[:max_features]

    mode = _resolve_mode(context_dir)
    from dummyindex.context.domains.fleet import estimate_run

    estimates = estimate_run(context_dir, tuple(work), mode)

    if "json" in flags:
        print(
            json.dumps(
                {
                    "anchor": report.indexed_commit,
                    "mode": mode,
                    "work": list(estimates["features"]),
                    "unassigned_new_files": list(report.unassigned_new_files),
                    "total_units": estimates["total_units"],
                    "heuristic_seconds": estimates["heuristic_seconds"],
                    "truncated": truncated,
                },
                indent=2,
            )
        )
        return 0

    anchor = report.indexed_commit[:12] if report.indexed_commit else "(none)"
    print(f"context maintain plan: anchor {anchor} mode {mode}")
    if not work:
        print("  in sync — nothing to maintain.")
        return 0
    suffix = " (truncated by --max-features)" if truncated else ""
    print(f"  ordered work list{suffix}:")
    for item in estimates["features"]:
        print(
            f"    {item['feature_id']}: "
            f"estimate: {item['estimate_nodes']} stub node(s) x "
            f"{item['estimate_stages']} stage(s) = {item['estimate_units']} unit(s)"
        )
    print(f"  estimate: total {estimates['total_units']} unit(s)", end="")
    print(
        f" (~{estimates['heuristic_seconds']}s at the labelled "
        f"{90}s/unit heuristic — not a promise)"
    )
    if report.unassigned_new_files:
        print(
            f"  note: {len(report.unassigned_new_files)} unassigned new file(s) "
            "need placement before stamp will pass (not part of the unit list)"
        )
    return 0


def _maintain_begin(args: list[str]) -> int:
    """`maintain begin [--max-features N] [--all] [--json] [--root DIR]`."""
    from dummyindex.context.build.reconcile import compute_reconcile_report

    values, flags, err = _parse_flags(
        args,
        value_keys={"max-features", "root"},
        bool_keys={"json", "all"},
    )
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain begin`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)
    root = context_dir.parent

    report = compute_reconcile_report(context_dir, root)
    full_work = work_list(report.drifted_features, report.awaiting_enrichment)
    if not full_work:
        if "json" in flags:
            print(json.dumps({"created": None, "reason": "in-sync"}))
        else:
            print("context maintain begin: in sync — nothing to maintain.")
        return 0

    max_features, err = _pull_max_features(values)
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain begin`)")
    # Scope guard: an unbounded run must be chosen explicitly — either a
    # truncation limit or a literal --all. Never both silently defaulted.
    if max_features is None and "all" not in flags:
        print(
            "error: `maintain begin` would start every maintenance unit in "
            "this repo. Pass --max-features N to scope the run, or --all to "
            "confirm the whole work list "
            f"({len(full_work)} feature(s)).",
            file=sys.stderr,
        )
        return 2
    work = full_work if max_features is None else full_work[:max_features]
    truncated = len(work) < len(full_work)

    mode = _resolve_mode(context_dir)
    from dummyindex.context.domains.fleet import create_run, estimate_run

    estimates = estimate_run(context_dir, tuple(work), mode)
    stages = tuple(estimates["stages"])
    stage_map = {fid: stages for fid in work}
    node_counts = {
        item["feature_id"]: item["estimate_nodes"] for item in estimates["features"]
    }
    run = create_run(
        context_dir,
        tuple(work),
        node_counts,
        mode=mode,
        anchor_sha=_read_anchor(context_dir),
        stages_for_feature=stage_map,
    )

    if "json" in flags:
        from dummyindex.context.domains.fleet import run_status

        payload = run_status(run)
        payload.update({"created": True, "truncated": truncated})
        print(json.dumps(payload, indent=2))
        return 0

    print(f"context maintain begin: {run.run_dir}")
    print(
        f"  {len(work)} feature(s), estimate: {estimates['total_units']} unit(s) "
        "(~"
        f"{estimates['heuristic_seconds']}s heuristic — not a promise)"
    )
    if truncated:
        print(
            f"  scoped by --max-features {len(work)} of {len(full_work)} — "
            "re-run later for the remainder."
        )
    print("  drive it with `maintain next`; resume any time from state.json.")
    return 0


def _maintain_next(args: list[str]) -> int:
    """`maintain next [--run NAME] [--json] [--root DIR]` — the frontier."""
    values, flags, err = _parse_flags(
        args, value_keys={"run", "root"}, bool_keys={"json"}
    )
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain next`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    run, err = _load_run(context_dir, values.get("run"))
    if err is not None:
        return _fleet_error(err)

    from dummyindex.context.domains.fleet import next_unit, run_status

    counts = run_status(run)
    unit = next_unit(run)
    if "json" in flags:
        print(
            json.dumps(
                {
                    "run": run.run_dir.name,
                    "complete": counts["complete"],
                    "unit": None
                    if unit is None
                    else {
                        "feature_id": unit.feature_id,
                        "stage": unit.stage,
                        "name": unit.name,
                    },
                    "counts": {
                        k: counts[k] for k in ("total", "done", "pending", "skipped")
                    },
                },
                indent=2,
            )
        )
        return 0

    if unit is None:
        print(
            f"maintain next [{run.run_dir.name}]: complete — all units done. "
            "Stamp each finished feature (`maintain stamp --feature ID`), then "
            "commit the re-anchor as `chore(context): re-anchor`."
        )
        return 0
    print(
        f"maintain next [{run.run_dir.name}]: {unit.feature_id}/stage "
        f"{unit.stage} ({unit.name})"
    )
    print(
        f"  {counts['pending']} pending of {counts['total']} "
        f"({counts['done']} done, {counts['skipped']} skipped)"
    )
    return 0


def _maintain_done(args: list[str]) -> int:
    """`maintain done --feature ID [--stage N] [--run NAME] [--root DIR]`."""
    values, flags, err = _parse_flags(
        args, value_keys={"feature", "stage", "run", "root"}, bool_keys=set()
    )
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain done`)")
    feature_id = values.get("feature")
    if not feature_id:
        return usage_error("maintain", "--feature ID is required (for `maintain done`)")
    stage, err = _pull_stage(values)
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain done`)")
    _ = flags  # none yet; kept for symmetry

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    run, err = _load_run(context_dir, values.get("run"))
    if err is not None:
        return _fleet_error(err)

    from dummyindex.context.domains.fleet import UnitStatus, mark_done, next_unit

    target_stage = stage
    if target_stage is None:
        pending = [
            u.stage
            for u in run.units
            if u.feature_id == feature_id and u.status is UnitStatus.PENDING
        ]
        if not pending:
            print(
                f"error: {feature_id} has no pending unit in {run.run_dir.name}",
                file=sys.stderr,
            )
            return 1
        target_stage = min(pending)

    try:
        updated = mark_done(run, feature_id, target_stage)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    frontier = next_unit(updated)
    print(
        f"maintain done [{updated.run_dir.name}]: {feature_id}/stage "
        f"{target_stage} marked done"
    )
    if frontier is not None:
        print(
            f"  next up: {frontier.feature_id}/stage {frontier.stage} ({frontier.name})"
        )
    else:
        print("  run complete — stamp finished features, then re-anchor.")
    return 0


def _maintain_stamp(args: list[str]) -> int:
    """`maintain stamp --feature ID [...]` — reconcile-stamp + tick the state."""
    from .reconcile import run_stamp

    values, flags, err = _parse_flags(
        args,
        value_keys={"feature", "run", "to", "root"},
        bool_keys={"force", "heal-orphaned"},
    )
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain stamp`)")
    feature_id = values.get("feature")
    if not feature_id:
        return usage_error(
            "maintain", "--feature ID is required (for `maintain stamp`)"
        )

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    run, err = _load_run(context_dir, values.get("run"))
    if err is not None:
        return _fleet_error(err)

    stamp_args: list[str] = ["--root", str(context_dir.parent)]
    if "force" in flags:
        stamp_args.append("--force")
    if "heal-orphaned" in flags:
        stamp_args.append("--heal-orphaned")
    if values.get("to"):
        stamp_args.extend(["--to", values["to"]])
    rc = run_stamp(stamp_args)
    if rc != 0:
        # A refused/failed stamp advances nothing — leave the run state alone.
        return rc

    from dummyindex.context.domains.fleet import UnitStatus, load_run, mark_done

    fresh = load_run(run.run_dir)
    ticked = 0
    for unit in fresh.units:
        if unit.feature_id == feature_id and unit.status is not UnitStatus.DONE:
            fresh = mark_done(fresh, feature_id, unit.stage, status=UnitStatus.DONE)
            ticked += 1
    print(
        f"context maintain stamp: {feature_id} reconciled — {ticked} unit(s) "
        f"ticked done in {fresh.run_dir.name}"
    )
    return 0


def _maintain_status(args: list[str]) -> int:
    """`maintain status [--run NAME] [--json] [--root DIR]`."""
    values, flags, err = _parse_flags(
        args, value_keys={"run", "root"}, bool_keys={"json"}
    )
    if err is not None:
        return usage_error("maintain", f"{err} (for `maintain status`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    run, err = _load_run(context_dir, values.get("run"))
    if err is not None:
        return _fleet_error(err)

    from dummyindex.context.domains.fleet import run_status

    counts = run_status(run)
    if "json" in flags:
        print(json.dumps(counts, indent=2))
        return 0

    elapsed = counts["elapsed_seconds"]
    elapsed_str = "unknown" if elapsed is None else f"{elapsed}s"
    remaining = counts["estimated_remaining_seconds_heuristic"]
    print(f"context maintain status [{run.run_dir.name}]")
    print(
        f"  {counts['done']}/{counts['total']} done, {counts['pending']} pending, "
        f"{counts['skipped']} skipped — elapsed {elapsed_str}"
    )
    print(
        f"  estimate: ~{remaining}s remaining at the labelled {90}s/unit "
        "heuristic — not a promise"
    )
    print(f"  anchor: {counts['anchor_sha'] or '(none)'} mode {counts['mode']}")
    return 0


# ----- helpers ---------------------------------------------------------------


def work_list(drifted: tuple[str, ...], awaiting: tuple[str, ...]) -> list[str]:
    """The execution order: drifted first, then awaiting-enrichment, deduped.

    Unassigned new files are deliberately absent — they need a placement
    decision (council work), not a per-feature recouncil unit.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for fid in (*drifted, *awaiting):
        if fid not in seen:
            seen.add(fid)
            ordered.append(fid)
    return ordered


def _resolve_mode(context_dir: Path) -> str:
    """The council depth for the recouncil units (config mode, default std)."""
    from dummyindex.context.domains.config import CouncilMode, read_config

    try:
        config = read_config(context_dir)
    except Exception:
        config = None
    if config is None:
        return CouncilMode.STANDARD.value
    return config.mode.value


def _read_anchor(context_dir: Path) -> str | None:
    """The recorded reconcile anchor from meta.json, tolerant (None if absent)."""
    path = context_dir / "meta.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(raw, dict):
        anchor = raw.get("indexed_commit")
        if isinstance(anchor, str) and anchor:
            return anchor
    return None


def _load_run(context_dir: Path, explicit: str | None):
    """Resolve + load the run; returns ``(run, error_message)``."""
    from dummyindex.context.domains.fleet import (
        FleetRunError,
        load_run,
        resolve_run_dir,
    )

    try:
        run_dir = resolve_run_dir(context_dir, explicit)
    except FleetRunError as exc:
        return None, str(exc)
    if run_dir is None:
        return None, (
            f"no maintain-* run found under {runs_root_display(context_dir)} — "
            "start one with `context maintain begin`"
        )
    try:
        return load_run(run_dir), None
    except FleetRunError as exc:
        return None, str(exc)


def runs_root_display(context_dir: Path) -> str:
    return str(context_dir / "fleet")


def _fleet_error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def _pull_max_features(values: dict[str, str]) -> tuple[int | None, str | None]:
    raw = values.get("max-features")
    if raw is None:
        return None, None
    try:
        n = int(raw)
    except ValueError:
        return None, "--max-features must be an integer"
    if n < 1:
        return None, "--max-features must be >= 1"
    return n, None


def _pull_stage(values: dict[str, str]) -> tuple[int | None, str | None]:
    raw = values.get("stage")
    if raw is None:
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, "--stage must be an integer"


def _context_dir(root: str | None) -> tuple[Path, bool]:
    """Resolve the ``.context/`` dir + whether it is missing (gc precedent)."""
    explicit_root = Path(root) if root else None
    out_root = resolve_context_root(Path("."), explicit_root=explicit_root)
    context_dir = out_root / ".context"
    return context_dir, not context_dir.is_dir()


def _missing_context(context_dir: Path) -> int:
    print(
        f"error: {context_dir} not found. Run `dummyindex ingest` first.",
        file=sys.stderr,
    )
    return 2


def _parse_flags(
    args: list[str],
    *,
    value_keys: set[str],
    bool_keys: set[str],
) -> tuple[dict[str, str], set[str], str | None]:
    """Parse ``--key value`` / ``--key=value`` / ``--flag`` arguments.

    The same trimmed parser as ``cli/gc.py:_parse_flags`` (no repeatable
    flags). Returns ``(values, flags, error)``; boolean flag names keep their
    dashes so callers membership-test on the raw key.
    """
    values: dict[str, str] = {}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return values, flags, f"unexpected argument: {token!r}"
        if "=" in token:
            name, inline_value = token[2:].split("=", 1)
            has_inline = True
        else:
            name, inline_value = token[2:], None
            has_inline = False

        if name in bool_keys:
            if has_inline:
                return values, flags, f"--{name} takes no value"
            flags.add(name)
            i += 1
            continue

        if name in value_keys:
            if has_inline:
                values[name] = inline_value or ""
                i += 1
            else:
                if i + 1 >= len(args):
                    return values, flags, f"--{name} requires a value"
                values[name] = args[i + 1]
                i += 2
            continue

        return values, flags, f"unknown argument: --{name}"
    return values, flags, None
