"""``python -m benchmarks`` — plan, run, and report.

Subcommands
-----------
``plan``
    Print the full planned matrix (suites x arms x tasks x repeats) with a
    sample invocation. Free; always allowed.
``run-repoqa``
    RepoQA SNF cells. Without ``--execute`` this is a dry-run planner that
    prints every planned argv. With ``--execute`` AND
    ``DUMMYINDEX_BENCH_ALLOW_PAY=1`` it actually spends tokens.
``run-swebench``
    SWE-bench Lite cells; same gating. Extracts model patches after each
    executed cell and writes the predictions JSONL for the official harness.
``grade-swebench``
    Invoke ``scoring/swegrade.sh`` on a predictions JSONL (docker required).
``report``
    Aggregate existing JSONL logs into REPORT.md; never spends anything.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # noqa: S404 - fixed-argv wrapper invocations only
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmarks import BENCHMARKS_VERSION, PAY_GATE_ENV
from benchmarks.arms import ARMS, Arm, WorkspaceError
from benchmarks.report import load_rows, render_report, write_report
from benchmarks.runner import (
    PayGateError,
    RunnerConfig,
    RunnerError,
    append_row,
    pay_gate_open,
    run_one_task,
)
from benchmarks.suites import SuiteDataError

RESULTS_DIR = Path("results/benchmarks")


def _print_plan_header(config: RunnerConfig) -> None:
    print(f"model:      {config.model}")
    print(
        "gates:      paid runs need --execute AND "
        f"{PAY_GATE_ENV}=1 (current: {'open' if pay_gate_open() else 'closed'})"
    )
    print("")


def cmd_plan(args: argparse.Namespace) -> int:
    config = _config_from(args)
    _print_plan_header(config)
    sample_prompt = "<suite prompt>"
    sample_ws = Path("<workspace>")
    outcome = run_one_task(
        suite="<suite>",
        arm_value="baseline",
        task_id="<task>",
        repeat_index=0,
        prompt=sample_prompt,
        workspace=sample_ws,
        config=config,
        execute=False,
    )
    print("sample invocation per cell:")
    print("  " + " ".join(outcome.argv))
    print("")
    counts = _matrix_counts(args)
    _print_matrix(counts, args.repeats)
    print("nothing was executed (plan mode).")
    return 0


def _matrix_counts(args: argparse.Namespace) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        from benchmarks.suites.repoqa import (
            load_repoqa_tasks,
            select_subset,
        )

        tasks = load_repoqa_tasks()
        subset = select_subset(
            tasks,
            per_lang_per_repo=args.repoqa_per_cell,
            seed=args.seed,
        )
        counts["repoqa"] = len(subset)
    except Exception as exc:
        print(f"(repoqa planning unavailable: {exc})", file=sys.stderr)
    counts["swebench"] = min(args.swe_size, 300)
    return counts


def _print_matrix(counts: dict[str, int], repeats: int) -> None:
    total_cells = 0
    for suite, n_tasks in sorted(counts.items()):
        if n_tasks < 0:
            continue
        cells = n_tasks * len(ARMS) * repeats
        total_cells += cells
        print(
            f"{suite:<10} tasks={n_tasks:>4} arms={len(ARMS)} "
            f"repeats={repeats} -> {cells} agent runs"
        )
    print(f"\ntotal planned agent runs: {total_cells}")


def _config_from(args: argparse.Namespace) -> RunnerConfig:
    return RunnerConfig(
        model=args.model,
        opencode_bin=args.opencode_bin,
        timeout_s=args.timeout_s,
        results_dir=RESULTS_DIR,
    )


def _done_cells(suite: str) -> set[tuple[str, str, int]]:
    """(arm, task_id, repeat) cells that already produced a final row."""
    done: set[tuple[str, str, int]] = set()
    for row in load_rows(RESULTS_DIR, suite):
        arm = row.get("arm")
        task_id = row.get("task_id")
        repeat = row.get("repeat_index")
        if (
            isinstance(arm, str)
            and isinstance(task_id, str)
            and isinstance(repeat, int)
        ):
            done.add((arm, task_id, repeat))
    return done


def _execute_gate_or_die(execute: bool) -> None:
    if execute and not pay_gate_open():
        raise PayGateError(f"--execute requires {PAY_GATE_ENV}=1 in the environment")


_ROW_LOCK = threading.Lock()


def _resilient_cell(
    suite: str,
    arm_value: str,
    task_label: str,
    repeat: int,
    factory: Callable[[], dict[str, object]],
    *,
    attempts: int = 3,
    backoff_s: float = 20.0,
) -> Callable[[], dict[str, object]]:
    """Wrap one cell so transport failures never kill the sweep.

    A failing cell is retried up to ``attempts`` times (transient opencode
    exits happen); if every attempt fails, an explicit ``error`` row is
    appended so the run log shows the hole instead of pretending the cell
    never existed. PayGateError still propagates — that gate is policy,
    not transport luck.
    """

    def wrapped() -> dict[str, object]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return factory()
            except PayGateError:
                raise
            except (RunnerError, WorkspaceError, OSError) as exc:
                last_error = exc
                print(
                    f"  [retry] {arm_value}/{task_label}/r{repeat} "
                    f"attempt {attempt}/{attempts}: {exc}",
                    flush=True,
                )
                if attempt < attempts:
                    time.sleep(backoff_s)
        row = {
            "suite": suite,
            "arm": arm_value,
            "task_id": task_label,
            "repeat_index": repeat,
            "executed": False,
            "error": str(last_error),
        }
        append_row(row, RESULTS_DIR, suite)
        return row

    return wrapped


def _run_cells(
    cells: Sequence[Callable[[], dict[str, object]]], *, workers: int
) -> list[dict[str, object]]:
    """Execute row-producing cells, sequentially or on a thread pool.

    Cells are independent: distinct workspaces, distinct sessions. JSONL
    appends are serialized by a lock so interleaved workers cannot tear
    lines. With ``workers=1`` this is a plain sequential map in submission
    order.
    """
    rows: list[dict[str, object]] = []

    def _run_one(factory: Callable[[], dict[str, object]]) -> None:
        row = factory()
        with _ROW_LOCK:
            rows.append(row)

    if workers <= 1:
        for factory in cells:
            print(".", end="", flush=True)
            _run_one(factory)
        print()
        return rows

    progress_lock = threading.Lock()
    done = 0

    def _tracked(indexed_factory) -> None:
        nonlocal done
        slot, factory = indexed_factory
        _staggered_start(slot)
        _run_one(factory)
        with progress_lock:
            done += 1
            if done % 10 == 0 or done == len(cells):
                print(f"  ... {done}/{len(cells)} cells done", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_tracked, list(enumerate(cells))))
    return rows


_START_STAGGER_LOCK = threading.Lock()


def _staggered_start(slot: int, delay_s: float = 3.0) -> None:
    """Space out worker cold-starts to avoid simultaneous first-boot storms."""
    with _START_STAGGER_LOCK:
        time.sleep((slot % 8) * delay_s)


def cmd_run_repoqa(args: argparse.Namespace) -> int:
    from benchmarks.scoring.snf import grade_snf
    from benchmarks.scoring.snf_official import grade_snf_official
    from benchmarks.suites import repoqa

    _execute_gate_or_die(args.execute)
    config = _config_from(args)
    records = repoqa.load_repoqa_records()
    tasks = repoqa.tasks_from_records(records)
    subset = repoqa.select_subset(
        tasks, per_lang_per_repo=args.per_cell, seed=args.seed
    )
    if args.limit is not None:
        subset = subset[: args.limit]
    print(
        f"running {len(subset)} SNF tasks x {len(ARMS)} arms x "
        f"r{args.repeats} (protocol={args.protocol}, workers={args.workers})"
    )

    def make_cell(arm_value: str, task: object, repeat: int):
        def cell() -> dict[str, object]:
            arm = Arm(arm_value)
            prepared = (
                repoqa.prepared_for_task(
                    arm,
                    task,
                    workspace_root=RESULTS_DIR / "workspaces",
                    cache_root=RESULTS_DIR / "cache" / "repos",
                    repeat=repeat,
                )
                if args.execute
                else None
            )
            workspace = (
                prepared.path
                if prepared is not None
                else RESULTS_DIR / "workspaces" / "dry-run"
            )
            prompt = repoqa.build_prompt(task, protocol=args.protocol)
            outcome = run_one_task(
                suite="repoqa",
                arm_value=arm.value,
                task_id=task.task_id,
                repeat_index=repeat,
                prompt=prompt,
                workspace=workspace,
                config=config,
                execute=args.execute,
            )
            row = outcome.to_row()
            row["protocol"] = args.protocol
            if prepared is not None:
                row["index_state"] = prepared.index_mode
            if outcome.executed:
                if args.protocol == "name":
                    verdict = grade_snf(outcome.metrics.response_text, task.func)
                    row["passed"] = verdict.passed
                else:
                    official = grade_snf_official(
                        outcome.metrics.response_text,
                        task.func,
                        repoqa.repo_record(records, task.language, task.repo),
                        task.language,
                    )
                    row["passed"] = official.passed_at()
                    row["best_similarity"] = round(official.best_similarity, 4)
            append_row(row, RESULTS_DIR, "repoqa")
            return row

        return cell

    done = _done_cells("repoqa")
    if done:
        print(f"resume: {len(done)} repoqa cells already recorded; skipping them")
    cells: list[Callable[[], dict[str, object]]] = [
        _resilient_cell(
            "repoqa",
            arm_value,
            task.task_id,
            repeat,
            make_cell(arm_value, task, repeat),
        )
        for arm_value in ("baseline", "context")
        for task in subset
        for repeat in range(args.repeats)
        if (arm_value, task.task_id, repeat) not in done
    ]
    graded_rows = _run_cells(cells, workers=args.workers)
    if args.execute:
        path = write_report({"repoqa": graded_rows}, RESULTS_DIR / "REPORT.md")
        print(f"report written: {path}")
    else:
        print(render_report({"repoqa": graded_rows}))
    return 0


def cmd_run_swebench(args: argparse.Namespace) -> int:
    from benchmarks.scoring.swebench_patch import extract_model_patch
    from benchmarks.suites import swebench

    _execute_gate_or_die(args.execute)
    config = _config_from(args)
    tasks = swebench.load_swebench_lite()
    subset = swebench.select_subset(tasks, size=args.size, seed=args.seed)
    if args.limit is not None:
        subset = subset[: args.limit]
    print(
        f"running {len(subset)} SWE-bench Lite instances x "
        f"{len(ARMS)} arms x r{args.repeats} (workers={args.workers})"
    )

    predictions: list[dict[str, str]] = []

    def make_cell(arm_value: str, task: object, repeat: int):
        def cell() -> dict[str, object]:
            arm = Arm(arm_value)
            prepared = (
                swebench.prepared_for_task(
                    arm,
                    task,
                    workspace_root=RESULTS_DIR / "workspaces",
                    cache_root=RESULTS_DIR / "cache" / "repos",
                    repeat=repeat,
                )
                if args.execute
                else None
            )
            workspace = (
                prepared.path
                if prepared is not None
                else RESULTS_DIR / "workspaces" / "dry-run"
            )
            prompt = swebench.build_prompt(task)
            outcome = run_one_task(
                suite="swebench",
                arm_value=arm.value,
                task_id=task.instance_id,
                repeat_index=repeat,
                prompt=prompt,
                workspace=workspace,
                config=config,
                execute=args.execute,
            )
            row = outcome.to_row()
            if prepared is not None:
                row["index_state"] = prepared.index_mode
            if outcome.executed:
                patch = extract_model_patch(workspace, task.base_commit)
                with _ROW_LOCK:
                    predictions.append(
                        {
                            "instance_id": (
                                f"{task.instance_id}-{arm.value}-r{repeat}"
                            ),
                            "model_patch": patch,
                        }
                    )
            append_row(row, RESULTS_DIR, "swebench")
            return row

        return cell

    done = _done_cells("swebench")
    if done:
        print(f"resume: {len(done)} swebench cells already recorded; skipping them")
    cells: list[Callable[[], dict[str, object]]] = [
        _resilient_cell(
            "swebench",
            arm_value,
            task.instance_id,
            repeat,
            make_cell(arm_value, task, repeat),
        )
        for arm_value in ("baseline", "context")
        for task in subset
        for repeat in range(args.repeats)
        if (arm_value, task.instance_id, repeat) not in done
    ]
    all_rows = _run_cells(cells, workers=args.workers)

    if args.execute:
        pred_path = swebench.write_predictions(
            predictions,
            RESULTS_DIR / "swebench" / f"preds-{args.run_id}.jsonl",
        )
        print(f"predictions written: {pred_path}")
        print(f'next: scoring/swegrade.sh "{pred_path}" "{args.run_id}"')
        write_report({"swebench": all_rows}, RESULTS_DIR / "REPORT.md")
    else:
        print(render_report({"swebench": all_rows}))
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    """Phase 0: council-enrich every unique (repo, commit) for the suites.

    Paid phase, double-gated like the sweeps; its token ledger lands in
    results/benchmarks/enrichment/runs.jsonl and is reported separately as
    one-time amortized index cost — never inside per-task sweep metrics.
    """
    from benchmarks.enrich import Enricher, unique_repos_from_tasks
    from benchmarks.suites import repoqa, swebench

    _execute_gate_or_die(args.execute)
    config = _config_from(args)
    repos: list[tuple[str, str]] = []
    if args.suite in ("repoqa", "both"):
        records = repoqa.load_repoqa_records()
        tasks = repoqa.tasks_from_records(records)
        subset = repoqa.select_subset(
            tasks, per_lang_per_repo=args.per_cell, seed=args.seed
        )
        repos.extend(unique_repos_from_tasks(subset))
    if args.suite in ("swebench", "both"):
        swe = swebench.load_swebench_lite()
        sub = swebench.select_subset(swe, size=args.size, seed=args.seed)
        repos.extend(unique_repos_from_tasks(sub))

    seen: set[tuple[str, str]] = set()
    unique = [rc for rc in repos if not (rc in seen or seen.add(rc))]
    if args.limit is not None:
        unique = unique[: args.limit]

    cache_root = RESULTS_DIR / "cache" / "repos"
    enricher = Enricher(
        config=config,
        cache_root=cache_root,
        results_dir=RESULTS_DIR,
        execute=args.execute,
        mode=args.mode,
        max_rounds=args.max_rounds,
        cap=args.cap,
    )

    print(
        f"enrichment plan: {len(unique)} unique (repo, commit) targets "
        f"mode={args.mode} execute={args.execute}"
    )
    summaries: list[object] = []
    for repo, commit in unique:
        cached = cache_root / f"{repo.replace('/', '-')}-{commit[:12]}"
        state = "enriched" if (cached / ".bi_bench_enriched").exists() else "pending"
        print(f"  [{state:>8}] {repo}@{commit[:12]}")
        if not args.execute:
            continue
        result = enricher.enrich_repo(repo, commit)
        summaries.append(result.to_row())
        print(
            f"           -> {result.status} calls={result.agent_calls} "
            f"rounds={result.rounds} features={result.features}"
        )

    if args.execute:
        from benchmarks.report import write_report

        ledger_rows = load_rows(RESULTS_DIR, "enrichment")
        path = write_report(
            {"__enrichment__": ledger_rows}, RESULTS_DIR / "ENRICHMENT.md"
        )
        print(f"enrichment report: {path}")
    else:
        print("dry-run only; pass --execute (and the env gate) to enrich.")
    return 0


def cmd_reset_cells(args: argparse.Namespace) -> int:
    """Drop rows matching --arm (optionally --index-state) from a suite log.

    Used to force a re-run of cells under a different index condition, e.g.
    deleting backbone-era context-arm rows so the enriched index gets a
    clean measurement. Never touches baseline rows unless asked.
    """
    path = RESULTS_DIR / args.suite / "runs.jsonl"
    if not path.exists():
        print(f"no rows to reset: {path}")
        return 0
    kept, dropped = [], 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        match_arm = args.arm is None or row.get("arm") == args.arm
        match_state = (
            args.index_state is None or row.get("index_state") == args.index_state
        )
        if match_arm and match_state:
            dropped += 1
        else:
            kept.append(line)
    backup = path.with_suffix(".jsonl.bak")
    backup.write_text(path.read_text())
    path.write_text("\n".join(kept) + ("\n" if kept else ""))
    print(f"{args.suite}: dropped {dropped} rows, kept {len(kept)} (backup: {backup})")
    return 0


def cmd_grade_swebench(args: argparse.Namespace) -> int:
    script = Path(__file__).resolve().parent / "scoring" / "swegrade.sh"
    argv = ["bash", str(script), str(args.predictions), args.run_id]
    result = subprocess.run(argv, check=False)
    return result.returncode


def cmd_report(args: argparse.Namespace) -> int:
    suites = ["repoqa", "swebench"] if args.suite == "all" else [args.suite]
    rows_by_suite = {suite: load_rows(RESULTS_DIR, suite) for suite in suites}
    resolved_map = _load_resolved_map(args.resolved)
    if resolved_map:
        for suite in suites:
            for row in rows_by_suite[suite]:
                key = (
                    f"{row.get('task_id')}-{row.get('arm')}-r{row.get('repeat_index')}"
                )
                if key in resolved_map:
                    row["passed"] = resolved_map[key]
    if not any(rows_by_suite.values()):
        print("no run rows found; nothing to report yet.")
        return 1
    if args.out:
        path = write_report(rows_by_suite, Path(args.out))
        print(f"report written: {path}")
    else:
        print(render_report(rows_by_suite))
    return 0


def _load_resolved_map(path_text: str | None) -> dict[str, bool]:
    if not path_text:
        return {}
    payload = json.loads(Path(path_text).read_text())
    if not isinstance(payload, dict):
        raise ValueError("resolved map must be a JSON object of id->bool")
    return {str(k): bool(v) for k, v in payload.items()}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=None)
    common.add_argument("--opencode-bin", default="opencode")
    common.add_argument("--timeout-s", type=float, default=1800.0)
    common.add_argument("--repeats", type=int, default=3)
    common.add_argument("--seed", type=int, default=20260823)
    common.add_argument(
        "--limit", type=int, default=None, help="cap tasks after stratification"
    )
    common.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel agent runs (distinct workspaces; 1 = sequential)",
    )

    parser = argparse.ArgumentParser(
        prog="python -m benchmarks",
        description="dummyindex head-to-head benchmark harness",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=BENCHMARKS_VERSION)

    sub = parser.add_subparsers(dest="command", required=True)

    plan_p = sub.add_parser("plan", help="dry-run matrix (free)", parents=[common])
    plan_p.set_defaults(func=cmd_plan, repoqa_per_cell=2, swe_size=50)

    rq_p = sub.add_parser("run-repoqa", help="RepoQA SNF cells", parents=[common])
    rq_p.add_argument(
        "--per-cell", type=int, default=2, help="needles per (language, repo)"
    )
    rq_p.add_argument(
        "--protocol",
        choices=["name", "function"],
        default="name",
        help="name = substring grading; function = official BLEU "
        "best-match grading (requires nltk)",
    )
    rq_p.add_argument("--execute", action="store_true")
    rq_p.set_defaults(func=cmd_run_repoqa)

    sw_p = sub.add_parser("run-swebench", help="SWE-bench Lite cells", parents=[common])
    sw_p.add_argument("--size", type=int, default=50)
    sw_p.add_argument("--execute", action="store_true")
    sw_p.add_argument("--run-id", default=None)
    sw_p.set_defaults(func=cmd_run_swebench)

    en_p = sub.add_parser(
        "enrich",
        help="phase 0: council-enrich unique repos (separate ledger)",
        parents=[common],
    )
    en_p.add_argument("--suite", choices=["repoqa", "swebench", "both"], default="both")
    en_p.add_argument("--per-cell", type=int, default=2)
    en_p.add_argument("--size", type=int, default=50)
    en_p.add_argument(
        "--mode", choices=["light", "standard", "deep"], default="standard"
    )
    en_p.add_argument("--cap", type=int, default=4, help="max units per batch")
    en_p.add_argument("--max-rounds", type=int, default=200)
    en_p.add_argument("--execute", action="store_true")
    en_p.set_defaults(func=cmd_enrich)

    rs_p = sub.add_parser(
        "reset-cells",
        help="drop rows by arm/index-state to force a re-measurement",
    )
    rs_p.add_argument("--suite", choices=["repoqa", "swebench"], required=True)
    rs_p.add_argument("--arm", choices=["baseline", "context"], default=None)
    rs_p.add_argument("--index-state", choices=["backbone", "enriched"], default=None)
    rs_p.set_defaults(func=cmd_reset_cells)

    gr_p = sub.add_parser("grade-swebench", help="official dockerized grading")
    gr_p.add_argument("predictions")
    gr_p.add_argument("run_id")
    gr_p.set_defaults(func=cmd_grade_swebench)

    rep_p = sub.add_parser("report", help="aggregate JSONL into REPORT.md")
    rep_p.add_argument("--suite", choices=["repoqa", "swebench", "all"], default="all")
    rep_p.add_argument("--out", default=None)
    rep_p.add_argument(
        "--resolved", default=None, help="JSON map of <id>-<arm>-r<n> -> resolved bool"
    )
    rep_p.set_defaults(func=cmd_report)

    return parser


def _install_death_recorder() -> None:
    """Log fatal signals with traceback before dying (except SIGKILL).

    Long sweeps were observed to die silently; this distinguishes SIGTERM
    (someone/something terminating us) from crashes.
    """
    import faulthandler
    import signal

    for sig in (signal.SIGTERM, signal.SIGABRT, signal.SIGSEGV, signal.SIGINT):
        try:
            faulthandler.register(sig, file=sys.stderr)
        except (OSError, RuntimeError, ValueError):  # pragma: no cover
            pass


def main(argv: list[str] | None = None) -> int:
    _install_death_recorder()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "model", None) is None:
        from benchmarks.runner import DEFAULT_MODEL

        args.model = DEFAULT_MODEL
    if args.command == "run-swebench" and not args.run_id:
        args.run_id = f"swe-{args.seed}"
    try:
        return int(args.func(args))
    except (PayGateError, RunnerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except SuiteDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
