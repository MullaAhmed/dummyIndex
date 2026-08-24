"""Enrichment driver tests — fully offline via injected CLI/runner fakes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.enrich import (
    Enricher,
    EnrichError,
    unique_repos_from_tasks,
)
from benchmarks.runner import RunnerConfig


def fake_cli(batches: list[dict], features: list[str] | None = None):
    """Return a cli_fn serving queued council-batch responses."""
    calls: list[tuple[list[str], Path]] = []
    state = {"i": 0}

    def cli(argv: list[str], cwd: Path) -> dict:
        calls.append((list(argv), cwd))
        if argv[2] == "council-batch":
            resp = batches[min(state["i"], len(batches) - 1)]
            state["i"] += 1
            return resp
        return {"ok": True}

    cli.calls = calls  # type: ignore[attr-defined]
    return cli


def make_stream(lines: list[str]):
    def factory(argv, *, cwd, env, timeout_s):
        class P:
            returncode = 0
            stderr = None

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

        return (lambda: iter(lines)), P()

    return factory


DONE_STREAM = ['{"type":"text","text":"DONE"}']


@pytest.fixture()
def cached_repo(tmp_path: Path) -> Path:
    from benchmarks.arms import repo_cache_dir

    dest = repo_cache_dir("acme/widget", "a" * 40, tmp_path / "cache")
    ctx = dest / ".context" / "features"
    ctx.mkdir(parents=True)
    (ctx / "INDEX.json").write_text(
        json.dumps({"features": [{"feature_id": "f-1", "trivial": False}]})
    )
    git = dest / ".git"
    if not git.is_dir():
        git.mkdir()
    (git / "BI_BENCH_PINNED").write_text("a" * 40 + "\n")
    return dest


class TestUniqueRepos:
    def test_dedupes_preserving_order(self) -> None:
        class T:
            def __init__(self, r, c):
                self.repo, self.commit = r, c

        tasks = [T("a/x", "1"), T("b/y", "2"), T("a/x", "1"), T("a/x", "3")]
        out = unique_repos_from_tasks(tasks)
        assert out == [("a/x", "1"), ("b/y", "2"), ("a/x", "3")]


class TestEnricher:
    def _enricher(
        self,
        tmp_path,
        cli,
        execute=False,
        max_rounds=50,
        monkeypatch=None,
    ):
        if execute and monkeypatch is not None:
            monkeypatch.setenv("DUMMYINDEX_BENCH_ALLOW_PAY", "1")
        return Enricher(
            config=RunnerConfig(real_data_home=tmp_path),
            cache_root=tmp_path / "cache",
            results_dir=tmp_path / "results",
            execute=execute,
            runner_fn=make_stream(DONE_STREAM),
            cli_fn=cli,
        )

    def test_already_enriched_short_circuits(self, tmp_path, cached_repo) -> None:
        from benchmarks.arms import mark_enriched

        mark_enriched(cached_repo, mode="standard", units=0)
        cli = fake_cli([])
        result = self._enricher(tmp_path, cli).enrich_repo("acme/widget", "a" * 40)
        assert result.status == "already"
        assert result.agent_calls == 0

    def test_full_loop_done_and_marker(
        self, tmp_path, cached_repo, monkeypatch
    ) -> None:
        batch_pending = {
            "complete": False,
            "units": [
                {"feature_id": "f-1", "stage": 1, "role": "dev"},
                {"feature_id": "f-1", "stage": 2, "role": "architect"},
            ],
        }
        batch_done = {"complete": True, "units": []}
        cli = fake_cli([batch_pending, batch_done])
        enricher = self._enricher(tmp_path, cli, execute=True, monkeypatch=monkeypatch)
        result = enricher.enrich_repo("acme/widget", "a" * 40)

        assert result.status == "done"
        assert result.agent_calls == 2
        assert result.rounds == 1
        assert (cached_repo / ".bi_bench_enriched").exists()
        # two agent dispatches + reality-check + mark-enriched CLI calls
        dispatches = [
            c for c in cli.calls if c[0][2] in ("reality-check", "mark-enriched")
        ]
        assert len(dispatches) == 2
        ledger = (
            (tmp_path / "results" / "enrichment" / "runs.jsonl")
            .read_text()
            .strip()
            .splitlines()
        )
        assert len(ledger) == 2
        row = json.loads(ledger[0])
        assert row["executed"] is True
        assert row["task_id"] == "acme/widget/f-1/stage1"

    def test_stall_cap_reports(self, tmp_path, cached_repo, monkeypatch) -> None:
        endless = {"complete": False, "units": []}
        cli = fake_cli([endless])
        enricher = self._enricher(
            tmp_path, cli, execute=True, max_rounds=3, monkeypatch=monkeypatch
        )
        result = enricher.enrich_repo("acme/widget", "a" * 40)
        assert result.status == "stalled"
        assert not (cached_repo / ".bi_bench_enriched").exists()

    def test_dry_run_dispatches_nothing(self, tmp_path, cached_repo) -> None:
        batch = {"complete": False, "units": [{"feature_id": "f-1", "stage": 1}]}
        cli = fake_cli([batch])
        enricher = self._enricher(tmp_path, cli, execute=False)
        result = enricher.enrich_repo("acme/widget", "a" * 40)
        # loop consumes planned outcomes; no ledger file written
        assert not (tmp_path / "results" / "enrichment").exists()
        assert result.status in ("done", "stalled")

    def test_missing_context_ingests_first(
        self, tmp_path, cached_repo, monkeypatch
    ) -> None:
        import shutil

        shutil.rmtree(cached_repo / ".context")
        setups: list[list[str]] = []

        def setup(argv, cwd=None):
            setups.append(list(argv))
            ctx = Path(argv[-1]) / ".context" / "features"
            ctx.mkdir(parents=True, exist_ok=True)
            (ctx / "INDEX.json").write_text(json.dumps({"features": []}))

        batch_done = {"complete": True, "units": []}
        cli = fake_cli([batch_done])
        monkeypatch.setenv("DUMMYINDEX_BENCH_ALLOW_PAY", "1")
        enricher = Enricher(
            config=RunnerConfig(real_data_home=tmp_path),
            cache_root=tmp_path / "cache",
            results_dir=tmp_path / "results",
            execute=True,
            runner_fn=make_stream(DONE_STREAM),
            cli_fn=cli,
            setup_fn=setup,
        )
        result = enricher.enrich_repo("acme/widget", "a" * 40)
        assert result.status == "done"
        assert any(a[0] == "dummyindex" and "ingest" in a for a in setups)

    def test_unit_prompt_carries_feature_stage_role(self) -> None:
        from benchmarks.enrich import _unit_prompt

        prompt = _unit_prompt(
            {"feature_id": "f-9", "stage": 2, "role": "critic"}, "deep"
        )
        assert "feature=f-9" in prompt
        assert "stage=2" in prompt
        assert "--section <spec|plan|concerns>" in prompt
        assert "procedures/" in prompt

    def test_cli_failure_raises(self, tmp_path, cached_repo) -> None:
        def bad_cli(argv, cwd):
            raise EnrichError("boom")

        enricher = self._enricher(tmp_path, bad_cli)
        with pytest.raises(EnrichError):
            enricher.enrich_repo("acme/widget", "a" * 40)
