"""Tests for ``context/build/reconcile.py`` — read-only drift detection.

Builds a tiny ``.context/`` + throwaway git repo under ``tmp_path`` by hand
so the mapping logic (changed file → owning feature, net-new → unassigned)
is exercised in isolation, without a full build_all.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.build.reconcile import (
    AnchorStatus,
    ReconcileReport,
    compute_reconcile_report,
    stamp_reconciled,
)
from dummyindex.context.domains.features import PENDING_ENRICHMENT_MARKER


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_index(context_dir: Path, indexed_commit: str | None) -> None:
    """Minimal meta.json + one feature owning ``auth.py``."""
    meta = {
        "schema_version": 1,
        "dummyindex_version": "0.15.2",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "root": str(context_dir.parent),
    }
    if indexed_commit is not None:
        meta["indexed_commit"] = indexed_commit
    _write_json(context_dir / "meta.json", meta)
    _write_json(
        context_dir / "features" / "auth" / "feature.json",
        {
            "schema_version": 1,
            "feature_id": "auth",
            "kind": "community",
            "name": "Authentication",
            "files": ["auth.py"],
        },
    )


@pytest.mark.unit
def test_no_indexed_commit_yields_empty_report(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    report = compute_reconcile_report(context_dir, tmp_path)
    assert report == ReconcileReport(indexed_commit=None)
    assert report.has_drift is False


@pytest.mark.unit
def test_non_git_with_anchor_degrades_to_empty(tmp_path: Path) -> None:
    # An anchor is recorded but the dir isn't a git repo → changed_paths
    # returns None → empty report, no raise.
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit="deadbeef")
    report = compute_reconcile_report(context_dir, tmp_path)
    assert report.drifted_features == ()
    assert report.unassigned_new_files == ()
    assert report.indexed_commit == "deadbeef"


@pytest.mark.unit
def test_changed_file_maps_to_owning_feature(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)

    # Modify the owned file and add a net-new file owned by nobody.
    (tmp_path / "auth.py").write_text("def login(): return True\n", encoding="utf-8")
    (tmp_path / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    report = compute_reconcile_report(context_dir, tmp_path)
    assert "auth" in report.drifted_features
    assert "newthing.py" in report.unassigned_new_files
    assert report.indexed_commit == anchor


@pytest.mark.unit
def test_pending_enrichment_marker_surfaces_independently_of_git(
    tmp_path: Path,
) -> None:
    """A placed-but-unenriched feature is reported even off-git / sans anchor.

    The ``awaiting_enrichment`` set drives the ``reconcile-stamp`` guard, so it
    must be visible regardless of the git delta (which short-circuits to empty
    when there's no anchor). ``has_drift`` flips True so the report reads as
    "work pending".
    """
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    marker = context_dir / "features" / "auth" / PENDING_ENRICHMENT_MARKER
    marker.write_text("awaiting enrichment\n", encoding="utf-8")

    report = compute_reconcile_report(context_dir, tmp_path)
    assert report.awaiting_enrichment == ("auth",)
    assert report.has_drift is True


@pytest.mark.unit
def test_tool_paths_excluded_from_unassigned(tmp_path: Path) -> None:
    """dummyindex's own install footprint under .claude/ is never reported as
    unassigned work — neither untracked nor committed."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)

    # A committed agent file and an untracked skill file — both .claude-owned.
    skill = tmp_path / ".claude" / "skills" / "dummyindex" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("# skill\n", encoding="utf-8")
    agent = tmp_path / ".claude" / "agents" / "x.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_text("# agent\n", encoding="utf-8")
    _git(tmp_path, "add", ".claude/agents/x.md")
    _git(tmp_path, "commit", "-qm", "add agent")

    report = compute_reconcile_report(context_dir, tmp_path)
    assert ".claude/skills/dummyindex/SKILL.md" not in report.unassigned_new_files
    assert ".claude/agents/x.md" not in report.unassigned_new_files
    assert ".claude/agents/x.md" not in report.removed_files
    assert report.has_drift is False


@pytest.mark.unit
def test_tool_paths_do_not_refuse_stamp(tmp_path: Path) -> None:
    """A fresh skill/agent file must not block reconcile-stamp."""
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    skill = root / ".claude" / "skills" / "dummyindex" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text("# skill\n", encoding="utf-8")

    result = stamp_reconciled(context_dir, root)
    assert result.refused is False
    assert result.stamped_commit == head


@pytest.mark.unit
def test_reconcile_exclude_globs_filter_added_paths(tmp_path: Path) -> None:
    """A repo-specific glob in config hides matching added files; a
    non-matching source file is still reported."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)
    _write_json(
        context_dir / "config.json",
        {
            "schema_version": 1,
            "scope": "repo",
            "scope_path": None,
            "mode": "standard",
            "model": "sonnet-4.6",
            "auto_refresh_hook": True,
            "reconcile_exclude": ["docs/spikes/**"],
        },
    )

    spike = tmp_path / "docs" / "spikes" / "idea.py"
    spike.parent.mkdir(parents=True, exist_ok=True)
    spike.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "real.py").write_text("y = 2\n", encoding="utf-8")

    report = compute_reconcile_report(context_dir, tmp_path)
    assert "docs/spikes/idea.py" not in report.unassigned_new_files
    assert "real.py" in report.unassigned_new_files


@pytest.mark.unit
def test_context_deletion_does_not_self_drift(tmp_path: Path) -> None:
    """Deleting one of .context's own committed files is not drift (D6)."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    flow = tmp_path / ".context" / "flows" / "f.md"
    flow.parent.mkdir(parents=True, exist_ok=True)
    flow.write_text("# flow\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)
    flow.unlink()  # prune a .context doc

    report = compute_reconcile_report(context_dir, tmp_path)
    assert report.removed_files == ()
    assert report.has_drift is False


@pytest.mark.unit
def test_unknown_anchor_reports_orphaned_not_clean(tmp_path: Path) -> None:
    """An anchor SHA unknown to the repo must NOT read as 'in sync'."""
    root, _head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit="0" * 40)

    report = compute_reconcile_report(context_dir, root)
    assert report.anchor_status == AnchorStatus.MISSING_FROM_REPO
    assert report.anchor_broken is True
    assert report.has_drift is True


@pytest.mark.unit
def test_known_ancestor_anchor_is_ok(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    report = compute_reconcile_report(context_dir, root)
    assert report.anchor_status == AnchorStatus.OK
    assert report.anchor_broken is False


@pytest.mark.unit
def test_no_anchor_status_is_none(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    report = compute_reconcile_report(context_dir, tmp_path)
    assert report.anchor_status == AnchorStatus.NONE
    assert report.anchor_broken is False


@pytest.mark.unit
def test_removed_owned_file_drifts_feature_and_lists_removal(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    anchor = _git(tmp_path, "rev-parse", "HEAD").strip()

    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=anchor)

    (tmp_path / "auth.py").unlink()

    report = compute_reconcile_report(context_dir, tmp_path)
    assert "auth" in report.drifted_features
    assert "auth.py" in report.removed_files


# ----- stamp_reconciled (the transactional boundary) ------------------------


def _committed_repo(tmp_path: Path) -> tuple[Path, str]:
    """A git repo with ``auth.py`` committed; returns ``(root, head_sha)``."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "auth.py").write_text("def login(): ...\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path, _git(tmp_path, "rev-parse", "HEAD").strip()


def _anchor(context_dir: Path) -> str | None:
    return json.loads((context_dir / "meta.json").read_text(encoding="utf-8")).get(
        "indexed_commit"
    )


@pytest.mark.unit
def test_stamp_advances_anchor_when_clean(tmp_path: Path) -> None:
    root, first = _committed_repo(tmp_path)
    context_dir = root / ".context"
    # Anchor at a REAL ancestor commit (not an orphaned/unknown sha — that now
    # refuses, per the rebase-orphan guard). A clean delta from it advances.
    _seed_index(context_dir, indexed_commit=first)
    (root / "auth.py").write_text("def login(): return True\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second")
    head = _git(root, "rev-parse", "HEAD").strip()

    result = stamp_reconciled(context_dir, root)
    assert result.refused is False
    assert result.off_git is False
    assert result.stamped_commit == head
    assert _anchor(context_dir) == head


@pytest.mark.unit
def test_stamp_refused_on_unassigned_then_forced(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    # A net-new untracked file owned by nobody → unassigned → blocks.
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    refused = stamp_reconciled(context_dir, root)
    assert refused.refused is True
    assert refused.stamped_commit is None
    assert "newthing.py" in refused.report.unassigned_new_files
    assert _anchor(context_dir) == head  # unchanged

    forced = stamp_reconciled(context_dir, root, force=True)
    assert forced.refused is False
    assert forced.stamped_commit == head


@pytest.mark.unit
def test_stamp_refused_on_awaiting_enrichment(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (context_dir / "features" / "auth" / PENDING_ENRICHMENT_MARKER).write_text(
        "pending\n", encoding="utf-8"
    )

    result = stamp_reconciled(context_dir, root)
    assert result.refused is True
    assert "auth" in result.report.awaiting_enrichment


@pytest.mark.unit
def test_stamp_does_not_block_on_drift_only(tmp_path: Path) -> None:
    """Drift alone never blocks the stamp — only the stamp clears drift."""
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    # Modify the owned file → drifts `auth`, but no unassigned / awaiting.
    (root / "auth.py").write_text("def login(): return True\n", encoding="utf-8")

    result = stamp_reconciled(context_dir, root)
    assert result.refused is False
    assert result.stamped_commit == head
    assert "auth" in result.report.drifted_features
    assert result.dirty_source is True  # uncommitted source edit


@pytest.mark.unit
def test_stamp_off_git_is_noop(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _seed_index(context_dir, indexed_commit=None)
    result = stamp_reconciled(context_dir, tmp_path)
    assert result.off_git is True
    assert result.stamped_commit is None
    assert _anchor(context_dir) is None


# ----- CLI front-ends -------------------------------------------------------


@pytest.mark.integration
def test_cli_reconcile_json_lists_unassigned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile", str(root), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["indexed_commit"] == head
    assert "newthing.py" in payload["unassigned_new_files"]
    assert payload["has_drift"] is True


def _config_path_with(root: Path, **overrides: object) -> Path:
    """Write `.context/config.json` under ``root`` and return its path."""
    from dataclasses import replace

    from dummyindex.context.domains.config import default_config, write_config

    cfg = replace(default_config(), **overrides)
    return write_config(root / ".context", cfg)


@pytest.mark.integration
def test_cli_reconcile_depth_flag_surfaces_and_does_not_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--depth deep` overrides the configured mode for this run and surfaces in
    the hand-off, leaving `config.json` bytes untouched (one-run override)."""
    from dummyindex.context.domains.config import CouncilMode

    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    cfg_path = _config_path_with(root, mode=CouncilMode.LIGHT)
    before = cfg_path.read_bytes()
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile", str(root), "--depth", "deep"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "council depth: deep" in out  # flag beat the configured light
    assert cfg_path.read_bytes() == before  # config.json untouched


@pytest.mark.integration
def test_cli_reconcile_no_depth_uses_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no `--depth`, reconcile resolves the configured mode."""
    from dummyindex.context.domains.config import CouncilMode

    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    _config_path_with(root, mode=CouncilMode.DEEP)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile", str(root)])
    assert rc == 0
    assert "council depth: deep" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_reconcile_invalid_depth_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    _seed_index(root / ".context", indexed_commit=head)

    rc = dispatch(["reconcile", str(root), "--depth", "turbo"])
    assert rc == 2
    assert "light|standard|deep" in capsys.readouterr().err


@pytest.mark.unit
def test_stamp_refuses_orphaned_anchor_without_to(tmp_path: Path) -> None:
    """An orphaned (unknown) anchor must not silently advance to HEAD."""
    root, _head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit="0" * 40)

    result = stamp_reconciled(context_dir, root)
    assert result.refused is True
    assert result.stamped_commit is None
    assert _anchor(context_dir) == "0" * 40  # untouched


@pytest.mark.unit
def test_stamp_to_rebaselines_with_valid_sha(tmp_path: Path) -> None:
    """`reconcile-stamp --to <sha>` re-anchors to a verified commit."""
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit="0" * 40)  # orphaned

    result = stamp_reconciled(context_dir, root, to_commit=head)
    assert result.refused is False
    assert result.stamped_commit == head
    assert _anchor(context_dir) == head


@pytest.mark.unit
def test_stamp_to_rejects_bogus_sha(tmp_path: Path) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)

    result = stamp_reconciled(context_dir, root, to_commit="0" * 40)
    assert result.stamped_commit is None
    assert result.invalid_to is True
    assert _anchor(context_dir) == head  # nothing written


@pytest.mark.integration
def test_cli_reconcile_warns_on_orphaned_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit="0" * 40)

    rc = dispatch(["reconcile", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "in sync" not in out
    assert "rewritten" in out or "unknown to this repo" in out
    assert "reconcile-stamp --to" in out


@pytest.mark.integration
def test_cli_reconcile_no_anchor_advises_stamp_not_ingest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=None)

    rc = dispatch(["reconcile", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "reconcile-stamp" in out
    assert "fresh `dummyindex ingest`" not in out
    assert "in sync" not in out


@pytest.mark.integration
def test_cli_stamp_bootstrap_notice_when_no_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=None)

    rc = dispatch(["reconcile-stamp", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "anchor advanced" in out
    assert "commit-anchored tracking" in out or "predating this point" in out
    assert _anchor(context_dir) == head


@pytest.mark.integration
def test_cli_stamp_to_flag_rebaselines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit="0" * 40)

    rc = dispatch(["reconcile-stamp", str(root), "--to", head])
    assert rc == 0
    assert "anchor advanced" in capsys.readouterr().out
    assert _anchor(context_dir) == head


@pytest.mark.integration
def test_cli_stamp_to_bogus_sha_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)

    rc = dispatch(["reconcile-stamp", str(root), "--to", "0" * 40])
    assert rc == 2
    assert _anchor(context_dir) == head  # nothing written


@pytest.mark.integration
def test_cli_stamp_force_warning_wording(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The --force warning distinguishes committed vs untracked and points at
    reconcile_exclude, not the nonexistent 'stop tracking it' remedy."""
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile-stamp", str(root), "--force"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UNTRACKED" in out
    assert "reconcile_exclude" in out
    assert "stop tracking it" not in out


@pytest.mark.integration
def test_cli_stamp_refusal_names_resolving_verbs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")
    (context_dir / "features" / "auth" / PENDING_ENRICHMENT_MARKER).write_text(
        "pending\n", encoding="utf-8"
    )

    rc = dispatch(["reconcile-stamp", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "assign-files" in err or "scaffold-feature" in err
    assert "mark-enriched" in err


@pytest.mark.integration
def test_cli_reconcile_stamp_refuses_then_forces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, head = _committed_repo(tmp_path)
    context_dir = root / ".context"
    _seed_index(context_dir, indexed_commit=head)
    (root / "newthing.py").write_text("def fresh(): ...\n", encoding="utf-8")

    rc = dispatch(["reconcile-stamp", str(root)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err and "newthing.py" in err
    assert _anchor(context_dir) == head  # unchanged

    rc = dispatch(["reconcile-stamp", str(root), "--force"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "anchor advanced" in out
    assert "WARNING" in out  # forced past unassigned
