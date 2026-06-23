"""Tests for ``dummyindex context statusline`` — the cold-path freshness badge.

The per-prompt hot path is a shipped shell/PowerShell wrapper that ``cat``s the
gitignored badge cache directly (no Python). ``cli/statusline.py`` is the
**cold-path fallback**: it reads the same cache file (resolved through
:func:`badge_cache_path`, the single source of truth shared with the
``plan-update`` writer) and prints it. Because this runs on *every* prompt, the
contract (spec §5) is absolute: it must **never** crash a user's shell — every
exception, a missing ``.context/``, a missing cache, or an
unreadable/malformed cache all collapse to **empty stdout, exit 0**, and it
never recomputes drift.

These tests pin exactly that. A smoke test also asserts the shipped ``.sh``
reads the same path and exits 0 when the cache is absent — deliberately light
(we don't over-test shell).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli.plan_update import badge_cache_path
from dummyindex.cli.statusline import SCRIPT_DIR, run


def _seed_badge(project_root: Path, text: str) -> Path:
    """Write ``text`` into the badge cache under ``.context/cache/``."""
    cache_file = badge_cache_path(project_root / ".context")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(text, encoding="utf-8")
    return cache_file


@pytest.mark.unit
def test_populated_cache_prints_its_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A populated cache ⇒ its exact contents print, rc 0, no trailing extras."""
    _seed_badge(tmp_path, "[ctx: 3 drift]")

    rc = run(["--root", str(tmp_path)])

    assert rc == 0
    assert capsys.readouterr().out == "[ctx: 3 drift]"


@pytest.mark.unit
def test_fresh_badge_prints_verbatim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fresh marker round-trips byte-for-byte (no reformatting)."""
    _seed_badge(tmp_path, "[ctx ✓]")

    rc = run(["--root", str(tmp_path)])

    assert rc == 0
    assert capsys.readouterr().out == "[ctx ✓]"


@pytest.mark.unit
def test_missing_context_dir_prints_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No ``.context/`` at all ⇒ empty stdout, exit 0 (never crash the shell)."""
    rc = run(["--root", str(tmp_path)])

    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_missing_cache_file_prints_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``.context/`` exists but the cache file is absent ⇒ empty stdout, rc 0."""
    (tmp_path / ".context").mkdir()

    rc = run(["--root", str(tmp_path)])

    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_unreadable_cache_prints_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A cache path that cannot be read as text (here: a directory standing in
    for the file ⇒ ``IsADirectoryError``) ⇒ empty stdout, rc 0 — the broad
    catch swallows it rather than letting it escape into the shell."""
    cache_path = badge_cache_path(tmp_path / ".context")
    cache_path.mkdir(parents=True)  # malformed: a dir where a file is expected

    rc = run(["--root", str(tmp_path)])

    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_any_exception_is_swallowed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If *anything* in the body raises, stdout stays empty and rc is 0 — the
    whole body is wrapped so it can never crash the per-prompt shell."""
    _seed_badge(tmp_path, "[ctx: 9 drift]")

    import dummyindex.cli.statusline as statusline_mod

    def _boom(context_dir: Path) -> Path:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(statusline_mod, "badge_cache_path", _boom)

    rc = run(["--root", str(tmp_path)])

    assert rc == 0
    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_shipped_scripts_exist() -> None:
    """Both hot-path wrappers ship alongside the package."""
    assert (SCRIPT_DIR / "statusline.sh").is_file()
    assert (SCRIPT_DIR / "statusline.ps1").is_file()


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_shell_script_reads_same_path_and_exits_zero_when_absent(
    tmp_path: Path,
) -> None:
    """Smoke: the shipped ``.sh`` ``cat``s the SAME badge cache path the Python
    writer/reader use, prints nothing when it is absent, and exits 0.

    Run from a ``.context``-less cwd so a missing cache is the realistic case;
    asserting on the resolved path keeps the shell and Python in lockstep
    without over-testing shell behaviour.
    """
    script = SCRIPT_DIR / "statusline.sh"
    # The relative path the script reads, derived from the single source of
    # truth — proves the wrapper and the Python fallback agree on location.
    rel = badge_cache_path(Path(".") / ".context")
    assert str(rel).replace("\\", "/") in script.read_text(encoding="utf-8")

    proc = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
