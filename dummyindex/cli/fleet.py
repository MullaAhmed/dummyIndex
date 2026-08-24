"""`dummyindex context fleet <verb>` — the fleet-run CLI (wire-only).

Sub-dispatches the first positional verb (`init|next|checkpoint|spend|
merge-order|status`) the same way `cli/gc.py` dispatches
`status|delete|stamp|signal`: parse this command's own flag alphabet,
lazy-import the `context.domains.fleetrun` domain *inside* each verb (the
layering rule — `cli` imports the domain, never the reverse), call a domain
function, print, and return an exit code. No business logic lives here;
run state, disjointness, gating, and the budget breaker all sit in the
domain over the committed artifacts (`RUN-MANIFEST.md` + `state.json`
under `.context/fleet/run-<id>/`).

The six verbs:

- `init --plans SLUG[,SLUG…] | --intake FILE --budget-usd N --max-parallel N
  [--branch-template TPL] [--ruling K=V]... [--root DIR]` — scaffold the run
  dir; prints the priority order + any conservative-serial warnings.
- `next [--run DIR] [--json] [--root DIR]` — the dispatch frontier. Always
  exit 0 for a valid envelope: an empty-but-valid `ok` envelope (everything
  gated/blocked) is the anti-stall guarantee, and at/over budget cap the
  response is a BUDGET-HALT envelope (`"halt": true` under `--json`)
  carrying exact resume steps — never a crash, never a nonzero exit.
- `checkpoint --unit ID [--status ST] [--wave N] [--gate Q] [--note ...]
  [--run DIR]` — advance one unit; `--gate` parks it as `gated` (skipped by
  `next` until answered via a later `--status` checkpoint).
- `spend --unit ID --est-usd X [--adjust] [--run DIR]` — accumulate the
  breaker meter; negative deltas require `--adjust` (the documented resume
  path after a BUDGET-HALT).
- `merge-order [--run DIR] [--json]` — projected landing order with
  disjointness rationale.
- `status [--run DIR] [--json]` — read-only run summary (units, statuses,
  meter, gates).

Default run discovery is prefix-scoped to the newest `run-*` dir; pass
`--run DIR` to target another one explicitly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import resolve_context_root, usage_error

_FLEET_USAGE = (
    "usage: dummyindex context fleet init|next|checkpoint|spend|merge-order|status ..."
)

_VERBS = ("init", "next", "checkpoint", "spend", "merge-order", "status")


def run(args: list[str]) -> int:
    """`dummyindex context fleet init|next|checkpoint|spend|merge-order|status ...`.

    `-h`/`--help` is intercepted at the dispatcher (`cli/__init__`), so it
    never reaches here.
    """
    if not args:
        print(f"error: {_FLEET_USAGE}", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    if verb == "init":
        return _fleet_init(rest)
    if verb == "next":
        return _fleet_next(rest)
    if verb == "checkpoint":
        return _fleet_checkpoint(rest)
    if verb == "spend":
        return _fleet_spend(rest)
    if verb == "merge-order":
        return _fleet_merge_order(rest)
    if verb == "status":
        return _fleet_status(rest)
    print(
        f"error: unknown fleet verb {verb!r} (expected {'|'.join(_VERBS)})",
        file=sys.stderr,
    )
    return 2


def _fleet_init(args: list[str]) -> int:
    """`fleet init (--plans | --intake) --budget-usd N --max-parallel N [...]`.

    Scaffolds `.context/fleet/run-<id>/` (manifest first, state last) and
    prints the minted run id, the priority order, and any warnings. Refusals
    (zero units, duplicate slugs, bad flags) exit 2.
    """
    from dummyindex.context.domains.fleetrun import (
        FleetError,
        init_run,
        units_from_intake,
        units_from_plans,
    )

    values, ruling_pairs, _flags, err = _parse_flags(
        args,
        value_keys={
            "plans",
            "intake",
            "budget-usd",
            "max-parallel",
            "branch-template",
            "root",
        },
        repeat_keys={"ruling"},
        bool_keys=set(),
    )
    if err is not None:
        return usage_error("fleet", f"{err} (for `fleet init`)")
    rulings: list[tuple[str, str]] = []
    for _name, raw in ruling_pairs:
        if "=" not in raw:
            return usage_error(
                "fleet", f"--ruling must be KEY=VALUE, got {raw!r} (for `fleet init`)"
            )
        key, val = raw.split("=", 1)
        rulings.append((key.strip(), val.strip()))

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    plans = values.get("plans")
    intake = values.get("intake")
    if bool(plans) == bool(intake):
        return usage_error(
            "fleet",
            "exactly one of --plans SLUG[,SLUG...] / --intake FILE is required "
            "(for `fleet init`)",
        )

    budget = _parse_float(values.get("budget-usd"))
    if budget is None:
        return usage_error("fleet", "--budget-usd must be a number (for `fleet init`)")
    max_parallel = _parse_int(values.get("max-parallel"))
    if max_parallel is None:
        return usage_error(
            "fleet", "--max-parallel must be an integer (for `fleet init`)"
        )

    if plans is not None:
        slugs = [s.strip() for s in plans.split(",") if s.strip()]
        specs, warnings = units_from_plans(context_dir, slugs)
    else:
        try:
            payload = json.loads(Path(intake).read_text(encoding="utf-8"))
        except OSError as exc:
            return usage_error("fleet", f"--intake {intake}: {exc} (for `fleet init`)")
        except json.JSONDecodeError as exc:
            return usage_error(
                "fleet", f"--intake {intake}: invalid JSON ({exc}) (for `fleet init`)"
            )
        specs = units_from_intake(payload)
        warnings = []

    try:
        state, init_warnings = init_run(
            context_dir,
            specs,
            budget_usd=budget,
            max_parallel=max_parallel,
            branch_template=values.get("branch-template", "{run}/{id}-{slug}"),
            rulings=rulings,
        )
    except FleetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    warnings += init_warnings
    print(f"context fleet init: run-{state.run_id} ({len(state.units)} units)")
    for i, unit in enumerate(state.units):
        print(f"  #{i + 1} {unit.id} {unit.slug} -> {unit.branch}")
    for w in warnings:
        print(f"  warning: {w}")
    from dummyindex.context.domains.fleetrun import fleet_root

    print(f"  manifest: {fleet_root(context_dir) / f'run-{state.run_id}'}")
    return 0


def _resolve_run(values: dict[str, str]) -> tuple[Path | None, int | None]:
    """Target run dir for a verb: explicit ``--run DIR`` wins, else the
    newest ``run-*`` dir under ``--root``'s ``.context/fleet/``.

    Returns ``(run_dir, None)`` or ``(None, exit_code)`` — discovery failure
    prints the domain's loud repair note and maps to exit 1 (a runtime
    failure, not a usage error); a missing ``.context/`` maps to exit 2.
    """
    from dummyindex.context.domains.fleetrun import (
        FleetStateCorruptError,
        resolve_run_dir,
    )

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return None, _missing_context(context_dir)
    if values.get("run"):
        return Path(values["run"]), None
    try:
        return resolve_run_dir(context_dir), None
    except FleetStateCorruptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None, 1


def _fleet_next(args: list[str]) -> int:
    """`fleet next [--run DIR] [--json] [--root DIR]` — dispatch frontier.

    Always exit 0 for a valid envelope: BUDGET-HALT and empty-but-valid ok
    envelopes are outcomes, not failures (the anti-stall rule).
    """
    from dummyindex.context.domains.fleetrun import load_run, next_units

    values, _repeats, flags, err = _parse_flags(
        args, value_keys={"run", "root"}, repeat_keys=set(), bool_keys={"json"}
    )
    if err is not None:
        return usage_error("fleet", f"{err} (for `fleet next`)")
    run_dir, code = _resolve_run(values)
    if run_dir is None:
        assert code is not None
        return code

    envelope = next_units(load_run(run_dir))
    halted = envelope.status == "BUDGET-HALT"
    payload = {"halt": halted, **envelope.to_dict()}
    if "json" in flags:
        print(json.dumps(payload, indent=2))
        return 0
    if halted:
        print(f"BUDGET-HALT — run {envelope.run_id}: no units will dispatch.")
        for line in envelope.resume:
            print(line)
        return 0
    print(
        f"context fleet next: run {envelope.run_id} — "
        f"{len(envelope.units)} unit(s) to dispatch"
    )
    for unit in envelope.units:
        print(f"  DISPATCH {unit.id} {unit.slug} -> {unit.branch}")
    for unit_id, reason in envelope.skipped:
        print(f"  skip {unit_id}: {reason}")
    if not envelope.units and not envelope.skipped:
        print("  (nothing left to dispatch)")
    return 0


def _fleet_checkpoint(args: list[str]) -> int:
    """`fleet checkpoint --unit ID [--status ST] [--wave N] [--gate Q]
    [--note ...] [--run DIR] [--root DIR]`."""
    from dummyindex.context.domains.fleetrun import FleetError, checkpoint

    values, _repeats, _flags, err = _parse_flags(
        args,
        value_keys={"unit", "status", "wave", "gate", "note", "run", "root"},
        repeat_keys=set(),
        bool_keys=set(),
    )
    if err is not None:
        return usage_error("fleet", f"{err} (for `fleet checkpoint`)")
    if not values.get("unit"):
        return usage_error("fleet", "--unit ID is required (for `fleet checkpoint`)")
    wave = None
    if values.get("wave") is not None:
        wave = _parse_int(values["wave"])
        if wave is None:
            return usage_error(
                "fleet", "--wave must be an integer (for `fleet checkpoint`)"
            )

    run_dir, code = _resolve_run(values)
    if run_dir is None:
        assert code is not None
        return code

    try:
        state = checkpoint(
            run_dir,
            values["unit"],
            status=values.get("status"),
            wave=wave,
            gate=values.get("gate"),
            note=values.get("note"),
        )
    except FleetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    unit = state.unit(values["unit"])
    gate = f' gate="{unit.gate_question}"' if unit.gate_question else ""
    print(f"context fleet checkpoint: {unit.id} status={unit.status}{gate}")
    return 0


def _fleet_spend(args: list[str]) -> int:
    """`fleet spend --unit ID --est-usd X [--adjust] [--run DIR] [--root DIR]`.

    Negative deltas require `--adjust` — the documented resume path after a
    BUDGET-HALT. Crossing the cap here is reported but still exits 0; the
    breaker itself trips on the next `next`.
    """
    from dummyindex.context.domains.fleetrun import FleetError, add_spend

    values, _repeats, flags, err = _parse_flags(
        args,
        value_keys={"unit", "est-usd", "run", "root"},
        repeat_keys=set(),
        bool_keys={"adjust"},
    )
    if err is not None:
        return usage_error("fleet", f"{err} (for `fleet spend`)")
    if not values.get("unit"):
        return usage_error("fleet", "--unit ID is required (for `fleet spend`)")
    amount = _parse_float(values.get("est-usd"))
    if amount is None:
        return usage_error("fleet", "--est-usd must be a number (for `fleet spend`)")

    run_dir, code = _resolve_run(values)
    if run_dir is None:
        assert code is not None
        return code

    try:
        state = add_spend(run_dir, values["unit"], amount, adjust="adjust" in flags)
    except FleetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    meter = state.budget
    pct = (
        f" ({meter.spent_est_usd / meter.cap_usd:.0%} of cap)"
        if meter.cap_usd > 0
        else ""
    )
    print(
        f"context fleet spend: {values['unit']} {amount:+g} -> "
        f"${meter.spent_est_usd:.2f}/${meter.cap_usd:.2f}{pct}"
    )
    if meter.spent_est_usd >= meter.cap_usd:
        print("  BUDGET-HALT reached — `fleet next` will halt until --adjust.")
    return 0


def _fleet_merge_order(args: list[str]) -> int:
    """`fleet merge-order [--run DIR] [--json] [--root DIR]`."""
    from dummyindex.context.domains.fleetrun import load_run, merge_order

    values, _repeats, flags, err = _parse_flags(
        args, value_keys={"run", "root"}, repeat_keys=set(), bool_keys={"json"}
    )
    if err is not None:
        return usage_error("fleet", f"{err} (for `fleet merge-order`)")
    run_dir, code = _resolve_run(values)
    if run_dir is None:
        assert code is not None
        return code

    state = load_run(run_dir)
    entries = merge_order(state)
    if "json" in flags:
        print(
            json.dumps(
                {
                    "run": state.run_id,
                    "order": [
                        {
                            "position": e.position,
                            "id": e.unit.id,
                            "slug": e.unit.slug,
                            "status": e.unit.status,
                            "landed": e.landed,
                            "reason": e.reason,
                        }
                        for e in entries
                    ],
                },
                indent=2,
            )
        )
        return 0
    print(f"context fleet merge-order: run {state.run_id}")
    for e in entries:
        mark = "landed" if e.landed else "plan"
        print(f"  {e.position}. [{mark}] {e.unit.id} {e.unit.slug} — {e.reason}")
    return 0


def _fleet_status(args: list[str]) -> int:
    """`fleet status [--run DIR] [--json] [--root DIR]` — read-only summary."""
    from dummyindex.context.domains.fleetrun import budget_halted, load_run

    values, _repeats, flags, err = _parse_flags(
        args, value_keys={"run", "root"}, repeat_keys=set(), bool_keys={"json"}
    )
    if err is not None:
        return usage_error("fleet", f"{err} (for `fleet status`)")
    run_dir, code = _resolve_run(values)
    if run_dir is None:
        assert code is not None
        return code

    state = load_run(run_dir)
    halted = budget_halted(state)
    if "json" in flags:
        print(
            json.dumps(
                {
                    "halt": halted,
                    "run": state.run_id,
                    "created": state.created,
                    "revision": state.revision,
                    "max_parallel": state.max_parallel,
                    "branch_template": state.branch_template,
                    "budget": {
                        "cap_usd": state.budget.cap_usd,
                        "spent_est_usd": state.budget.spent_est_usd,
                        "halt": halted,
                    },
                    "units": [_unit_payload(u) for u in state.units],
                },
                indent=2,
            )
        )
        return 0
    print(
        f"context fleet status: run {state.run_id} "
        f"(rev {state.revision}, max_parallel={state.max_parallel})"
    )
    print(f"  created: {state.created or '(unset)'}")
    print(
        f"  budget: ${state.budget.spent_est_usd:.2f} of "
        f"${state.budget.cap_usd:.2f}" + (" — BUDGET-HALT" if halted else "")
    )
    for unit in state.units:
        gate = f" [gated: {unit.gate_question}]" if unit.gate_question else ""
        print(
            f"  {unit.id} {unit.slug:<24} {unit.status:<9}"
            f" ${unit.spend_est_usd:.2f}{gate}"
        )
    return 0


# ----- helpers --------------------------------------------------------------


def _unit_payload(unit: object) -> dict:
    """One row of `fleet status --json`'s units array."""
    return {
        "id": unit.id,  # type: ignore[attr-defined]
        "slug": unit.slug,  # type: ignore[attr-defined]
        "branch": unit.branch,  # type: ignore[attr-defined]
        "status": unit.status,  # type: ignore[attr-defined]
        "paths": list(unit.paths),  # type: ignore[attr-defined]
        "revision": unit.revision,  # type: ignore[attr-defined]
        "spend_est_usd": unit.spend_est_usd,  # type: ignore[attr-defined]
        "wave": unit.wave,  # type: ignore[attr-defined]
        "gate_question": unit.gate_question,  # type: ignore[attr-defined]
    }


