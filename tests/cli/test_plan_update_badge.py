"""Badge-write boundary tests for ``dummyindex context plan-update``.

The drift report is the SessionStart hook's stdout contract (covered in
``tests/context/test_drift.py``). *Additionally*, after computing the report,
``plan-update`` writes the ``compute_badge(report)`` string to a gitignored
cache file under ``.context/cache/`` so the statusline command can read a
pre-computed badge off the per-prompt hot path without re-running Python's
drift scan.

That write is **best-effort** (spec §5): a missing or unwritable cache must
never fail the hook and must never perturb the drift report that prints to
stdout. These tests pin exactly that — the badge is written on the happy
path, the cache dir is created when absent, and a write failure is swallowed
while the report still prints and the verb still returns 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.cli.plan_update import badge_cache_path
from dummyindex.context.drift import compute_badge, compute_drift


def _make_feature(
    project_root: Path,
    feature_id: str,
    *,
    files: list[str],
    docs: tuple[str, ...] = ("architecture.md",),
) -> Path:
    """Stand up a minimal ``.context/features/<feature_id>/`` folder."""
    feature_dir = project_root / ".context" / "features" / feature_id
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "feature.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_id": feature_id,
                "kind": "community",
                "name": feature_id,
                "files": files,
                "members": [],
                "entry_points": [],
                "flow_ids": [],
            }
        ),
        encoding="utf-8",
    )
    for name in docs:
        (feature_dir / name).write_text(f"# {feature_id} {name}\n", encoding="utf-8")
    return feature_dir


@pytest.mark.integration
def test_plan_update_writes_badge_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """After ``plan-update`` runs on a repo with ``.context/features/``, the
    badge cache file exists and contains exactly ``compute_badge(report)``."""
    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    _make_feature(tmp_path, "service-loop", files=["app/service.py"])

    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0

    cache_file = badge_cache_path(tmp_path / ".context")
    assert cache_file.is_file()
    expected = compute_badge(compute_drift(tmp_path))
    assert cache_file.read_text(encoding="utf-8") == expected


@pytest.mark.integration
def test_plan_update_creates_cache_dir_when_absent(tmp_path: Path) -> None:
    """The ``.context/cache/`` directory is created if it does not exist."""
    _make_feature(tmp_path, "svc", files=["app/x.py"], docs=("spec.md",))
    cache_dir = tmp_path / ".context" / "cache"
    assert not cache_dir.exists()

    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0
    assert cache_dir.is_dir()
    assert badge_cache_path(tmp_path / ".context").is_file()


@pytest.mark.integration
def test_badge_write_failure_is_swallowed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the badge write raises, ``plan-update`` still returns 0 and still
    prints the drift report — the failure is swallowed (best-effort, spec §5)."""
    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    feature_dir = _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    # Force drift: source newer than the docs.
    import os

    os.utime(feature_dir / "architecture.md", (500.0, 500.0))
    os.utime(src, (1_000.0, 1_000.0))

    # Simulate an OSError on the atomic writer used by the badge step.
    import dummyindex.cli.plan_update as plan_update_mod

    def _boom(path: Path, text: str) -> None:
        raise OSError("read-only cache")

    monkeypatch.setattr(plan_update_mod, "write_text_atomic", _boom)

    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0

    out = capsys.readouterr().out
    # The drift report still prints — the badge failure did not affect it.
    assert "drift report" in out
    assert "service-loop" in out
    # And nothing was written to the cache.
    assert not badge_cache_path(tmp_path / ".context").exists()
