"""`dummyindex context migrate-docs` — the wire-only doc-migration CLI.

These exercise `cli/migrate_docs.py:run` **in-process** (the `migrate-docs` verb
is not yet registered in the `context` dispatcher — that lands in a later wave —
so we import `run` directly rather than shell out). The move mechanics are
unit-tested in `tests/context/domains/docguard/`; here we pin the *wiring*: flag
parsing, dry-run-vs-`--yes`, the deterministic sorted listing, the `--json`
exact key sets, exit codes, and idempotency.

A synthetic repo is built under `tmp_path` (never this repo's mutable contents):
a `.context/` skeleton plus a `docs/` tree carrying stray planning docs. A real
`git init` backs the `--yes` path (the one place a real `git` is needed) so the
tracked-source `git mv` rename is observable in `git status --porcelain`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli.migrate_docs import run

# Slugs the fixture strays resolve to, in their deterministic sorted order
# (group_strays walks buckets sorted by (directory, pairing_stem)):
#   docs/internal/audits/cache-REPORT.md  -> audit    "cache-report"
#   docs/plans/2026-06-09-cache.md        -> proposal "2026-06-09-cache"
#   docs/specs/2026-06-08-widget-design.md+ -> proposal "2026-06-08-widget"
_AUDIT_SLUG = "cache-report"
_PLAN_SLUG = "2026-06-09-cache"
_WIDGET_SLUG = "2026-06-08-widget"


# ----- fixture helpers ------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _make_context(repo_root: Path) -> Path:
    """Create the `.context/` skeleton; return the `.context/` dir."""
    context_dir = repo_root / ".context"
    (context_dir / "proposals").mkdir(parents=True)
    (context_dir / "audits").mkdir(parents=True)
    return context_dir


def _seed_strays(repo_root: Path) -> None:
    """Write the stray planning-doc tree plus a published-guide negative control."""
    specs = repo_root / "docs" / "specs"
    specs.mkdir(parents=True)
    # A paired spec+plan under docs/specs → ONE group, two moves.
    (specs / "2026-06-08-widget-design.md").write_text(
        "# Widget design\n\nThe spec body.\n", encoding="utf-8"
    )
    (specs / "2026-06-08-widget.md").write_text(
        "# Widget plan\n\nThe plan body.\n", encoding="utf-8"
    )
    # A lone plan under docs/plans → ONE group, one move (plan.md).
    plans = repo_root / "docs" / "plans"
    plans.mkdir(parents=True)
    (plans / "2026-06-09-cache.md").write_text(
        "# Cache plan\n\nA lone plan.\n", encoding="utf-8"
    )
    # A lone audit report under docs/internal/audits → ONE group → report.md.
    audits = repo_root / "docs" / "internal" / "audits"
    audits.mkdir(parents=True)
    (audits / "cache-REPORT.md").write_text(
        "# Cache audit\n\nFindings.\n", encoding="utf-8"
    )
    # Negative control: a published guide doc that must NEVER move.
    guide = repo_root / "docs" / "guide"
    guide.mkdir(parents=True)
    (guide / "01-intro.md").write_text(
        "# Intro\n\nUser-facing, never a stray.\n", encoding="utf-8"
    )


def _init_git_repo(repo_root: Path) -> None:
    """`git init` + commit the seeded `docs/` so the strays are *tracked*."""
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test")
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-qm", "seed docs")


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Path → bytes for every regular file under `root` (excluding `.git/`)."""
    snap: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            snap[path.relative_to(root).as_posix()] = path.read_bytes()
    return snap


# ----- dry-run (default) ----------------------------------------------------