def _context_dir(root: str | None) -> tuple[Path, bool]:
    """Resolve the ``.context/`` dir + whether it is missing (gc precedent)."""
    explicit_root = Path(root) if root else None
    out_root = resolve_context_root(Path("."), explicit_root=explicit_root)
    context_dir = out_root / ".context"
    return context_dir, not context_dir.is_dir()


def _missing_context(context_dir: Path) -> int:
    """Print the standard missing-`.context/` error and return exit 2."""
    print(
        f"error: {context_dir} not found. Run `dummyindex ingest` first.",
        file=sys.stderr,
    )
    return 2


def _parse_float(raw: str | None) -> float | None:
    """Parse a float flag value; ``None`` on absent/malformed input."""
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_int(raw: str | None) -> int | None:
    """Parse an int flag value; ``None`` on absent/malformed input."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_flags(
    args: list[str],
    *,
    value_keys: set[str],
    repeat_keys: set[str],
    bool_keys: set[str],
) -> tuple[dict[str, str], list[tuple[str, str]], set[str], str | None]:
    """Parse ``--key value`` / ``--key=value`` / ``--flag`` arguments.

    A repeatable-flag cousin of ``cli/gc.py:_parse_flags`` (fleet's only
    repeatable is ``--ruling KEY=VALUE``). Returns ``(values, repeats,
    flags, error)``; ``error`` is a message on a malformed / unknown
    argument, else None. Boolean and repeated names keep their dashes.
    """
    values: dict[str, str] = {}
    repeats: list[tuple[str, str]] = []
    flags: set[str] = set()
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return values, repeats, flags, f"unexpected argument: {token!r}"
        if "=" in token:
            name, inline_value = token[2:].split("=", 1)
            has_inline = True
        else:
            name, inline_value = token[2:], None
            has_inline = False

        if name in bool_keys:
            if has_inline:
                return values, repeats, flags, f"--{name} takes no value"
            flags.add(name)
            i += 1
            continue

        if name in repeat_keys:
            if inline_value is not None:
                repeats.append((name, inline_value))
                i += 1
            elif i + 1 < len(args):
                repeats.append((name, args[i + 1]))
                i += 2
            else:
                return values, repeats, flags, f"--{name} requires a value"
            continue

        if name in value_keys:
            if has_inline:
                values[name] = inline_value or ""
                i += 1
            else:
                if i + 1 >= len(args):
                    return values, repeats, flags, f"--{name} requires a value"
                values[name] = args[i + 1]
                i += 2
            continue

        return values, repeats, flags, f"unknown argument: --{name}"
    return values, repeats, flags, None
