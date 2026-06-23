"""Tests for `dummyindex context propose` — grounded planning (Slice A).

Two fixture flavours:

- ``bare_context`` — a minimal hand-built ``.context/`` (no features index).
  Enough to exercise scaffolding, ``--force``, schema, and the
  scan-degrades-gracefully path.
- ``indexed_repo`` — the real ``build_all`` output over the sample repo,
  reused verbatim from ``test_query``. Proves the consistency scan returns
  related features for a title that overlaps a real feature.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli.propose import run as run_propose
from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.proposals import (
    SCHEMA_VERSION,
    ProposalExistsError,
    ensure_proposal,
    scan_consistency,
)
from tests.paths import SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO


@pytest.fixture
def bare_context(tmp_path: Path) -> Path:
    """A repo root with a minimal `.context/` and no features index."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    # A convention doc so the scan has something to list.
    conv = context_dir / "conventions"
    conv.mkdir()
    (conv / "naming.md").write_text("# Naming\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def indexed_repo(tmp_path: Path) -> Path:
    """The sample repo run through `build_all` once (mirrors test_query)."""
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    build_all(dest, cache_root=tmp_path / "cache")
    return dest


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ensure_proposal_scaffolds_four_files(bare_context: Path) -> None:
    written = ensure_proposal(bare_context / ".context", "demo", "Add export")
    assert len(written) == 4
    pdir = bare_context / ".context" / "proposals" / "demo"
    for name in ("proposal.json", "spec.md", "plan.md", "checklist.md"):
        assert (pdir / name).is_file(), f"missing {name}"


@pytest.mark.unit
def test_proposal_json_schema(bare_context: Path) -> None:
    ensure_proposal(bare_context / ".context", "demo", "Add export")
    payload = json.loads(
        (bare_context / ".context" / "proposals" / "demo" / "proposal.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["slug"] == "demo"
    assert payload["title"] == "Add export"
    assert payload["status"] == "planned"
    assert payload["related_features"] == []
    assert payload["conventions"] == []
    assert payload["reused_symbols"] == []


@pytest.mark.unit
def test_spec_has_acceptance_section(bare_context: Path) -> None:
    ensure_proposal(bare_context / ".context", "demo", "Add export")
    spec = (bare_context / ".context" / "proposals" / "demo" / "spec.md").read_text(
        encoding="utf-8"
    )
    assert "## Acceptance" in spec
    assert "- [ ]" in spec


# ---------------------------------------------------------------------------
# Re-run / force semantics
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rerun_without_force_errors(bare_context: Path) -> None:
    ensure_proposal(bare_context / ".context", "demo", "First")
    with pytest.raises(ProposalExistsError):
        ensure_proposal(bare_context / ".context", "demo", "Second")


@pytest.mark.unit
def test_rerun_with_force_overwrites(bare_context: Path) -> None:
    ensure_proposal(bare_context / ".context", "demo", "First")
    ensure_proposal(bare_context / ".context", "demo", "Second", force=True)
    payload = json.loads(
        (bare_context / ".context" / "proposals" / "demo" / "proposal.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["title"] == "Second"


# ---------------------------------------------------------------------------
# Slug safety
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bad_slug_rejected(bare_context: Path) -> None:
    from dummyindex.context.domains.proposals import ProposalSlugError

    with pytest.raises(ProposalSlugError):
        ensure_proposal(bare_context / ".context", "../escape", "X")


# ---------------------------------------------------------------------------
# Consistency scan
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scan_degrades_without_features_index(bare_context: Path) -> None:
    """No features/INDEX.json → empty related, but conventions still listed."""
    hits = scan_consistency(bare_context / ".context", "anything")
    assert hits.related_features == ()
    assert "conventions/naming.md" in hits.conventions


@pytest.mark.integration
def test_scan_lists_related_features(indexed_repo: Path) -> None:
    """A title overlapping the sample repo's `App` surfaces related features."""
    hits = scan_consistency(indexed_repo / ".context", "app helper")
    assert hits.related_features, "expected related features for an 'app' title"


@pytest.mark.integration
def test_apply_persists_hits_into_proposal_json(indexed_repo: Path) -> None:
    from dummyindex.context.domains.proposals import apply_consistency

    ensure_proposal(indexed_repo / ".context", "demo", "app helper")
    hits = scan_consistency(indexed_repo / ".context", "app helper")
    apply_consistency(indexed_repo / ".context", "demo", hits)
    payload = json.loads(
        (indexed_repo / ".context" / "proposals" / "demo" / "proposal.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["related_features"] == list(hits.related_features)
    spec = (indexed_repo / ".context" / "proposals" / "demo" / "spec.md").read_text(
        encoding="utf-8"
    )
    assert "## Consistency" in spec


# ---------------------------------------------------------------------------
# CLI plumbing (call `run_propose` directly for focused unit coverage).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_cli_propose_creates_proposal(indexed_repo: Path, capsys) -> None:
    rc = run_propose(
        ["--slug", "demo", "--title", "app helper", "--root", str(indexed_repo)]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "propose" in captured.out.lower()
    assert (indexed_repo / ".context" / "proposals" / "demo" / "spec.md").is_file()


@pytest.mark.integration
def test_cli_propose_force_overwrites(indexed_repo: Path) -> None:
    base = ["--slug", "demo", "--root", str(indexed_repo)]
    assert run_propose(base + ["--title", "First"]) == 0
    # Without --force the re-run is a runtime error (exit 1).
    assert run_propose(base + ["--title", "Second"]) == 1
    # With --force it succeeds and overwrites.
    assert run_propose(base + ["--title", "Second", "--force"]) == 0
    payload = json.loads(
        (indexed_repo / ".context" / "proposals" / "demo" / "proposal.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["title"] == "Second"


@pytest.mark.unit
def test_cli_propose_missing_args_errors(bare_context: Path, capsys) -> None:
    rc = run_propose(["--root", str(bare_context)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "required" in captured.err.lower()


@pytest.mark.unit
def test_cli_propose_bad_slug_errors(bare_context: Path, capsys) -> None:
    rc = run_propose(
        ["--slug", "../escape", "--title", "X", "--root", str(bare_context)]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "slug" in captured.err.lower()
