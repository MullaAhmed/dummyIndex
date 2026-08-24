"""Arm contract tests: shared-base/single-delta AGENTS.md + workspace prep.

Workspace preparation is exercised through injected fakes for git and the
dummyindex indexer, so these tests never clone or index anything real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.arms import (
    ARMS,
    CONTEXT_SECTION,
    NEUTRAL_BASE,
    Arm,
    WorkspaceError,
    ensure_pinned_clone,
    materialize_workspace,
    prepare_arm_workspace,
    render_agents_md,
    repo_cache_dir,
)


class TestAgentsMdDelta:
    def test_baseline_is_exactly_the_neutral_base(self) -> None:
        assert render_agents_md(Arm.BASELINE) == NEUTRAL_BASE

    def test_context_is_base_plus_section(self) -> None:
        assert render_agents_md(Arm.CONTEXT) == NEUTRAL_BASE + CONTEXT_SECTION

    def test_single_delta_property(self) -> None:
        base = render_agents_md(Arm.BASELINE)
        ctx = render_agents_md(Arm.CONTEXT)
        assert ctx.startswith(base)
        assert ctx.removeprefix(base).strip() == CONTEXT_SECTION.strip()

    def test_both_arms_defined(self) -> None:
        assert {arm.value for arm in ARMS} == {"baseline", "context"}

    def test_unknown_arm_rejected(self) -> None:
        with pytest.raises(ValueError):
            render_agents_md("nope")


class RecordingRunner:
    """Fake subprocess runner capturing argv sequences."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, argv: list[str], cwd: Path | None = None) -> None:
        self.calls.append((list(argv), cwd))
        if argv[:2] == ["git", "clone"]:
            Path(argv[3]).mkdir(parents=True)
            (Path(argv[3]) / ".git").mkdir()
        elif argv[0] == "dummyindex" and len(argv) > 2:
            ws = Path(argv[-1])
            (ws / ".context").mkdir(parents=True, exist_ok=True)


def fake_cached_repo(repo: str, commit: str, cache_root: Path) -> Path:
    dest = repo_cache_dir(repo, commit, cache_root)
    (dest / ".git").mkdir(parents=True, exist_ok=True)
    (dest / ".git" / "BI_BENCH_PINNED").write_text(commit + "\n")
    (dest / "src.py").write_text("x = 1\n")
    return dest


