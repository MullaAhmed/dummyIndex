"""Tests for dummyindex.context.runner — end-to-end build_all flow."""

from __future__ import annotations

import importlib
import json
import re
import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.manifest import compare
from dummyindex.context.build.runner import BuildResult, build_all
from dummyindex.context.build.upgrade import ensure_context_gitignore
from dummyindex.pipeline.io.detect import detect
from tests.paths import FIXTURES_DIR, SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO
_RETIRED_SUITES = FIXTURES_DIR / "retired_equipment_evals"
_FAKE_CACHE_ENTRY = "ab" * 32 + ".json"
_CACHE_ENTRY_RE = re.compile(r"[0-9a-f]{64}\.json")


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


@pytest.mark.integration
def test_build_all_returns_build_result(sample_repo: Path, tmp_path: Path) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    assert isinstance(result, BuildResult)
    assert result.root == sample_repo
    assert result.context_dir == sample_repo / ".context"
    assert result.file_count > 0
    assert result.symbol_count > 0


@pytest.mark.integration
def test_build_all_writes_every_expected_file(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    expected = {
        "meta.json",
        "map/files.json",
        "map/symbols.json",
        "tree.json",
        "conventions/naming.json",
        "conventions/naming.md",
        "PROJECT.md",
        "INDEX.md",
    }
    assert expected <= set(result.written)
    for rel in expected:
        assert (result.context_dir / rel).exists(), f"missing {rel}"


@pytest.mark.integration
def test_build_all_writes_meta_with_real_counts(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    meta_payload = json.loads(
        (result.context_dir / "meta.json").read_text(encoding="utf-8")
    )
    assert meta_payload["file_count"] == result.file_count
    assert meta_payload["symbol_count"] == result.symbol_count
    assert sorted(meta_payload["languages"]) == sorted(result.languages)


@pytest.mark.integration
def test_build_all_with_bootstrap_writes_claude_md(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache", bootstrap=True)
    assert result.bootstrapped is True
    claude_md = sample_repo / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "dummyindex" in claude_md.read_text(encoding="utf-8")
    # CLAUDE.md must live inside .claude/, never at the project root.
    assert not (sample_repo / "CLAUDE.md").exists()


@pytest.mark.integration
def test_build_all_without_bootstrap_skips_claude_md(
    sample_repo: Path, tmp_path: Path
) -> None:
    build_all(sample_repo, cache_root=tmp_path / "cache", bootstrap=False)
    assert not (sample_repo / "CLAUDE.md").exists()
    assert not (sample_repo / ".claude" / "CLAUDE.md").exists()


@pytest.mark.integration
def test_build_all_languages_inferred(sample_repo: Path, tmp_path: Path) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    assert "python" in result.languages
    assert "typescript" in result.languages


@pytest.mark.integration
def test_index_md_lists_what_was_written(sample_repo: Path, tmp_path: Path) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    index_text = (result.context_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "tree.json" in index_text
    assert "map/symbols.json" in index_text
    assert "conventions/naming.md" in index_text


@pytest.mark.integration
def test_second_run_is_idempotent_in_content(sample_repo: Path, tmp_path: Path) -> None:
    first = build_all(sample_repo, cache_root=tmp_path / "cache")
    files_first = (first.context_dir / "map" / "files.json").read_text(encoding="utf-8")
    symbols_first = (first.context_dir / "map" / "symbols.json").read_text(
        encoding="utf-8"
    )
    tree_first = (first.context_dir / "tree.json").read_text(encoding="utf-8")

    build_all(sample_repo, cache_root=tmp_path / "cache")
    files_second = (first.context_dir / "map" / "files.json").read_text(
        encoding="utf-8"
    )
    symbols_second = (first.context_dir / "map" / "symbols.json").read_text(
        encoding="utf-8"
    )
    tree_second = (first.context_dir / "tree.json").read_text(encoding="utf-8")

    # Files/symbols/tree are deterministic — should round-trip identically
    assert files_first == files_second
    assert symbols_first == symbols_second
    assert tree_first == tree_second


# ---------------------------------------------------------------------------
# Context-layout migration on the build path
# ---------------------------------------------------------------------------


def _cache_entries(cache: Path) -> set[str]:
    return {p.name for p in cache.iterdir() if _CACHE_ENTRY_RE.fullmatch(p.name)}


def _seed_older_context(repo: Path) -> dict[str, bytes]:
    """Lay down the ``.context/`` an older dummyindex leaves behind.

    Returns the bytes of every file the migration must back up, keyed by
    its ``.context/``-relative backup path.
    """
    ctx = repo / ".context"
    ensure_context_gitignore(ctx)
    gitignore = ctx / ".gitignore"
    gitignore.write_text(
        "".join(
            line + "\n"
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() != "_council-log.json"
        ),
        encoding="utf-8",
    )
    legacy_graph = b'{"nodes": [], "edges": []}\n'
    (ctx / "graph").mkdir()
    (ctx / "graph" / "graph.json").write_bytes(legacy_graph)
    (ctx / "_enrich_plan.json").write_bytes(b"{}\n")

    evals = ctx / "equipment-evals"
    evals.mkdir()
    starter = "python-tester.suite.json"
    shutil.copyfile(_RETIRED_SUITES / starter, evals / starter)
    original = (_RETIRED_SUITES / "python-implementer.suite.json").read_bytes()
    edited = original.replace(b"unrelated", b"unrelatee", 1)
    assert edited != original
    (evals / "python-implementer.suite.json").write_bytes(edited)

    cache = ctx / "cache"
    cache.mkdir()
    (cache / "extraction-version").write_bytes(b"0.36.0\n")
    (cache / _FAKE_CACHE_ENTRY).write_bytes(b'{"nodes": [], "edges": []}\n')
    return {
        "_doc_backups/retired/0.37.0/equipment-evals/python-implementer.suite.json": (
            edited
        ),
        "_doc_backups/retired/0.6.0/graph/graph.json": legacy_graph,
    }


@pytest.mark.integration
def test_build_all_migrates_an_older_context_layout(
    sample_repo: Path, tmp_path: Path
) -> None:
    expected_backups = _seed_older_context(sample_repo)
    ctx = sample_repo / ".context"

    result = build_all(
        sample_repo, cache_root=tmp_path / "cache", dummyindex_version="9.9.9"
    )

    migration = result.migration
    assert migration.errors == ()
    assert set(migration.removed) == {
        "_enrich_plan.json",
        "equipment-evals/python-implementer.suite.json",
        "equipment-evals/python-tester.suite.json",
        "graph/graph.json",
        "cache: 1 stale extraction entries",
    }
    assert set(migration.backed_up) == set(expected_backups)

    assert not (ctx / "graph").exists()
    assert not (ctx / "_enrich_plan.json").exists()
    assert not (ctx / "equipment-evals").exists()
    lines = (ctx / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "_council-log.json" in lines
    for rel, data in expected_backups.items():
        assert (ctx / rel).read_bytes() == data
    # The unedited starter suite is provably generated: deleted, no backup.
    assert not (
        ctx / "_doc_backups/retired/0.37.0/equipment-evals/python-tester.suite.json"
    ).exists()
    # The current graph replaces the legacy one.
    assert (ctx / "features" / "symbol-graph.json").is_file()

    cache = ctx / "cache"
    assert not (cache / _FAKE_CACHE_ENTRY).exists()
    assert (cache / "extraction-version").read_text(encoding="utf-8").strip() == (
        "9.9.9"
    )
    # The scope ran before extraction, so this build's own entries survive.
    assert _cache_entries(cache)


@pytest.mark.integration
def test_build_all_reuses_a_cache_stamped_with_its_own_version(
    sample_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two real builds, no hand-seeded stamp: a fresh repo's first build must
    # stamp the cache it fills, or the second build would discard it.
    first = build_all(
        sample_repo, cache_root=tmp_path / "cache", dummyindex_version="9.9.9"
    )
    cache = first.context_dir / "cache"
    assert (cache / "extraction-version").read_text(encoding="utf-8").strip() == (
        "9.9.9"
    )
    entries = _cache_entries(cache)
    assert entries, "first build wrote no extraction entries"
    (cache / _FAKE_CACHE_ENTRY).write_bytes(b'{"nodes": [], "edges": []}\n')

    extract_module = importlib.import_module("dummyindex.pipeline.extract")
    real_save = extract_module.save_cached
    saved: list[Path] = []

    def _spy(path, *args, **kwargs):
        saved.append(Path(path))
        return real_save(path, *args, **kwargs)

    monkeypatch.setattr(extract_module, "save_cached", _spy)
    second = build_all(
        sample_repo, cache_root=tmp_path / "cache", dummyindex_version="9.9.9"
    )

    assert second.migration.errors == ()
    assert not any(item.startswith("cache:") for item in second.migration.removed)
    assert saved == [], "every file should have been served from the cache"
    assert (cache / _FAKE_CACHE_ENTRY).is_file()
    assert entries <= _cache_entries(cache)


def test_build_all_seeds_memory_store(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    from dummyindex.context.build.runner import build_all

    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    assert (tmp_path / ".context" / "session-memory" / "now.md").exists()
    assert (tmp_path / ".context" / "session-memory" / "core-memories.md").exists()


def test_rebuild_preserves_memory_content(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    from dummyindex.context.build.runner import build_all

    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    now_path = tmp_path / ".context" / "session-memory" / "now.md"
    now_path.write_text(
        "# Now\n\n## 2026-06-05 10:00 | main\nprecious note\n", encoding="utf-8"
    )
    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    assert "precious note" in now_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Regression: session-memory store must be invisible to drift detection
# ---------------------------------------------------------------------------


def test_detect_excludes_session_memory_store(tmp_path: Path) -> None:
    """Root-cause guard: detect() must not collect any file under .context/session-memory/.

    If a future change accidentally re-includes the dir in the walk, this test
    catches it before the end-to-end drift test can fire.
    """
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    session_memory_dir = tmp_path / ".context" / "session-memory"
    session_memory_dir.mkdir(parents=True, exist_ok=True)
    (session_memory_dir / "now.md").write_text(
        "# Now\n\n## 2026-06-05 12:00 | main\nhandoff note\n", encoding="utf-8"
    )

    detection = detect(tmp_path.resolve())
    collected = [p for bucket in detection["files"].values() for p in bucket]

    # Vacuous-pass guard: detect must have found at least one file (a.py).
    assert any(str(p).endswith("a.py") for p in collected), (
        "detect() returned no files — test is vacuously passing"
    )
    # Core guarantee: no collected path is inside .context/session-memory/.
    assert not any("session-memory" in str(p) for p in collected), (
        f"session-memory files leaked into detect() output: "
        f"{[p for p in collected if 'session-memory' in str(p)]}"
    )


def test_session_memory_write_does_not_register_as_drift(tmp_path: Path) -> None:
    """End-to-end guard: writing to session-memory after build_all must not produce drift.

    Mirrors the exact file-list construction that check.run uses so the test
    is faithful to real drift detection. Uses compare() directly to avoid the
    --auto-refresh side-effect of dispatch(['check', ...]).
    """
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")

    # Simulate a /dummyindex-remember save — write into session-memory post-build.
    now_path = tmp_path / ".context" / "session-memory" / "now.md"
    now_path.write_text(
        "# Now\n\n## 2026-06-05 12:00 | main\nhandoff note\n", encoding="utf-8"
    )

    # Reconstruct the current-files list exactly as check.run does.
    detection = detect(tmp_path.resolve())
    files_map = detection.get("files", {}) or {}
    current: list[Path] = [Path(p) for p in files_map.get("code", [])]
    for ftype in ("document", "paper"):
        for raw in files_map.get(ftype, []) or []:
            p = Path(raw)
            try:
                p.resolve().relative_to(tmp_path.resolve())
            except ValueError:
                continue
            current.append(p)

    context_dir = tmp_path / ".context"
    drift = compare(context_dir, root=tmp_path, current_files=current)

    # Primary: the full drift report must be clean.
    assert drift.is_clean, (
        f"Drift detected after session-memory write — "
        f"added={drift.added!r}, modified={drift.modified!r}, removed={drift.removed!r}"
    )
    # Targeted: no session-memory path in any drift bucket (belt-and-suspenders).
    all_drift_paths = (*drift.added, *drift.modified, *drift.removed)
    assert not any("session-memory" in s for s in all_drift_paths), (
        f"session-memory paths appeared in drift report: "
        f"{[s for s in all_drift_paths if 'session-memory' in s]}"
    )
