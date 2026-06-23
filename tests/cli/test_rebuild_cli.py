"""Tests for `dummyindex context rebuild` — the bare/--full/--changed paths.

Focus: the bare `rebuild` (no flag) must REFUSE on a curated index (exit 2)
rather than silently re-clustering it. `--full` is the explicit escape hatch;
`--changed` already routes to the non-destructive refresh.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import rebuild
from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.features import rename_feature
from tests.paths import SAMPLE_REPO

_FIXTURE_ROOT = SAMPLE_REPO


@pytest.fixture
def primed_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    build_all(dest, cache_root=tmp_path / "cache")
    return dest


def _curate(repo: Path) -> str:
    features_dir = repo / ".context" / "features"
    index = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    first_id = index["features"][0]["feature_id"]
    new_id = "auth-core"
    rename_feature(
        features_dir,
        from_id=first_id,
        to_id=new_id,
        new_name="Auth Core",
        new_summary="Curated.",
    )
    return new_id


@pytest.mark.integration
def test_bare_rebuild_refuses_on_enriched_index(
    primed_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    new_id = _curate(primed_repo)
    index_before = (primed_repo / ".context" / "features" / "INDEX.json").read_text(
        encoding="utf-8"
    )

    rc = rebuild.run([str(primed_repo)])  # bare rebuild, absolute scope

    assert rc == 2
    err = capsys.readouterr().err
    assert "curated index detected" in err
    assert "--full" in err and "--changed" in err
    # Refused → INDEX.json untouched, curated dir intact.
    index_after = (primed_repo / ".context" / "features" / "INDEX.json").read_text(
        encoding="utf-8"
    )
    assert index_after == index_before
    assert (primed_repo / ".context" / "features" / new_id).is_dir()


@pytest.mark.integration
def test_bare_rebuild_full_proceeds_on_enriched_index(
    primed_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _curate(primed_repo)

    rc = rebuild.run([str(primed_repo), "--full"])

    assert rc == 0
    captured = capsys.readouterr()
    # The destructive warning fires, and the build runs (re-clustering).
    assert "DISCARDS" in captured.err
    assert "context rebuild: wrote" in captured.out


@pytest.mark.integration
def test_bare_rebuild_proceeds_on_deterministic_index(
    primed_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No curation — a deterministic-only index has nothing to lose, so the
    # bare rebuild proceeds (full build) without refusing.
    rc = rebuild.run([str(primed_repo)])
    assert rc == 0
    assert "context rebuild: wrote" in capsys.readouterr().out
