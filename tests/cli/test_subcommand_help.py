"""Every context subcommand answers -h / --help (read-only, exit 0).

The CLI is a hand-rolled dispatcher, not argparse: before this guard, a
``--help`` token after a subcommand fell through to the handler's
leftover-args check and exited 2 (or, for ``hooks``, was misread as a verb).
Worse, the probe that followed a failed ``--help`` — running the bare verb —
could MUTATE the repo (``equip``). These tests pin the contract:

- ``dispatch([sub, '--help'])`` and ``dispatch([sub, '-h'])`` exit 0,
- print a non-empty usage block naming the subcommand,
- and write NOTHING to disk (run in a throwaway cwd).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.enums import ContextSubcommand


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.mark.unit
@pytest.mark.parametrize("sub", list(ContextSubcommand), ids=lambda s: s.value)
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_every_subcommand_answers_help(
    sub: ContextSubcommand,
    flag: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)

    code = dispatch([sub.value, flag])

    out = capsys.readouterr().out
    assert code == 0, f"`context {sub.value} {flag}` should exit 0, got {code}"
    assert out.strip(), f"`context {sub.value} {flag}` printed nothing"
    assert sub.value in out, (
        f"`context {sub.value} {flag}` usage does not name the subcommand"
    )
    after = _snapshot(tmp_path)
    assert before == after, (
        f"`context {sub.value} {flag}` mutated the cwd: {sorted(after - before)}"
    )


@pytest.mark.unit
def test_help_token_after_verbed_subcommand(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A nested verb's --help still resolves to the parent subcommand usage."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    for argv in (["equip", "discover", "--help"], ["hooks", "--help"], ["init", "-h"]):
        code = dispatch(argv)
        out = capsys.readouterr().out
        assert code == 0, f"{argv} should exit 0"
        assert out.strip(), f"{argv} printed nothing"


@pytest.mark.unit
def test_onboard_help_documents_depth_command_depths_and_wired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`onboard --help` documents the per-command depth + wiring config keys
    (mirrors the `--skill-only` usage-help substring test)."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    code = dispatch(["onboard", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "--depth" in out
    assert "command_depths" in out
    assert "wired" in out


@pytest.mark.unit
def test_onboard_module_docstring_documents_depth_and_wired() -> None:
    """The onboard handler's own usage banner (module docstring) documents the
    hand-edited `command_depths`/`wired` keys + the `--depth` flag."""
    from dummyindex.cli import onboard

    banner = onboard.__doc__ or ""
    assert "--depth" in banner
    assert "command_depths" in banner
    assert "wired" in banner


@pytest.mark.unit
def test_gc_help_lists_all_four_verbs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`gc --help` documents every verb (status|delete|stamp|signal)."""
    from dummyindex.cli import dispatch

    monkeypatch.chdir(tmp_path)
    code = dispatch(["gc", "--help"])
    out = capsys.readouterr().out
    assert code == 0
    for verb in ("status", "delete", "stamp", "signal"):
        assert verb in out, f"`gc --help` does not document the {verb!r} verb"


@pytest.mark.unit
def test_top_level_install_and_ingest_help(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`dummyindex install --help` / `ingest --help` exit 0 with no side effects."""
    from dummyindex import __main__

    monkeypatch.setattr(
        __main__,
        "install",
        lambda **kw: pytest.fail("install --help must not run install"),
    )
    monkeypatch.setattr(__main__.sys, "argv", ["dummyindex", "install", "--help"])
    with pytest.raises(SystemExit) as exc:
        __main__.main()
    assert exc.value.code == 0
    assert "install" in capsys.readouterr().out

    monkeypatch.setattr(__main__.sys, "argv", ["dummyindex", "ingest", "--help"])
    code = None
    with pytest.raises(SystemExit) as exc2:
        __main__.main()
    code = exc2.value.code
    assert code == 0
    out = capsys.readouterr().out
    assert "init" in out or "ingest" in out
