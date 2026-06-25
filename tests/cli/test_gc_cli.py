"""`dummyindex context gc status|delete|stamp|signal` — the wire-only GC CLI.

These exercise the CLI surface end-to-end through ``dispatch(["gc", ...])``,
against a synthetic ``.context/`` built under ``tmp_path`` (never this repo's
mutable contents). The domain logic is unit-tested in
``tests/context/domains/gc/``; here we pin the *wiring*: verb dispatch, flag
parsing, exit codes (2 on a guard / usage violation, 0 otherwise), the
``--json`` payload shape, dry-run vs ``--yes``, and the session-id-driven
``signal`` throttle.

A real ``git init`` repo under ``tmp_path`` backs the tracked/untracked,
commit-throttle, and stamp cases — the one place a real ``git`` is needed.
``--root <tmp_path>`` makes ``context_dir.parent`` the repo root, mirroring the
real layout the git probes assume.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch

_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

# A complete checklist — liveness must NOT refuse a delete of this proposal.
_CHECKLIST_DONE = (
    "# Checklist — done\n\n- [x] First item done.\n- [x] Second item done.\n"
)
# A partial checklist — liveness MUST refuse without --force-partial.
_CHECKLIST_PARTIAL = (
    "# Checklist — partial\n\n- [x] First item done.\n- [ ] Second still open.\n"
)


# ----- fixture helpers ------------------------------------------------------


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_repo(tmp_path: Path) -> Path:
    """`tmp_path` as a real git repo; return its ``.context/`` dir."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    context_dir = tmp_path / ".context"
    (context_dir / "proposals").mkdir(parents=True)
    (context_dir / "audits").mkdir(parents=True)
    return context_dir


def _write_proposal(
    context_dir: Path,
    slug: str,
    *,
    status: str = "done",
    checklist: str = _CHECKLIST_DONE,
) -> Path:
    workspace = context_dir / "proposals" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "proposal.json").write_text(
        json.dumps({"slug": slug, "title": slug, "status": status}, indent=2) + "\n",
        encoding="utf-8",
    )
    (workspace / "checklist.md").write_text(checklist, encoding="utf-8")
    return workspace


def _write_audit(context_dir: Path, slug: str, *, report: bool = True) -> Path:
    workspace = context_dir / "audits" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "audit.json").write_text(
        json.dumps({"slug": slug}, indent=2) + "\n", encoding="utf-8"
    )
    if report:
        (workspace / "report.md").write_text("# findings\n", encoding="utf-8")
    return workspace


def _commit_all(tmp_path: Path, message: str = "fixture") -> str:
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", message)
    return _git(tmp_path, "rev-parse", "HEAD").strip()


# ----- gc status ------------------------------------------------------------


@pytest.mark.integration
def test_status_human_lists_candidates_with_signals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    _write_proposal(context_dir, "live-feature", status="done")
    _write_audit(context_dir, "cache-audit", report=True)
    archive = context_dir / "proposals" / "_archive" / "old-thing"
    archive.mkdir(parents=True)
    (archive / "spec.md").write_text("archived\n", encoding="utf-8")
    _commit_all(tmp_path)

    code = dispatch(["gc", "status", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "live-feature" in out
    assert "cache-audit" in out
    assert "report-written" in out
    assert "old-thing" in out  # the _archive child surfaces as a candidate
    assert "archived" in out  # its kind label
    assert "threshold=10" in out


@pytest.mark.integration
def test_status_json_emits_expected_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    _write_proposal(context_dir, "feat", status="planned", checklist=_CHECKLIST_PARTIAL)
    _commit_all(tmp_path)

    code = dispatch(["gc", "status", "--json", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert set(payload) == {
        "candidates",
        "anchor",
        "commits_since",
        "threshold",
        "should_signal",
        "anchor_orphaned",
    }
    assert payload["threshold"] == 10
    assert payload["should_signal"] is False  # no anchor → no commits_since
    (cand,) = payload["candidates"]
    assert set(cand) == {
        "kind",
        "slug",
        "rel_path",
        "status",
        "signals",
        "tracked",
        "age_days",
    }
    assert cand["slug"] == "feat"
    assert cand["kind"] == "proposal"
    assert cand["status"] == "planned"
    assert "checklist-partial" in cand["signals"]


@pytest.mark.integration
def test_status_surfaces_anchor_orphaned_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path)
    # Record an anchor unknown to the repo (a history rewrite orphaned it).
    state = context_dir / "gc" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"anchor": "0123456789abcdef0123456789abcdef01234567"}),
        encoding="utf-8",
    )

    code = dispatch(["gc", "status", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "re-baseline" in out
    assert "gc stamp --to HEAD" in out


# ----- gc delete ------------------------------------------------------------


@pytest.mark.integration
def test_delete_without_yes_is_dry_run_deletes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "stale-plan")
    _commit_all(tmp_path)

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "stale-plan",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "dry-run" in out
    assert workspace.exists(), "dry-run must not delete anything"


@pytest.mark.integration
def test_delete_with_yes_removes_the_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "stale-plan")
    _commit_all(tmp_path)

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "stale-plan",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "removed" in out
    assert not workspace.exists()