@pytest.mark.integration
def test_dry_run_lists_groups_sorted_and_moves_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)
    _seed_strays(tmp_path)
    before = _tree_snapshot(tmp_path)

    code = run(["--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "dry-run" in out
    assert "pass --yes" in out
    # Every stray group is listed by slug + target home.
    assert _AUDIT_SLUG in out
    assert _PLAN_SLUG in out
    assert _WIDGET_SLUG in out
    assert ".context/audits/cache-report" in out
    assert ".context/proposals/2026-06-08-widget/spec.md" in out
    # Deterministic sorted order: audit, then plans, then specs group.
    assert out.index(_AUDIT_SLUG) < out.index(_PLAN_SLUG) < out.index(_WIDGET_SLUG)

    # The headline acceptance: a dry-run moves *nothing* — tree before == after.
    assert _tree_snapshot(tmp_path) == before


@pytest.mark.integration
def test_dry_run_json_pins_exact_key_sets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)
    _seed_strays(tmp_path)

    code = run(["--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)

    # Top-level key set is fixed (gc `_status_payload` discipline).
    assert set(payload) == {"dry_run", "groups", "skipped"}
    assert payload["dry_run"] is True
    assert payload["skipped"] == []

    # Per-group + per-move key sets are fixed.
    assert len(payload["groups"]) == 3
    for group in payload["groups"]:
        assert set(group) == {"slug", "kind", "home", "title", "moves"}
        for move in group["moves"]:
            assert set(move) == {"source", "target", "method"}
            # Dry-run: nothing executed, so every method is empty.
            assert move["method"] == ""

    by_slug = {g["slug"]: g for g in payload["groups"]}
    assert set(by_slug) == {_AUDIT_SLUG, _PLAN_SLUG, _WIDGET_SLUG}
    assert by_slug[_AUDIT_SLUG]["kind"] == "audit"
    assert by_slug[_AUDIT_SLUG]["home"] == ".context/audits/cache-report"
    assert by_slug[_WIDGET_SLUG]["kind"] == "proposal"
    # Paired spec+plan → two moves under the one slug.
    widget_targets = {m["target"] for m in by_slug[_WIDGET_SLUG]["moves"]}
    assert widget_targets == {
        ".context/proposals/2026-06-08-widget/spec.md",
        ".context/proposals/2026-06-08-widget/plan.md",
    }


@pytest.mark.integration
def test_no_strays_reports_nothing_to_migrate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)
    # docs/ holds only a published guide doc — no strays.
    guide = tmp_path / "docs" / "guide"
    guide.mkdir(parents=True)
    (guide / "01-intro.md").write_text("# Intro\n", encoding="utf-8")

    code = run(["--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "nothing to migrate" in out


# ----- --yes (end-to-end) ---------------------------------------------------


@pytest.mark.integration
def test_yes_relocates_tracked_strays_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)
    _seed_strays(tmp_path)
    _init_git_repo(tmp_path)
    context_dir = tmp_path / ".context"

    code = run(["--root", str(tmp_path), "--yes"])
    out = capsys.readouterr().out

    assert code == 0
    assert "moved" in out

    # Sources are gone; targets exist under the managed homes.
    assert not (tmp_path / "docs" / "specs" / "2026-06-08-widget-design.md").exists()
    assert not (tmp_path / "docs" / "plans" / "2026-06-09-cache.md").exists()
    assert not (tmp_path / "docs" / "internal" / "audits" / "cache-REPORT.md").exists()

    widget_home = context_dir / "proposals" / _WIDGET_SLUG
    assert (widget_home / "spec.md").read_text(encoding="utf-8") == (
        "# Widget design\n\nThe spec body.\n"
    )
    assert (widget_home / "plan.md").exists()
    assert (context_dir / "proposals" / _PLAN_SLUG / "plan.md").exists()

    # The migrated proposal.json round-trips through the store reader at a
    # terminal status (so the hygiene GC won't read it as in-flight).
    from dummyindex.context.domains.proposals import ProposalStatus, read_proposal

    prop = read_proposal(context_dir, _WIDGET_SLUG)
    assert prop.slug == _WIDGET_SLUG
    assert prop.status is ProposalStatus.DONE
    assert prop.title == "Widget design"

    # The audit lands as a well-formed workspace with the report relocated.
    audit_home = context_dir / "audits" / _AUDIT_SLUG
    assert (audit_home / "audit.json").exists()
    assert (audit_home / "report.md").read_text(encoding="utf-8") == (
        "# Cache audit\n\nFindings.\n"
    )

    # A tracked source moved via `git mv` shows as a staged rename in the index
    # (R …), distinguishing it from a delete+create.
    porcelain = _git(tmp_path, "status", "--porcelain")
    rename_lines = [ln for ln in porcelain.splitlines() if ln.startswith("R")]
    assert any(
        ".context/proposals/2026-06-08-widget/spec.md" in ln for ln in rename_lines
    ), porcelain

    # Negative control: the published guide doc is byte-identical and unmoved.
    assert (tmp_path / "docs" / "guide" / "01-intro.md").read_text(
        encoding="utf-8"
    ) == "# Intro\n\nUser-facing, never a stray.\n"


@pytest.mark.integration
def test_yes_json_marks_executed_methods(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)
    _seed_strays(tmp_path)
    _init_git_repo(tmp_path)

    code = run(["--root", str(tmp_path), "--yes", "--json"])
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert set(payload) == {"dry_run", "groups", "skipped"}
    assert payload["dry_run"] is False
    # Every executed move records how it ran; tracked sources use `git mv`.
    methods = {move["method"] for group in payload["groups"] for move in group["moves"]}
    assert methods == {"git-mv"}


@pytest.mark.integration
def test_second_yes_is_idempotent_nothing_to_migrate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_context(tmp_path)
    _seed_strays(tmp_path)
    _init_git_repo(tmp_path)

    assert run(["--root", str(tmp_path), "--yes"]) == 0
    capsys.readouterr()  # drain first-run output

    after_first = _tree_snapshot(tmp_path)
    code = run(["--root", str(tmp_path), "--yes"])
    out = capsys.readouterr().out

    assert code == 0
    assert "nothing to migrate" in out
    # The second run touched nothing.
    assert _tree_snapshot(tmp_path) == after_first


# ----- exit codes / usage ---------------------------------------------------


@pytest.mark.unit
def test_unknown_arg_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    code = run(["--bogus"])
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
    assert "--bogus" in err


@pytest.mark.integration
def test_missing_context_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A directory with no .context/ at all — migration relocates *into* it, so a
    # missing index is a clean usage error (mirrors `gc`).
    code = run(["--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2
    assert "not found" in err
