"""Wave-4 registration: ``debt`` + ``statusline`` are wired into the dispatcher.

The command *bodies* (``cli/debt.py`` / ``cli/statusline.py``) are covered by
``test_debt_cli.py`` / ``test_statusline.py``, which invoke ``run`` directly
because the subcommands were not registered until this wave. These tests pin the
*wiring* this task adds — and nothing more:

- the ``_HANDLERS`` table maps ``ContextSubcommand.DEBT`` / ``STATUSLINE`` to the
  exact ``run`` callables (mirroring ``ContextSubcommand.QUERY: query.run``);
- ``dispatch([...])`` routes to those handlers with the post-subcommand argv
  (the same ``rest`` shape every other subcommand receives);
- both new subcommands answer ``--help`` (the shared read-only help contract);
- a real end-to-end ``dispatch`` of each subcommand returns 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.cli import _HANDLERS, debt, dispatch, statusline
from dummyindex.context.enums import ContextSubcommand


@pytest.mark.unit
def test_handlers_table_maps_debt_and_statusline_to_their_run() -> None:
    """The dispatch table points at the exact module ``run`` callables."""
    assert _HANDLERS[ContextSubcommand.DEBT] is debt.run
    assert _HANDLERS[ContextSubcommand.STATUSLINE] is statusline.run


@pytest.mark.unit
def test_every_enum_member_has_a_handler() -> None:
    """No ``ContextSubcommand`` is left undispatchable (the new two included)."""
    missing = [s.value for s in ContextSubcommand if s not in _HANDLERS]
    assert missing == [], f"subcommands with no handler: {missing}"


@pytest.mark.unit
def test_dispatch_routes_debt_to_handler_with_rest_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``dispatch(['debt', ...])`` calls ``debt.run`` with the trailing args."""
    seen: dict[str, list[str]] = {}

    def _spy(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    # Patch the entry in the live dispatch table (what ``dispatch`` reads).
    monkeypatch.setitem(_HANDLERS, ContextSubcommand.DEBT, _spy)

    rc = dispatch(["debt", "--root", "."])
    assert rc == 0
    assert seen["argv"] == ["--root", "."]


@pytest.mark.unit
def test_dispatch_routes_statusline_to_handler_with_rest_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``dispatch(['statusline', ...])`` calls ``statusline.run`` with the args."""
    seen: dict[str, list[str]] = {}

    def _spy(argv: list[str]) -> int:
        seen["argv"] = argv
        return 0

    monkeypatch.setitem(_HANDLERS, ContextSubcommand.STATUSLINE, _spy)

    rc = dispatch(["statusline", "--root", "."])
    assert rc == 0
    assert seen["argv"] == ["--root", "."]


@pytest.mark.unit
@pytest.mark.parametrize("sub", ["debt", "statusline"])
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_new_subcommands_answer_help(
    sub: str,
    flag: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--help`` for each new subcommand exits 0, names it, writes nothing."""
    monkeypatch.chdir(tmp_path)
    rc = dispatch([sub, flag])
    out = capsys.readouterr().out
    assert rc == 0
    assert sub in out, f"`context {sub} {flag}` usage does not name the subcommand"
    # Read-only: the throwaway cwd must be untouched.
    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
def test_dispatch_statusline_end_to_end_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real (un-spied) ``statusline`` dispatch on a bare dir exits 0."""
    monkeypatch.chdir(tmp_path)
    assert dispatch(["statusline", "--root", str(tmp_path)]) == 0


@pytest.mark.unit
def test_dispatch_debt_end_to_end_on_clean_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A real ``debt`` dispatch over a marker-free repo exits 0 + no-debt msg."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "clean.py").write_text(
        "def f():\n    return 1\n", encoding="utf-8"
    )
    rc = dispatch(["debt", "--root", str(tmp_path)])
    assert rc == 0
    assert "No debt markers" in capsys.readouterr().out
