"""Tests for ``plan-update --json`` — the stable machine envelope.

The SessionStart hook consumes markdown; ``--json`` exists so scripts can act
per-row instead of parsing prose (spec §Contracts). The envelope has exactly
the documented keys, exit code stays 0, stdout-only — and plain mode is
untouched: byte-identical output on a no-drift repo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dummyindex.cli import dispatch


def _make_feature(
    project_root: Path,
    feature_id: str,
    *,
    files: list[str],
) -> Path:
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
    (feature_dir / "spec.md").write_text(f"# {feature_id}\n", encoding="utf-8")
    return feature_dir


def _drifting_repo(tmp_path: Path) -> None:
    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    feature_dir = _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    os.utime(feature_dir / "spec.md", (500.0, 500.0))
    os.utime(src, (1_000.0, 1_000.0))


_ENVELOPE_KEYS = {"edited", "anchored", "suppressed", "acked"}
_ANCHORED_KEYS = {"unassigned_new_files", "awaiting_enrichment", "drifted_features"}


@pytest.mark.integration
def test_json_envelope_has_exactly_the_documented_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _drifting_repo(tmp_path)

    rc = dispatch(["plan-update", "--root", str(tmp_path), "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == _ENVELOPE_KEYS
    assert set(payload["anchored"].keys()) == _ANCHORED_KEYS
    assert payload["edited"] == ["app/service.py"]
    assert payload["suppressed"] == 0 and payload["acked"] == 0


@pytest.mark.integration
def test_plain_mode_unchanged_on_no_drift_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hook's historical contract stands: a clean repo prints nothing."""
    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    feature_dir = _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    os.utime(feature_dir / "spec.md", (1_000.0, 1_000.0))
    os.utime(src, (500.0, 500.0))

    rc = dispatch(["plan-update", "--root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.integration
def test_json_envelope_reports_suppressed_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Basis-matched files flow into ``suppressed`` and never into ``edited``;
    an inert ack (wrong feature + stale sha) never inflates ``acked``."""
    from dummyindex.context.build.reconcile import blob_sha
    from dummyindex.context.domains.drift_acks import append_ack

    src = tmp_path / "app" / "service.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("def f(): return 1\n", encoding="utf-8")
    _make_feature(tmp_path, "service-loop", files=["app/service.py"])
    context_dir = tmp_path / ".context"
    basis_path = context_dir / "cache" / "doc-basis.json"
    basis_path.parent.mkdir(parents=True, exist_ok=True)
    basis_path.write_text(
        json.dumps(
            {
                "basis_version": 1,
                "features": {
                    "service-loop": {"app/service.py": blob_sha(src.read_bytes())}
                },
            }
        ),
        encoding="utf-8",
    )
    append_ack(
        context_dir,
        feature_id="other",
        acked_sha="deadbeef",
        path="x.py",
    )

    rc = dispatch(["plan-update", "--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["suppressed"] == 1
    assert payload["acked"] == 0
    assert payload["edited"] == []


@pytest.mark.integration
def test_unknown_args_still_rejected_alongside_json_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = dispatch(["plan-update", "--root", str(tmp_path), "--json", "--bogus"])
    assert rc == 2
    assert "unknown argument" in capsys.readouterr().err
