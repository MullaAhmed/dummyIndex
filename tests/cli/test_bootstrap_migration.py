"""`context bootstrap` legacy-root-CLAUDE.md folding (install-claude-md-migration).

The bootstrap command regenerates the managed guidance block for the selected
host. Since the fold wiring, it must ALSO consolidate a dangling legacy root
``CLAUDE.md`` into the canonical ``.claude/CLAUDE.md`` — but only when

1. the platform touches Claude (``claude|both`` — ``agents`` never folds), and
2. :func:`has_foldable_legacy_claude_md` passes (root exists AND is not an
   active Codex instruction candidate).

Degradations inside ``reconcile_claude_md`` are non-fatal: exit stays 0, a
warning lands on stderr, and the root file survives.

The legacy root file is seeded strictly AFTER ``_ingested()`` returns:
``init`` itself runs ``build_all(bootstrap=True)`` which would otherwise
consume the seed instead of the code under test.
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


def _managed_root_claude() -> str:
    """User content wrapped around a stale legacy managed block."""
    return (
        f"{USER_BODY}\n"
        f"{BEGIN_MARKER}\nstale managed body\n{END_MARKER}\n\n"
        "More user content below the block.\n"
    )


def _malformed_root_claude() -> str:
    """Reversed markers — reconcile must degrade to NOOP + warning."""
    return f"{USER_BODY}\n{END_MARKER}\nreversed body\n{BEGIN_MARKER}\n"


def _assert_folded(target: Path) -> str:
    root = target / "CLAUDE.md"
    canonical = target / ".claude" / "CLAUDE.md"
    assert not root.exists(), "root ./CLAUDE.md should have been folded away"
    text = canonical.read_text(encoding="utf-8")
    assert text.count(BEGIN_MARKER) == 1
    assert text.count(END_MARKER) == 1
    assert "Hand-written house rules that must survive." in text
    assert "stale managed body" not in text
    return text


@pytest.mark.integration
def test_bootstrap_claude_folds_legacy_root(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "bootstrap_fold")
    (target / "CLAUDE.md").write_text(_managed_root_claude(), encoding="utf-8")

    assert dispatch(["bootstrap", str(target)]) == 0

    _assert_folded(target)


@pytest.mark.integration
def test_bootstrap_degrades_on_malformed_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "bootstrap_malformed")
    root = target / "CLAUDE.md"
    root.write_text(_malformed_root_claude(), encoding="utf-8")

    assert dispatch(["bootstrap", str(target)]) == 0

    err = capsys.readouterr().err
    assert "migration warning:" in err
    assert root.exists(), "degraded fold must leave the root file in place"


@pytest.mark.integration
def test_bootstrap_without_root_file_is_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "bootstrap_silent")
    assert not (target / "CLAUDE.md").exists()

    capsys.readouterr()
    assert dispatch(["bootstrap", str(target)]) == 0

    captured = capsys.readouterr()
    assert "migration:" not in captured.out
    assert not (target / "CLAUDE.md").exists()


@pytest.mark.integration
def test_bootstrap_agents_platform_does_not_fold(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "bootstrap_agents")
    root = target / "CLAUDE.md"
    seeded = _managed_root_claude()
    root.write_text(seeded, encoding="utf-8")

    assert dispatch(["bootstrap", str(target), "--platform", "agents"]) == 0

    assert root.exists(), "agents-platform bootstrap must never fold CLAUDE.md"
    assert root.read_text(encoding="utf-8") == seeded


@pytest.mark.integration
def test_bootstrap_both_platform_folds_and_writes_agents(tmp_path: Path) -> None:
    target = _ingested(tmp_path, "bootstrap_both")
    (target / "CLAUDE.md").write_text(_managed_root_claude(), encoding="utf-8")

    assert dispatch(["bootstrap", str(target), "--platform", "both"]) == 0

    _assert_folded(target)
    agents_md = target / "AGENTS.md"
    assert agents_md.exists()
    assert ".context/HOW_TO_USE.md" in agents_md.read_text(encoding="utf-8")


@pytest.mark.integration
def test_bootstrap_leaves_codex_fallback_doc_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root CLAUDE.md named as an active Codex fallback doc is never folded."""
    target = _ingested(tmp_path, "bootstrap_codexdoc")
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

    root = target / "CLAUDE.md"
    seeded = USER_BODY
    root.write_text(seeded, encoding="utf-8")

    assert dispatch(["bootstrap", str(target)]) == 0

    assert root.exists(), "an active Codex fallback doc must be left in place"
    assert root.read_text(encoding="utf-8") == seeded
