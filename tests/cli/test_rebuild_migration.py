"""`context rebuild` legacy-root-CLAUDE.md folding (install-claude-md-migration).

Every successful rebuild exit — ``--changed`` rebuilt / enriched-preserved /
skipped, and the bare full rebuild — must fold a dangling legacy root
``CLAUDE.md`` under :func:`has_foldable_legacy_claude_md`, without ever
creating Claude guidance for a tree that has none.

The root file is seeded strictly AFTER the index build: ``init`` runs
``build_all(bootstrap=True)``, which would otherwise consume the seed instead
of the code under test.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.output.bootstrap import BEGIN_MARKER, END_MARKER
from tests.paths import SAMPLE_REPO

USER_BODY = "# Project notes\n\nHand-written house rules that must survive.\n"


def _ingested(tmp_path: Path, name: str) -> Path:
    """Copy SAMPLE_REPO into tmp_path and `init` it so `.context/` exists."""
    target = tmp_path / name
    shutil.copytree(SAMPLE_REPO, target)
    assert dispatch(["init", str(target)]) == 0
    return target


def _touch_source(target: Path) -> None:
    """Change a source file so `rebuild --changed` has work to do."""
    app = target / "app.py"
    app.write_text(app.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")


def _seed_enriched_curation(target: Path) -> None:
    """Seed a minimal curated feature dir (see test_install.py's local twin)."""
    feature_dir = target / ".context" / "features" / "auth-flow"
    feature_dir.mkdir(parents=True)
    (feature_dir / "feature.json").write_text(
        '{"feature_id": "auth-flow", "confidence": "INFERRED"}\n',
        encoding="utf-8",
    )


def _assert_folded(target: Path) -> None:
    assert not (target / "CLAUDE.md").exists()
    canonical = target / ".claude" / "CLAUDE.md"
    text = canonical.read_text(encoding="utf-8")
    assert text.count(BEGIN_MARKER) == 1
    assert text.count(END_MARKER) == 1
    assert "Hand-written house rules that must survive." in text


@pytest.mark.integration
def test_rebuild_changed_folds_legacy_root(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "rebuild_changed_fold")
    _touch_source(target)
    (target / "CLAUDE.md").write_text(USER_BODY, encoding="utf-8")

    assert dispatch(["rebuild", str(target), "--changed"]) == 0

    _assert_folded(target)


@pytest.mark.integration
def test_rebuild_changed_skipped_path_still_folds(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "rebuild_skipped_fold")
    assert dispatch(["rebuild", str(target), "--changed"]) == 0

    (target / "CLAUDE.md").write_text(USER_BODY, encoding="utf-8")

    assert dispatch(["rebuild", str(target), "--changed"]) == 0

    _assert_folded(target)


@pytest.mark.integration
def test_rebuild_enriched_preserved_path_folds(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "rebuild_enriched_fold")
    _seed_enriched_curation(target)
    _touch_source(target)
    (target / "CLAUDE.md").write_text(USER_BODY, encoding="utf-8")

    assert dispatch(["rebuild", str(target), "--changed"]) == 0

    _assert_folded(target)


@pytest.mark.integration
def test_rebuild_bare_full_folds_legacy_root(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "rebuild_bare_fold")
    (target / "CLAUDE.md").write_text(USER_BODY, encoding="utf-8")

    assert dispatch(["rebuild", str(target), "--full"]) == 0

    _assert_folded(target)


@pytest.mark.integration
def test_rebuild_without_root_file_is_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "rebuild_silent")
    _touch_source(target)

    capsys.readouterr()
    assert dispatch(["rebuild", str(target), "--changed"]) == 0

    captured = capsys.readouterr()
    assert "migration:" not in captured.out
    assert not (target / "CLAUDE.md").exists()


@pytest.mark.integration
def test_rebuild_leaves_codex_fallback_doc_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _ingested(tmp_path, "rebuild_codexdoc")
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    trust_key = json.dumps(str(target.resolve()))
    (codex_home / "config.toml").write_text(
        "project_doc_fallback_filenames = [\"CLAUDE.md\"]\n"
        f"[projects.{trust_key}]\n"
        'trust_level = "trusted"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    _touch_source(target)
    root = target / "CLAUDE.md"
    root.write_text(USER_BODY, encoding="utf-8")

    assert dispatch(["rebuild", str(target), "--changed"]) == 0

    assert root.exists(), "an active Codex fallback doc must be left in place"
    assert root.read_text(encoding="utf-8") == USER_BODY