class TestEnsurePinnedClone:
    def test_clones_then_pins(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        dest = ensure_pinned_clone(
            "acme/widget",
            "c0ffeec0ffee",
            cache_root=tmp_path,
            run_fn=runner,
        )
        assert runner.calls[0][0] == [
            "git",
            "clone",
            "https://github.com/acme/widget.git",
            str(dest),
        ]
        assert runner.calls[1][0][:3] == ["git", "checkout", "--detach"]
        assert runner.calls[1][0][3] == "c0ffeec0ffee"
        assert (dest / ".git" / "BI_BENCH_PINNED").exists()

    def test_idempotent_when_marker_present(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        first = ensure_pinned_clone(
            "acme/widget", "c0ffee", cache_root=tmp_path, run_fn=runner
        )
        calls_after_first = len(runner.calls)
        again = ensure_pinned_clone(
            "acme/widget", "c0ffee", cache_root=tmp_path, run_fn=runner
        )
        assert first == again
        assert len(runner.calls) == calls_after_first

    def test_failing_git_raises_workspace_error(self, tmp_path: Path) -> None:
        def failing_runner(argv: list[str], cwd: Path | None = None) -> None:
            raise WorkspaceError(f"git failed: {argv}")

        with pytest.raises(WorkspaceError):
            ensure_pinned_clone(
                "acme/widget",
                "deadbeef",
                cache_root=tmp_path,
                run_fn=failing_runner,
            )


class TestMaterialize:
    def test_copies_and_refuses_existing(self, tmp_path: Path) -> None:
        cached = fake_cached_repo("acme/widget", "c0ffee", tmp_path / "cache")
        target = tmp_path / "ws"
        materialize_workspace(cached, target)
        assert (target / "src.py").exists()
        with pytest.raises(WorkspaceError):
            materialize_workspace(cached, target)


class TestPrepareArmWorkspace:
    def test_context_arm_indexes_and_writes_doc_last(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        fake_cached_repo("acme/widget", "cafe1234abcd", cache_root)
        ws_root = tmp_path / "ws"

        prepared = prepare_arm_workspace(
            Arm.CONTEXT,
            "acme/widget",
            "cafe1234abcd",
            ws_root,
            cache_root=cache_root,
            run_setup=runner,
        )
        ingest_calls = [c for c in runner.calls if c[0][0] == "dummyindex"]
        assert len(ingest_calls) == 1
        argv = ingest_calls[0][0]
        assert "--platform" in argv and "agents" in argv
        assert "--no-hooks" in argv
        assert str(prepared.path) in argv[-1]
        assert prepared.indexed
        doc_path = prepared.path / "AGENTS.md"
        assert doc_path.read_text() == render_agents_md(Arm.CONTEXT)

    def test_baseline_arm_never_invokes_indexer(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        fake_cached_repo("acme/widget", "beef01abc1234", cache_root)
        prepared = prepare_arm_workspace(
            Arm.BASELINE,
            "acme/widget",
            "beef01abc1234",
            tmp_path / "ws",
            cache_root=cache_root,
            run_setup=runner,
        )
        assert not any(c[0][0] == "dummyindex" for c in runner.calls)
        assert not prepared.indexed
        assert (prepared.path / "AGENTS.md").read_text() == NEUTRAL_BASE

    def test_resume_reuses_marked_workspace(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        fake_cached_repo("acme/widget", "cafe1234abcd", cache_root)
        first = prepare_arm_workspace(
            Arm.CONTEXT,
            "acme/widget",
            "cafe1234abcd",
            tmp_path / "ws",
            cache_root=cache_root,
            run_setup=runner,
        )
        calls_after_first = len(runner.calls)
        second = prepare_arm_workspace(
            Arm.CONTEXT,
            "acme/widget",
            "cafe1234abcd",
            tmp_path / "ws",
            cache_root=cache_root,
            run_setup=runner,
        )
        assert second.path == first.path
        assert second.indexed is True
        assert len(runner.calls) == calls_after_first

    def test_context_inherits_enriched_cache(self, tmp_path: Path) -> None:
        from benchmarks.arms import mark_enriched

        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        cached = fake_cached_repo("acme/widget", "cafe1234abcd", cache_root)
        feats = cached / ".context" / "features"
        feats.mkdir(parents=True)
        (feats / "INDEX.json").write_text('{"features": []}')
        mark_enriched(cached, mode="standard", units=7)
        prepared = prepare_arm_workspace(
            Arm.CONTEXT,
            "acme/widget",
            "cafe1234abcd",
            tmp_path / "ws",
            cache_root=cache_root,
            run_setup=runner,
        )
        assert prepared.index_mode == "enriched"
        # no ingest ran: curated work is inherited, never overwritten
        assert not any(c[0][0] == "dummyindex" for c in runner.calls)
        assert (prepared.path / ".context").exists()

    def test_baseline_strips_enriched_context(self, tmp_path: Path) -> None:
        from benchmarks.arms import mark_enriched

        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        cached = fake_cached_repo("acme/widget", "cafe1234abcd", cache_root)
        mark_enriched(cached, mode="standard", units=7)
        prepared = prepare_arm_workspace(
            Arm.BASELINE,
            "acme/widget",
            "cafe1234abcd",
            tmp_path / "ws",
            cache_root=cache_root,
            run_setup=runner,
        )
        assert prepared.index_mode == "none"
        assert not (prepared.path / ".context").exists()

    def test_backbone_mode_when_cache_not_enriched(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        fake_cached_repo("acme/widget", "cafe1234abcd", cache_root)
        prepared = prepare_arm_workspace(
            Arm.CONTEXT,
            "acme/widget",
            "cafe1234abcd",
            tmp_path / "ws",
            cache_root=cache_root,
            run_setup=runner,
        )
        assert prepared.index_mode == "backbone"

    def test_partial_workspace_wiped_and_rebuilt(self, tmp_path: Path) -> None:
        runner = RecordingRunner()
        cache_root = tmp_path / "cache"
        fake_cached_repo("acme/widget", "cafe1234abcd", cache_root)
        ws_root = tmp_path / "ws"
        stale = ws_root / "acme-widget-cafe1234abcd-baseline"
        stale.mkdir(parents=True)
        (stale / "junk.txt").write_text("half-copied\n")
        prepared = prepare_arm_workspace(
            Arm.BASELINE,
            "acme/widget",
            "cafe1234abcd",
            ws_root,
            cache_root=cache_root,
            run_setup=runner,
        )
        assert not (prepared.path / "junk.txt").exists()
        assert (prepared.path / "src.py").exists()
