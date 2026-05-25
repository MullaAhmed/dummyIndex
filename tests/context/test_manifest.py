"""Tests for the drift manifest + `dummyindex context check` command."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.cli import dispatch
from dummyindex.context.manifest import (
    MANIFEST_REL,
    compare,
    read_manifest,
    write_manifest,
)


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


def _ingested(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(_FIXTURE, target)
    assert dispatch(["init", str(target)]) == 0
    return target


# ----- write_manifest / read_manifest ---------------------------------------


@pytest.mark.unit
def test_write_creates_manifest_in_cache(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def f(): pass\n", encoding="utf-8")
    context = root / ".context"
    context.mkdir()

    path = write_manifest(context, root=root, files=[root / "a.py"])
    assert path == context / MANIFEST_REL
    assert path.exists()

    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert "a.py" in payload["files"]
    entry = payload["files"]["a.py"]
    assert "sha256" in entry and "size" in entry and "mtime" in entry


@pytest.mark.unit
def test_read_returns_none_when_no_manifest(tmp_path: Path) -> None:
    context = tmp_path / ".context"
    context.mkdir()
    assert read_manifest(context) is None


@pytest.mark.unit
def test_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    context = root / ".context"
    context.mkdir()
    write_manifest(context, root=root, files=[root / "a.py"])

    m = read_manifest(context)
    assert m is not None
    assert "a.py" in m.files
    assert m.files["a.py"].size == len("x = 1\n")


# ----- compare() ------------------------------------------------------------


@pytest.mark.unit
def test_compare_no_manifest_treats_all_as_added(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("pass\n", encoding="utf-8")
    context = root / ".context"
    context.mkdir()

    drift = compare(context, root=root, current_files=[root / "a.py"])
    assert drift.added == ("a.py",)
    assert drift.modified == ()
    assert drift.removed == ()
    assert not drift.is_clean


@pytest.mark.unit
def test_compare_clean_when_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("pass\n", encoding="utf-8")
    context = root / ".context"
    context.mkdir()
    write_manifest(context, root=root, files=[root / "a.py"])

    drift = compare(context, root=root, current_files=[root / "a.py"])
    assert drift.is_clean


@pytest.mark.unit
def test_compare_detects_modified(tmp_path: Path) -> None:
    import time

    root = tmp_path / "repo"
    root.mkdir()
    f = root / "a.py"
    f.write_text("pass\n", encoding="utf-8")
    context = root / ".context"
    context.mkdir()
    write_manifest(context, root=root, files=[f])

    # Bump mtime so the cheap pre-check fires; content also differs.
    time.sleep(0.01)
    f.write_text("def g(): pass\n", encoding="utf-8")

    drift = compare(context, root=root, current_files=[f])
    assert drift.modified == ("a.py",)
    assert drift.added == ()
    assert drift.removed == ()


@pytest.mark.unit
def test_compare_detects_added_and_removed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("pass\n", encoding="utf-8")
    context = root / ".context"
    context.mkdir()
    write_manifest(context, root=root, files=[root / "a.py"])

    # Add a new file, "remove" a.py from the current set.
    (root / "b.py").write_text("pass\n", encoding="utf-8")
    drift = compare(context, root=root, current_files=[root / "b.py"])
    assert drift.added == ("b.py",)
    assert drift.removed == ("a.py",)
    assert drift.modified == ()


# ----- CLI: dispatch ["check"] ---------------------------------------------


@pytest.mark.integration
def test_check_cli_clean_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "check_clean")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["check"])
    assert rc == 0
    assert "clean" in capsys.readouterr().out


@pytest.mark.integration
def test_check_cli_drift_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import time

    target = _ingested(tmp_path, "check_drift")
    capsys.readouterr()
    # Modify a source file
    fixture_py = next(target.rglob("*.py"))
    time.sleep(0.01)
    fixture_py.write_text(fixture_py.read_text() + "\n# drift\n", encoding="utf-8")

    monkeypatch.chdir(target)
    rc = dispatch(["check"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "drift detected" in out
    assert "modified" in out


@pytest.mark.integration
def test_check_cli_quiet_suppresses_clean_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "check_quiet")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["check", "--quiet"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out == ""


@pytest.mark.integration
def test_check_cli_auto_refresh_triggers_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import time

    target = _ingested(tmp_path, "check_auto")
    capsys.readouterr()
    # Modify a file to create drift
    fixture_py = next(target.rglob("*.py"))
    time.sleep(0.01)
    fixture_py.write_text(fixture_py.read_text() + "\ndef _added(): pass\n", encoding="utf-8")

    monkeypatch.chdir(target)
    rc = dispatch(["check", "--auto-refresh"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "auto-refreshing" in out
    # And a follow-up check is now clean.
    capsys.readouterr()
    rc2 = dispatch(["check"])
    assert rc2 == 0


@pytest.mark.integration
def test_check_cli_errors_when_no_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    rc = dispatch(["check"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


@pytest.mark.integration
def test_ingest_writes_manifest(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "manifest_after_ingest")
    manifest = target / ".context" / MANIFEST_REL
    assert manifest.exists()
    payload = json.loads(manifest.read_text())
    assert payload["files"], "manifest should have at least one file entry"
