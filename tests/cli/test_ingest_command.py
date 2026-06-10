"""Tests for the top-level `dummyindex ingest` CLI command."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.paths import REPO_ROOT, SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO
_REPO_ROOT = REPO_ROOT


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


def _run_dummyindex(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dummyindex", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )


@pytest.mark.integration
def test_ingest_with_path_arg_creates_context(sample_repo: Path) -> None:
    rc = _run_dummyindex(["ingest", str(sample_repo)])
    assert rc.returncode == 0, rc.stderr
    assert (sample_repo / ".context").is_dir()
    assert (sample_repo / ".context" / "tree.json").exists()
    # CLAUDE.md lives inside .claude/, never at the project root.
    assert (sample_repo / ".claude" / "CLAUDE.md").exists()
    assert not (sample_repo / "CLAUDE.md").exists()


@pytest.mark.integration
def test_ingest_includes_managed_block_in_claude_md(sample_repo: Path) -> None:
    _run_dummyindex(["ingest", str(sample_repo)])
    claude_md = (sample_repo / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "dummyindex:begin" in claude_md
    assert ".context/HOW_TO_USE.md" in claude_md


@pytest.mark.integration
def test_ingest_writes_all_v0_files(sample_repo: Path) -> None:
    _run_dummyindex(["ingest", str(sample_repo)])
    ctx = sample_repo / ".context"
    expected = [
        "INDEX.md",
        "PROJECT.md",
        "HOW_TO_USE.md",
        "tree.json",
        "meta.json",
        "map/files.json",
        "map/symbols.json",
        "conventions/naming.md",
        "conventions/naming.json",
        "architecture/overview.md",
        "playbooks/add-feature.md",
        "playbooks/add-endpoint.md",
        "playbooks/add-migration.md",
        "playbooks/fix-bug.md",
        "playbooks/refactor.md",
    ]
    for rel in expected:
        assert (ctx / rel).exists(), f"missing {rel}"


@pytest.mark.integration
def test_ingest_command_appears_in_help() -> None:
    result = _run_dummyindex(["--help"])
    assert "ingest" in result.stdout
    assert ".context/" in result.stdout
    assert "CLAUDE.md" in result.stdout
