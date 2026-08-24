"""Phase-0 per-repo council enrichment, driven through opencode.

Builds the FULL curated `.context/` (feature specs/plans/concerns written by
the council personas) once per ``(repo, commit)`` in the shared pinned cache
clone — never per benchmark cell — so every context-arm workspace copy
inherits a genuinely useful index and the one-time index-build cost stays a
separate line item.

Accounting split: every agent call here flows through the standard runner
under ``suite="enrichment"``, i.e. its own JSONL ledger at
``results/benchmarks/enrichment/runs.jsonl``. The sweep report reads that
ledger ONLY for the amortized-cost section; gates never see it.

Loop = the real dummyindex council protocol:

1. ``dummyindex context council-batch --next --json`` → dispatch units.
2. One opencode run per unit: the agent reads the shipped procedure file for
   its role (copied into ``.context/council/procedures/`` from the installed
   dummyindex package), writes its markdown, places it via
   ``context section-write``, logs via ``context council-log``.
3. Repeat until ``complete`` or ``--max-rounds``.
4. Deterministic closeout per feature: ``reality-check`` + ``mark-enriched``;
   then the local completion marker makes the whole repo skippable on resume.

Fully offline-testable: subprocess calls are injectable; nothing here runs
unless invoked with execute=True behind the usual pay gates.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from benchmarks import arms
from benchmarks.runner import RunnerConfig, run_one_task

COUNCIL_NEXT_ARGV = ["dummyindex", "context", "council-batch", "--next", "--json"]
REALITY_CHECK_ARGV = ["dummyindex", "context", "reality-check"]
MARK_ENRICHED_ARGV = ["dummyindex", "context", "mark-enriched"]

DEFAULT_MODE = "standard"
PROCEDURE_DIRNAME = ".context/council/procedures"


class EnrichError(Exception):
    """Raised when the enrichment loop cannot proceed."""


@dataclass(frozen=True)
class EnrichResult:
    repo: str
    commit: str
    status: str  # "already" | "done" | "stalled" | "failed"
    agent_calls: int = 0
    rounds: int = 0
    features: int = 0
    detail: str = ""

    def to_row(self) -> dict[str, object]:
        return {
            "repo": self.repo,
            "commit": self.commit,
            "status": self.status,
            "agent_calls": self.agent_calls,
            "rounds": self.rounds,
            "features": self.features,
            "detail": self.detail,
        }


def _run_json(argv: list[str], cwd: Path) -> dict:
    """Run a dummyindex CLI call returning stdout JSON; hard error otherwise."""
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise EnrichError(
            f"{' '.join(argv)} exited {result.returncode}: {result.stderr[-300:]!r}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EnrichError(
            f"{' '.join(argv)} printed non-JSON stdout: {result.stdout[:200]!r}"
        ) from exc


def _copy_procedures(cached: Path) -> int:
    """Ship the council procedure markdowns into the workspace for agents."""
    try:
        import dummyindex as _pkg  # noqa: PLC0415 - located at runtime

        src = Path(_pkg.__file__).parent / "skills" / "council"
    except ImportError:
        src = Path(__file__).resolve().parents[1] / "dummyindex" / "skills" / "council"
    if not src.is_dir():
        raise EnrichError(f"council procedures not found at {src}")
    dest = cached / PROCEDURE_DIRNAME
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for md in sorted(src.glob("*.md")):
        shutil.copy2(md, dest / md.name)
        count += 1
    return count


def _unit_prompt(unit: dict, mode: str) -> str:
    feature = unit.get("feature_id")
    stage = unit.get("stage")
    role = unit.get("role") or unit.get("subagent_type") or "dev"
    return (
        f"You are executing ONE council unit inside this repository's "
        f"`.context/` index.\n\n"
        f"Unit: feature={feature} stage={stage} role={role} mode={mode}\n\n"
        f"Steps:\n"
        f"1. Read `.context/council/procedures/` and follow the procedure "
        f"file matching your stage/role for feature `{feature}` exactly.\n"
        f"2. Read `.context/features/{feature}/feature.json` and the member "
        f"sources it cites before writing anything.\n"
        f"3. Write your section markdown to a scratch file in this directory "
        f"(e.g. `_draft_{stage}.md`).\n"
        f"4. Place it atomically:\n"
        f"   dummyindex context section-write --root . --feature {feature} "
        f"--section <spec|plan|concerns> --from-file <scratch>\n"
        f"5. Log completion:\n"
        f"   dummyindex context council-log --root . --feature {feature} "
        f"--stage {stage} --agent {role} --status complete\n"
        f"\nDo not touch files outside `.context/` and your scratch file. "
        f"When the placement command succeeds, reply DONE."
    )


@dataclass
class Enricher:
    """Drives the council loop over cached clones; injectable for tests."""

    config: RunnerConfig
    cache_root: Path
    results_dir: Path
    execute: bool = False
    mode: str = DEFAULT_MODE
    max_rounds: int = 200
    cap: int = 4
    runner_fn: Callable[..., object] | None = None
    cli_fn: Callable[[list[str], Path], dict] | None = None
    setup_fn: Callable[..., None] | None = None
    calls_log: list[dict[str, object]] = field(default_factory=list)

    def _cli(self, argv: list[str], cwd: Path) -> dict:
        if self.cli_fn is not None:
            return self.cli_fn(argv, cwd)
        return _run_json(argv, cwd)

    def enrich_repo(self, repo: str, commit: str) -> EnrichResult:
        cached = arms.ensure_pinned_clone(
            repo, commit, cache_root=self.cache_root, run_fn=self.setup_fn
        )
        if arms.is_enriched(cached):
            return EnrichResult(repo, commit, "already")

        ctx = cached / ".context"
        if not ctx.exists():
            (self.setup_fn or arms._run)([*arms.INGEST_ARGV_TEMPLATE, str(cached)])

        features = self._feature_ids(cached)
        _copy_procedures(cached)
        rounds = 0
        agent_calls = 0
        while True:
            batch = self._cli(
                [
                    "dummyindex",
                    "context",
                    "council-batch",
                    "--next",
                    "--json",
                    "--mode",
                    self.mode,
                    "--cap",
                    str(self.cap),
                ],
                cached,
            )
            if batch.get("complete"):
                break
            rounds += 1
            if rounds > self.max_rounds:
                return EnrichResult(
                    repo,
                    commit,
                    "stalled",
                    agent_calls,
                    rounds,
                    len(features),
                    detail="max-rounds exceeded",
                )
            for unit in batch.get("units", []):
                self._dispatch_unit(cached, repo, unit)
                agent_calls += 1

        for feature in features:
            self._close_feature(cached, feature)
        arms.mark_enriched(cached, mode=self.mode, units=agent_calls)
        return EnrichResult(repo, commit, "done", agent_calls, rounds, len(features))

    def _dispatch_unit(self, cached: Path, repo: str, unit: dict) -> None:
        feature = unit.get("feature_id", "?")
        stage = unit.get("stage", "?")
        task_id = f"{repo}/{feature}/stage{stage}"
        prompt = _unit_prompt(unit, self.mode)
        outcome = run_one_task(
            suite="enrichment",
            arm_value="council",
            task_id=task_id,
            repeat_index=0,
            prompt=prompt,
            workspace=cached,
            config=self.config,
            execute=self.execute,
            stream_fn=self.runner_fn or None,
        )
        row = outcome.to_row()
        row["enrich_unit"] = {
            "feature_id": feature,
            "stage": stage,
            "role": unit.get("role"),
        }
        if outcome.executed:
            # The enrichment ledger is a COST ledger: only real, paid calls
            # belong in it. Planned dry-run cells are counted by the caller.
            from benchmarks.runner import append_row

            append_row(row, self.results_dir, "enrichment")
        self.calls_log.append(row)
        if outcome.executed and "DONE" not in outcome.metrics.response_text.upper():
            # Agent finished its session without confirming placement; let the
            # next council-batch decide whether the unit is actually done.
            pass

    def _close_feature(self, cached: Path, feature: str) -> None:
        self._cli(
            [
                "dummyindex",
                "context",
                "reality-check",
                "--root",
                ".",
                "--feature",
                feature,
                "--json",
            ],
            cached,
        )
        self._cli(
            [
                "dummyindex",
                "context",
                "mark-enriched",
                "--root",
                ".",
                "--feature",
                feature,
            ],
            cached,
        )

    @staticmethod
    def _feature_ids(cached: Path) -> list[str]:
        index = cached / ".context" / "features" / "INDEX.json"
        if not index.exists():
            return []
        try:
            payload = json.loads(index.read_text())
        except json.JSONDecodeError:
            return []
        feats = payload.get("features", [])
        ids = []
        for f in feats:
            fid = f.get("feature_id") if isinstance(f, dict) else None
            trivial = f.get("trivial") if isinstance(f, dict) else False
            if fid and not trivial:
                ids.append(str(fid))
        return ids


def unique_repos_from_tasks(tasks: list) -> list[tuple[str, str]]:
    """Deduplicate (repo, commit) preserving first-seen order.

    Accepts both suite task shapes (``SnfTask.commit`` /
    ``SweTask.base_commit``).
    """
    seen: dict[tuple[str, str], None] = {}
    for t in tasks:
        commit = getattr(t, "commit", None) or getattr(t, "base_commit", "")
        seen.setdefault((t.repo, str(commit)), None)
    return list(seen)


__all__ = [
    "COUNCIL_NEXT_ARGV",
    "DEFAULT_MODE",
    "EnrichError",
    "EnrichResult",
    "Enricher",
    "unique_repos_from_tasks",
]
