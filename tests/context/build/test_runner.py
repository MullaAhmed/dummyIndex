"""Tests for dummyindex.context.runner — end-to-end build_all flow."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from tests.paths import SAMPLE_REPO

import pytest

from dummyindex.context.build.manifest import compare
from dummyindex.context.build.runner import BuildResult, build_all
from dummyindex.pipeline.io.detect import detect

_FIXTURE_ROOT = SAMPLE_REPO


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
def test_index_md_lists_what_was_written(
    sample_repo: Path, tmp_path: Path
) -> None:
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    index_text = (result.context_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "tree.json" in index_text
    assert "map/symbols.json" in index_text
    assert "conventions/naming.md" in index_text


@pytest.mark.integration
def test_second_run_is_idempotent_in_content(
    sample_repo: Path, tmp_path: Path
) -> None:
    first = build_all(sample_repo, cache_root=tmp_path / "cache")
    files_first = (first.context_dir / "map" / "files.json").read_text(encoding="utf-8")
    symbols_first = (first.context_dir / "map" / "symbols.json").read_text(encoding="utf-8")
    tree_first = (first.context_dir / "tree.json").read_text(encoding="utf-8")

    build_all(sample_repo, cache_root=tmp_path / "cache")
    files_second = (first.context_dir / "map" / "files.json").read_text(encoding="utf-8")
    symbols_second = (first.context_dir / "map" / "symbols.json").read_text(encoding="utf-8")
    tree_second = (first.context_dir / "tree.json").read_text(encoding="utf-8")

    # Files/symbols/tree are deterministic — should round-trip identically
    assert files_first == files_second
    assert symbols_first == symbols_second
    assert tree_first == tree_second


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
