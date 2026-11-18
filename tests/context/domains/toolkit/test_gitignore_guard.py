"""Project toolkit writes keep ``.context/toolkit/`` out of git, and only that."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.domains.toolkit.host import (
    WriteSession,
    preserve_skill,
    project_layout,
    write_stash,
)

pytestmark = pytest.mark.unit

_GIT = shutil.which("git")


def _gitignore(root: Path) -> list[str]:
    return (root / ".context" / ".gitignore").read_text(encoding="utf-8").splitlines()


def _ignored(root: Path, rel: str) -> bool:
    result = subprocess.run(
        [_GIT, "check-ignore", "-q", rel], cwd=root, capture_output=True
    )
    return result.returncode == 0


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if _GIT is None:
        pytest.skip("git not installed")
    subprocess.run([_GIT, "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".context").mkdir()
    return tmp_path


def test_write_stash_adds_anchored_toolkit_rule_when_missing(repo: Path) -> None:
    (repo / ".context" / ".gitignore").write_text("cache/\n", encoding="utf-8")

    write_stash(project_layout(repo), [])

    assert "/toolkit/" in _gitignore(repo)


def test_write_stash_ignores_stash_but_not_feature_docs(repo: Path) -> None:
    feature = repo / ".context" / "features" / "toolkit" / "spec.md"
    feature.parent.mkdir(parents=True)
    feature.write_text("# spec\n", encoding="utf-8")

    write_stash(project_layout(repo), [])

    assert _ignored(repo, ".context/toolkit/disabled.json") is True
    assert _ignored(repo, ".context/features/toolkit/spec.md") is False


def test_unanchored_toolkit_rule_is_replaced(repo: Path) -> None:
    (repo / ".context" / ".gitignore").write_text(
        "cache/\ntoolkit/\n", encoding="utf-8"
    )

    write_stash(project_layout(repo), [])

    lines = _gitignore(repo)
    assert "toolkit/" not in lines
    assert lines.count("/toolkit/") == 1


def test_write_session_backup_guards_project_backup_dir(repo: Path) -> None:
    host = repo / ".mcp.json"
    host.write_text("{}\n", encoding="utf-8")
    backup_dir = repo / ".context" / "toolkit" / "backups"

    WriteSession(backup_dir=backup_dir).backup(host)

    assert "/toolkit/" in _gitignore(repo)


def test_preserve_skill_guards_project_backup_root(repo: Path) -> None:
    skill = repo / ".claude" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# demo\n", encoding="utf-8")

    preserve_skill(project_layout(repo), skill, "demo")

    assert "/toolkit/" in _gitignore(repo)
