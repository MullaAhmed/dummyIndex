"""`dummyindex context gc status|delete|closeout|stamp|signal` — the wire-only GC CLI.

Drives ``dispatch(["gc", ...])`` on a synthetic ``tmp_path`` ``.context/``
(never this repo's) and pins the wiring: verbs, flags, exit codes (2 on a guard
or usage violation, else 0), the ``--json`` shape, dry-run vs ``--yes``, and the
``signal`` throttle. A real ``git init`` backs the tracked, throttle and stamp
cases; ``--root <tmp_path>`` makes ``context_dir.parent`` the repo root.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.proposals.retirement import workspace_inventory

_SESSION_ENV = "CLAUDE_CODE_SESSION_ID"

# A complete checklist — liveness must NOT refuse a delete of this proposal.
_CHECKLIST_DONE = (
    "# Checklist — done\n\n- [x] First item done.\n- [x] Second item done.\n"
)
# A partial checklist — liveness MUST refuse without --force-partial.
_CHECKLIST_PARTIAL = (
    "# Checklist — partial\n\n- [x] First item done.\n- [ ] Second still open.\n"
)


# --- fixture helpers


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


def _fill_draft(draft: Path) -> None:
    """Give every empty discard reason in a closeout draft a value."""
    data = json.loads(draft.read_text(encoding="utf-8"))
    for key in data["discarded"]:
        data["discarded"][key] = "obsolete"
    draft.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _closed_out(tmp_path: Path, context_dir: Path, slug: str) -> Path:
    """A committed, closeout-receipted proposal; return its workspace."""
    workspace = _write_proposal(context_dir, slug, status="planned")
    (workspace / "notes.md").write_text("notes\n", encoding="utf-8")
    (context_dir / "INDEX.md").write_text(
        f"- .context/proposals/{slug}/notes.md\n", encoding="utf-8"
    )
    _commit_all(tmp_path)
    assert (
        dispatch(
            [
                "gc",
                "closeout",
                "--draft",
                "--kind",
                "proposal",
                "--slug",
                slug,
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    draft = context_dir / "cache" / "gc" / f"closeout-proposal-{slug}.json"
    _fill_draft(draft)
    assert (
        dispatch(
            [
                "gc",
                "closeout",
                "--kind",
                "proposal",
                "--slug",
                slug,
                "--manifest",
                str(draft),
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    _commit_all(tmp_path)
    return workspace


def _orphan_anchor(tmp_path: Path) -> Path:
    """A repo whose recorded anchor is unknown to it; return ``.context/``."""
    context_dir = _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path)
    state = context_dir / "gc" / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"anchor": "0123456789abcdef0123456789abcdef01234567"}),
        encoding="utf-8",
    )
    return context_dir


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
        "summary",
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
        "recommendation",
        "reason",
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


@pytest.mark.integration
def test_status_recommends_an_action_per_candidate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    _write_proposal(context_dir, "gone", status="done")
    receipts = context_dir / "gc" / "closeouts"
    receipts.mkdir(parents=True)
    (receipts / "proposal-gone.json").write_text("{}\n", encoding="utf-8")
    _write_proposal(context_dir, "finished", status="planned")
    archive = context_dir / "proposals" / "_archive" / "old"
    archive.mkdir(parents=True)
    (archive / "spec.md").write_text("archived\n", encoding="utf-8")
    _write_proposal(
        context_dir, "active", status="in_progress", checklist=_CHECKLIST_PARTIAL
    )
    _commit_all(tmp_path)

    code = dispatch(["gc", "status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert (
        "context gc status: 4 candidate(s): 1 delete, 1 close, 1 review, 1 keep" in out
    )
    assert "-> close:" in out

    code = dispatch(["gc", "status", "--json", "--root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["summary"] == {"delete": 1, "close": 1, "review": 1, "keep": 1}


@pytest.mark.integration
def test_status_empty_reports_nothing_to_retire(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)

    code = dispatch(["gc", "status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "context gc status: ran, nothing to retire" in out


@pytest.mark.integration
def test_status_all_keep_reports_nothing_to_retire(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    _write_proposal(
        context_dir, "active", status="in_progress", checklist=_CHECKLIST_PARTIAL
    )
    _commit_all(tmp_path)

    code = dispatch(["gc", "status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "context gc status: ran, nothing to retire" in out


# ----- gc delete ------------------------------------------------------------


@pytest.mark.integration
def test_delete_dry_run_without_receipt_is_guard_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "material")
    (workspace / "notes.md").write_text("lesson\n", encoding="utf-8")
    _commit_all(tmp_path)

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "material",
            "--root",
            str(tmp_path),
        ]
    )
    err = capsys.readouterr().err

    assert code == 2
    assert "knowledge review/closeout receipt required" in err
    assert workspace.exists()


@pytest.mark.integration
def test_delete_dry_run_closed_out_reports_would_delete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _closed_out(tmp_path, context_dir, "shipped")
    before = workspace_inventory(workspace)

    code = dispatch(
        [
            "gc",
            "delete",
            "--kind",
            "proposal",
            "--slug",
            "shipped",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "context gc delete (dry-run): would delete proposal --slug" in out
    assert "pass --yes to delete (nothing removed)" in out
    assert workspace_inventory(workspace) == before


@pytest.mark.integration
def test_delete_dry_run_untracked_refused(
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
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "refused" in out
    assert workspace.exists()


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


# ----- gc closeout ----------------------------------------------------------


@pytest.mark.integration
def test_closeout_draft_never_overwrites_and_rejects_bad_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    _write_proposal(context_dir, "drafted", status="planned")
    _commit_all(tmp_path)
    draft_args = [
        "gc",
        "closeout",
        "--kind",
        "proposal",
        "--slug",
        "drafted",
        "--draft",
        "--root",
        str(tmp_path),
    ]
    assert dispatch(draft_args) == 0
    draft = context_dir / "cache" / "gc" / "closeout-proposal-drafted.json"
    first = draft.read_bytes()
    capsys.readouterr()

    assert dispatch(draft_args) == 2
    assert "draft exists" in capsys.readouterr().err
    assert draft.read_bytes() == first

    bad_slug = [*draft_args[:5], "../x", *draft_args[6:]]
    assert dispatch(bad_slug) == 2
    missing = [*draft_args[:5], "nope", *draft_args[6:]]
    assert dispatch(missing) == 2
    both = [*draft_args, "--manifest", str(draft)]
    assert dispatch(both) == 2


@pytest.mark.integration
def test_closeout_flow_status_to_gc_delete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context_dir = _init_repo(tmp_path)
    workspace = _write_proposal(context_dir, "retire-me", status="planned")
    (workspace / "notes.md").write_text("notes\n", encoding="utf-8")
    (context_dir / "INDEX.md").write_text(
        "- .context/proposals/retire-me/notes.md\n", encoding="utf-8"
    )
    _commit_all(tmp_path)

    assert dispatch(["gc", "status", "--root", str(tmp_path)]) == 0
    assert "-> close:" in capsys.readouterr().out

    assert (
        dispatch(
            [
                "gc",
                "closeout",
                "--draft",
                "--kind",
                "proposal",
                "--slug",
                "retire-me",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    draft = context_dir / "cache" / "gc" / "closeout-proposal-retire-me.json"
    assert draft.exists()
    _fill_draft(draft)

    assert (
        dispatch(
            [
                "gc",
                "closeout",
                "--kind",
                "proposal",
                "--slug",
                "retire-me",
                "--manifest",
                str(draft),
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    _commit_all(tmp_path)

    assert (
        dispatch(
            [
                "gc",
                "delete",
                "--kind",
                "proposal",
                "--slug",
                "retire-me",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "would delete" in capsys.readouterr().out

    assert (
        dispatch(
            [
                "gc",
                "delete",
                "--kind",
                "proposal",
                "--slug",
                "retire-me",
                "--yes",
                "--root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert not workspace.exists()
    assert (context_dir / "gc" / "closeouts" / "proposal-retire-me.json").exists()


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


# --- gc signal


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


@pytest.mark.integration
def test_signal_nudges_on_orphaned_anchor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _orphan_anchor(tmp_path)
    monkeypatch.setenv(_SESSION_ENV, "s-orph")

    code = dispatch(["gc", "signal", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert (
        "GC anchor orphaned (history rewrite) — run /dummyindex-gc, "
        "then gc stamp --to HEAD" in out
    )


@pytest.mark.integration
def test_status_json_orphaned_anchor_should_signal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _orphan_anchor(tmp_path)

    code = dispatch(["gc", "status", "--json", "--root", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["should_signal"] is True


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