@pytest.mark.integration
def test_delete_traversal_slug_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "../../etc",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err


@pytest.mark.integration
def test_delete_archive_sentinel_slug_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    archive = context_dir / "proposals" / "_archive" / "child"
    archive.mkdir(parents=True)
    (archive / "spec.md").write_text("archived\n", encoding="utf-8")
    _commit_all(tmp_path)

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "_archive",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
    assert (context_dir / "proposals" / "_archive").exists()


@pytest.mark.integration
def test_delete_partial_proposal_refused_without_force_partial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "half", checklist=_CHECKLIST_PARTIAL)
    _commit_all(tmp_path)

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "half",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "error:" in err
    assert workspace.exists()


@pytest.mark.integration
def test_delete_missing_target_exits_0_nothing_to_delete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "never-existed",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "nothing to delete" in out


@pytest.mark.integration
def test_delete_untracked_refused_without_allow_untracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    # Never committed → untracked → recoverability refusal (exit 0, a guard
    # outcome, not a usage error).
    workspace = _write_proposal(context_dir, "scratch")

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "scratch",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "refused" in out
    assert workspace.exists()


@pytest.mark.integration
def test_delete_untracked_removed_with_allow_untracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "scratch")

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "scratch",
            "--yes",
            "--allow-untracked",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "removed" in out
    assert not workspace.exists()


@pytest.mark.integration
def test_delete_requires_kind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    code = dispatch(["gc", "delete", "--slug", "x", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2
    assert "--kind" in err


@pytest.mark.integration
def test_delete_requires_slug_or_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    code = dispatch(["gc", "delete", "--kind", "proposal", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2
    assert "--slug" in err or "--path" in err


# ----- gc stamp -------------------------------------------------------------


@pytest.mark.integration
def test_stamp_writes_anchor_and_zeroes_commits_since(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    _write_proposal(context_dir, "feat")
    head = _commit_all(tmp_path)

    code = dispatch(["gc", "stamp", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert head in out

    # The committed anchor lands at .context/gc/state.json.
    state = json.loads((context_dir / "gc" / "state.json").read_text(encoding="utf-8"))
    assert state == {"anchor": head}

    # A subsequent status reports commits_since == 0 (anchor == HEAD).
    dispatch(["gc", "status", "--json", "--root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["commits_since"] == 0


# ----- gc signal ------------------------------------------------------------


@pytest.mark.integration
def test_signal_emits_over_threshold_then_silent_same_session(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_dir = _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    # Anchor far enough back that the default threshold (10) is crossed.
    state = context_dir / "gc" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"anchor": anchor}), encoding="utf-8")
    for i in range(10):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    monkeypatch.setenv(_SESSION_ENV, "session-A")

    code = dispatch(["gc", "signal", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "commits since last hygiene sweep" in out
    assert "/dummyindex-gc" in out

    # Same session id → fire-once memo suppresses the second call (silent).
    code2 = dispatch(["gc", "signal", "--root", str(tmp_path)])
    out2 = capsys.readouterr().out
    assert code2 == 0
    assert out2.strip() == ""


@pytest.mark.integration
def test_signal_silent_under_threshold(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_dir = _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    state = context_dir / "gc" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"anchor": anchor}), encoding="utf-8")
    # Only 2 commits past the anchor — well under the default threshold of 10.
    for i in range(2):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    monkeypatch.setenv(_SESSION_ENV, "session-B")

    code = dispatch(["gc", "signal", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == ""


# ----- verb dispatch / usage ------------------------------------------------


@pytest.mark.unit
def test_unknown_verb_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = dispatch(["gc", "frobnicate", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2
    assert "unknown gc verb" in err


@pytest.mark.unit
def test_no_verb_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    code = dispatch(["gc"])
    err = capsys.readouterr().err
    assert code == 2
    assert "usage:" in err


@pytest.mark.integration
def test_status_missing_context_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A directory with no .context/ at all.
    code = dispatch(["gc", "status", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2
    assert "not found" in err
