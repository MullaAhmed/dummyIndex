"""Tests for the scope-vs-output-root decoupling.

Bug fixed by these tests: `cd /repo && dummyindex ingest app` used to write
`.context/` + `CLAUDE.md` to `/repo/app/`, leaving a duplicate CLAUDE.md
alongside the real one at `/repo/CLAUDE.md`. The fix is in
`dummyindex.context.cli._resolve_context_root`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.cli import _resolve_context_root, dispatch


# ----- pure-function tests ---------------------------------------------------


@pytest.mark.unit
def test_relative_subdir_uses_cwd_as_root(tmp_path: Path) -> None:
    """`dummyindex ingest app` from /repo writes to /repo, not /repo/app."""
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    out_root = _resolve_context_root(Path("app"), cwd=repo)
    assert out_root == repo.resolve()


@pytest.mark.unit
def test_absolute_subdir_treated_as_explicit_root(tmp_path: Path) -> None:
    """An absolute path is always taken at face value, even if it's under cwd."""
    repo = tmp_path / "repo"
    sub = repo / "app"
    sub.mkdir(parents=True)
    out_root = _resolve_context_root(sub, cwd=repo)
    assert out_root == sub.resolve()


@pytest.mark.unit
def test_dot_scope_resolves_to_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    out_root = _resolve_context_root(Path("."), cwd=repo)
    assert out_root == repo.resolve()


@pytest.mark.unit
def test_explicit_root_always_wins(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    sub = repo / "app"
    sub.mkdir(parents=True)
    explicit = repo / "other"
    explicit.mkdir()
    out_root = _resolve_context_root(
        Path("app"), explicit_root=explicit, cwd=repo
    )
    assert out_root == explicit.resolve()


@pytest.mark.unit
def test_scope_outside_cwd_uses_scope(tmp_path: Path) -> None:
    """If the user is at /home but ingests /tmp/foo, output goes to /tmp/foo."""
    home = tmp_path / "home"
    foo = tmp_path / "tmp" / "foo"
    home.mkdir()
    foo.mkdir(parents=True)
    out_root = _resolve_context_root(foo, cwd=home)
    assert out_root == foo.resolve()


# ----- end-to-end via dispatch ----------------------------------------------


@pytest.mark.integration
def test_ingest_relative_subdir_writes_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: cd into repo, ingest a subdir — .context lands at repo root."""
    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("def run():\n    return 42\n", encoding="utf-8")

    monkeypatch.chdir(repo)
    rc = dispatch(["init", "app"])
    assert rc == 0

    assert (repo / ".context").is_dir(), ".context must land at repo root"
    assert (repo / ".claude" / "CLAUDE.md").is_file(), "CLAUDE.md must land in repo/.claude/"
    assert not (repo / "CLAUDE.md").exists(), "CLAUDE.md must not be written at repo root"
    assert not (app / ".context").exists(), ".context must NOT leak into the subdir"
    assert not (app / "CLAUDE.md").exists(), "CLAUDE.md must NOT leak into the subdir"
    assert not (app / ".claude" / "CLAUDE.md").exists(), ".claude/CLAUDE.md must NOT leak into the subdir"


@pytest.mark.integration
def test_ingest_subdir_paths_are_relative_to_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tree.json / map paths must be relative to the *output root*, not the scope."""
    import json

    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    monkeypatch.chdir(repo)
    assert dispatch(["init", "app"]) == 0

    files = json.loads((repo / ".context" / "map" / "files.json").read_text())
    paths = [f["path"] for f in files["files"]]
    assert "app/main.py" in paths, f"expected app/main.py, got {paths}"


@pytest.mark.integration
def test_explicit_root_flag_overrides_smart_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("def run(): pass\n", encoding="utf-8")

    monkeypatch.chdir(repo)
    rc = dispatch(["init", "app", "--root", str(app)])
    assert rc == 0
    # With --root, .context lands at the override location (the subdir).
    assert (app / ".context").is_dir()
    assert (app / ".claude" / "CLAUDE.md").is_file()
    assert not (app / "CLAUDE.md").exists()
    # And NOT at the repo root.
    assert not (repo / ".context").exists()
    assert not (repo / "CLAUDE.md").exists()
    assert not (repo / ".claude" / "CLAUDE.md").exists()


@pytest.mark.integration
def test_absolute_scope_does_not_smart_default_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cd /tmp && dummyindex ingest /tmp/proj` → .context goes to /tmp/proj, NOT /tmp."""
    parent = tmp_path / "parent"
    proj = parent / "proj"
    proj.mkdir(parents=True)
    (proj / "a.py").write_text("def f(): pass\n", encoding="utf-8")

    monkeypatch.chdir(parent)
    rc = dispatch(["init", str(proj)])
    assert rc == 0
    assert (proj / ".context").is_dir()
    assert not (parent / ".context").exists()


@pytest.mark.integration
def test_enrich_plan_on_subdir_finds_repo_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After ingesting from inside a repo, `enrich-plan app` must locate
    `.context/` at the repo root, not look for `app/.context/`."""
    repo = tmp_path / "repo"
    app = repo / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("def run(): pass\n", encoding="utf-8")

    monkeypatch.chdir(repo)
    assert dispatch(["init", "app"]) == 0
    rc = dispatch(["enrich-plan", "app"])
    assert rc == 0
    assert (repo / ".context" / "_enrich_plan.json").exists()
