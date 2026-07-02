"""``equip eval`` / ``equip benchmark`` — the I/O boundary for the eval stage.

Wire-only: this is the single place the eval stage touches the filesystem and
``json``. It parses flags, sanitizes the attacker-controllable ``<tool>`` name
(vendored skill names come from an external ``SKILL.md``), resolves paths under
:data:`EVALS_REL` (``.context/equipment-evals/``), reads + ``json.loads`` the
suite and observation files, calls the **pure** eval domain
(:mod:`dummyindex.context.domains.equip.eval` — ``score_run`` /
``aggregate_benchmark`` and the parse/serialize helpers), and writes results via
:func:`write_text_atomic`. All policy — the confusion matrix, the numeric
conventions, coverage checks, variance — lives in that pure domain; nothing here
scores anything. Trigger judgments arrive only as data (the observations file),
never as an LLM call from code.

Exit codes match the equip family:

- ``2`` — bad flags / missing required arg / unsafe tool name / missing suite /
  a ``--run-label`` collision without ``--force``.
- ``1`` — malformed suite/observations content or a scoring (coverage) error.
- ``0`` — scored (``eval``) or aggregated / nothing-to-do (``benchmark``).

``benchmark`` is a **reporter, not a gate**: a missing evals dir or zero run
files is a stderr warning + exit ``0`` that writes nothing; only a malformed run
file (which would silently deflate variance) fails loud with exit ``1``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.equip import EVALS_REL
from dummyindex.context.domains.equip.eval import (
    EvalError,
    EvalSuiteNotFoundError,
    aggregate_benchmark,
    benchmark_to_dict,
    parse_eval_suite,
    parse_observations,
    result_from_dict,
    result_to_dict,
    score_run,
)

from .common import (
    pull_bool_flag,
    pull_flag_value,
    pull_root_then_positional,
    safe_tool_name,
)


def run_eval(rest: list[str]) -> int:
    """``equip eval <tool> --observations FILE [--suite FILE] [--run-label L] ...``.

    Reads the suite (default ``<tool>.suite.json``) + the observations file,
    calls the pure ``score_run``, writes ``<tool>.result.json`` (or
    ``<tool>.run-<L>.result.json``), and prints accuracy + each misfire's
    ``case_id`` + ``EvalOutcome``. See the module docstring for exit codes.
    """
    # Pull every flag first so the tool name is the only bare positional left.
    observations, rest = pull_flag_value(rest, "observations")
    suite, rest = pull_flag_value(rest, "suite")
    run_label, rest = pull_flag_value(rest, "run-label")
    force, rest = pull_bool_flag(rest, "force")
    as_json, rest = pull_bool_flag(rest, "json")
    project_root, (tool, leftover) = pull_root_then_positional(rest)

    if tool is None:
        print("error: `equip eval` requires a TOOL name", file=sys.stderr)
        return 2
    if leftover:
        print(f"error: unknown argument(s): {' '.join(leftover)}", file=sys.stderr)
        return 2
    if observations is None:
        print("error: `equip eval` requires --observations FILE", file=sys.stderr)
        return 2

    try:
        safe_tool = safe_tool_name(tool)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    evals_dir = project_root / ".context" / EVALS_REL
    suite_path = Path(suite) if suite else evals_dir / f"{safe_tool}.suite.json"
    result_path = (
        evals_dir / f"{safe_tool}.run-{run_label}.result.json"
        if run_label
        else evals_dir / f"{safe_tool}.result.json"
    )

    # Run-label collision guard — a silent overwrite would deflate benchmark
    # variance, so reject a re-used label unless --force. Checked before any work.
    if run_label and result_path.exists() and not force:
        print(
            f"error: {result_path} already exists; pass --force to overwrite "
            "(a silent overwrite would deflate benchmark variance)",
            file=sys.stderr,
        )
        return 2

    try:
        if not suite_path.is_file():
            raise EvalSuiteNotFoundError(f"no eval suite at {suite_path}")
        cases = parse_eval_suite(json.loads(suite_path.read_text(encoding="utf-8")))
        obs = parse_observations(
            json.loads(Path(observations).read_text(encoding="utf-8"))
        )
        result = score_run(cases, obs, tool_name=safe_tool)
    except EvalSuiteNotFoundError as exc:
        # An EvalError subclass, but a MISSING suite is a bad-input (exit 2)
        # condition, not malformed content — listed first so it wins the except.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (EvalError, OSError, json.JSONDecodeError) as exc:
        # Malformed suite/observations content (EvalSuiteError/ObservationsError)
        # or a scoring/coverage error (ObservationMismatchError/
        # MissingObservationError) — all map to exit 1.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_text_atomic(result_path, json.dumps(result_to_dict(result), indent=2) + "\n")

    if as_json:
        print(json.dumps(result_to_dict(result), indent=2))
        return 0

    print(
        f"equip eval: {safe_tool} — accuracy {result.accuracy:.3f} "
        f"precision {result.precision:.3f} recall {result.recall:.3f} "
        f"-> {result_path}"
    )
    # Look each misfire's outcome up from the recorded (case_id, outcome) pairs —
    # do NOT re-derive it (the pure scorer is the single source of truth).
    outcome_by_id = dict(result.cases)
    for misfire in result.misfires:
        print(f"  misfire {misfire.case_id}: {outcome_by_id[misfire.case_id].value}")
    return 0


def run_benchmark(rest: list[str]) -> int:
    """``equip benchmark <tool> [--root DIR] [--json]`` — aggregate run files.

    A **reporter, not a gate**: globs ``<tool>.run-*.result.json`` (excluding the
    ``.tmp`` files :func:`write_text_atomic` leaves mid-write), aggregates them
    via the pure ``aggregate_benchmark``, and writes ``<tool>.benchmark.json``.
    A missing dir or zero run files is a warning + exit ``0`` that writes nothing;
    a malformed run file fails loud (exit ``1``) — never silently skipped, which
    would deflate variance.
    """
    as_json, rest = pull_bool_flag(rest, "json")
    project_root, (tool, leftover) = pull_root_then_positional(rest)

    if tool is None:
        print("error: `equip benchmark` requires a TOOL name", file=sys.stderr)
        return 2
    if leftover:
        print(f"error: unknown argument(s): {' '.join(leftover)}", file=sys.stderr)
        return 2

    try:
        safe_tool = safe_tool_name(tool)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    evals_dir = project_root / ".context" / EVALS_REL

    # Fail-open: a missing evals dir is treated as "no runs to benchmark".
    if not evals_dir.is_dir():
        print(
            f"warning: no evals dir at {evals_dir} — nothing to benchmark "
            "(run `equip eval --run-label` first)",
            file=sys.stderr,
        )
        return 0

    run_files = sorted(
        p
        for p in evals_dir.glob(f"{safe_tool}.run-*.result.json")
        if not p.name.endswith(".tmp")
    )

    # Fail-open: zero labelled runs. Distinguish "only unlabelled results" (the
    # user forgot --run-label) from "nothing at all" so the warning is actionable.
    if not run_files:
        if (evals_dir / f"{safe_tool}.result.json").is_file():
            print(
                f"warning: {safe_tool} has only unlabelled results — re-run "
                "`equip eval --run-label` to build a benchmark",
                file=sys.stderr,
            )
        else:
            print(
                f"warning: no run files for {safe_tool} in {evals_dir} "
                "(run `equip eval --run-label` first)",
                file=sys.stderr,
            )
        return 0

    try:
        results = tuple(
            result_from_dict(json.loads(p.read_text(encoding="utf-8")))
            for p in run_files
        )
        report = aggregate_benchmark(results)
    except (EvalError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    benchmark_path = evals_dir / f"{safe_tool}.benchmark.json"
    write_text_atomic(
        benchmark_path, json.dumps(benchmark_to_dict(report), indent=2) + "\n"
    )

    if as_json:
        print(json.dumps(benchmark_to_dict(report), indent=2))
        return 0

    flaky = ", ".join(report.flaky_case_ids) if report.flaky_case_ids else "none"
    print(
        f"equip benchmark: {safe_tool} — {len(report.runs)} run(s), "
        f"mean_accuracy {report.mean_accuracy:.3f} "
        f"variance {report.accuracy_variance:.6f} flaky [{flaky}] "
        f"-> {benchmark_path}"
    )
    return 0
