"""`dummyindex context wire` — the interactive escalation surface for `wired`.

The headless reconciler (``wire_default_plugins``) only classifies and reports
needs-user entries; it NEVER prompts (it runs in best-effort headless init).
``wire`` is the only surface that prompts. These tests pin that contract using
an INJECTED fake prompt (``wire._PROMPT``) — never real stdin, so the suite can
never hang:

- a needs-user plugin + affirmative prompt → wired (settings.json enables it),
- a needs-user plugin + negative prompt → not wired, still needs-user,
- a skill entry → surfaced manual, never wired,
- ``--yes`` → auto-affirms with no prompt call,
- non-TTY + no ``--yes`` → prints the would-prompt list, exits 0, no prompt call,
- no config / no .context/ → graceful messages + exit codes,
- nothing-to-do → no mutation,
- the headless ``wire_default_plugins`` still never calls ``input()``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def _indexed(tmp_path: Path) -> Path:
    """Minimal .context/ so `wire` treats the repo as initialized."""
    context_dir = tmp_path / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)
    return context_dir


def _write_config(context_dir: Path, wired: list[dict]) -> None:
    payload = {
        "schema_version": 2,
        "scope": "repo",
        "scope_path": None,
        "mode": "standard",
        "model": "sonnet-4.6",
        "auto_refresh_hook": True,
        "external_docs": [],
        "reconcile_exclude": [],
        "command_depths": {},
        "wired": wired,
        "dummyindex_version": "1.0.0",
    }
    (context_dir / "config.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _enabled_plugins(tmp_path: Path) -> dict:
    settings = tmp_path / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    return json.loads(settings.read_text()).get("enabledPlugins", {})


class _FakePrompt:
    """Records calls and returns a canned answer. NEVER reads real stdin."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[str] = []

    def __call__(self, message: str) -> str:
        self.calls.append(message)
        return self.answer


@pytest.fixture
def _tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force `wire` to believe stdin is a TTY so it takes the prompt path."""
    import dummyindex.cli.wire as wire

    monkeypatch.setattr(wire, "_stdin_is_tty", lambda: True)


@pytest.mark.unit
def test_needs_user_plugin_affirmative_prompt_wires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _tty: None,
) -> None:
    """A declared-but-absent plugin + 'y' → it is wired into settings.json."""
    import dummyindex.cli.wire as wire
    from dummyindex.cli import dispatch

    context_dir = _indexed(tmp_path)
    target = "superpowers@claude-plugins-official"
    _write_config(context_dir, [{"kind": "plugin", "target": target, "version": None}])

    fake = _FakePrompt("y")
    monkeypatch.setattr(wire, "_PROMPT", fake)

    code = dispatch(["wire", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert fake.calls, "the plugin prompt should have been raised"
    assert _enabled_plugins(tmp_path).get(target) is True
    assert "1 wired" in out


@pytest.mark.unit
def test_needs_user_plugin_negative_prompt_not_wired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _tty: None,
) -> None:
    """A declared-but-absent plugin + 'n' → NOT wired, still needs-user."""
    import dummyindex.cli.wire as wire
    from dummyindex.cli import dispatch

    context_dir = _indexed(tmp_path)
    target = "superpowers@claude-plugins-official"
    _write_config(context_dir, [{"kind": "plugin", "target": target, "version": None}])

    fake = _FakePrompt("n")
    monkeypatch.setattr(wire, "_PROMPT", fake)

    code = dispatch(["wire", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert fake.calls, "the plugin prompt should have been raised"
    assert target not in _enabled_plugins(tmp_path)
    assert "1 skipped" in out
    assert "1 needs-user remaining" in out


@pytest.mark.unit
def test_skill_entry_surfaced_manual_never_wired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _tty: None,
) -> None:
    """A kind=skill entry is surfaced as manual and NEVER prompts or wires."""
    import dummyindex.cli.wire as wire
    from dummyindex.cli import dispatch

    context_dir = _indexed(tmp_path)
    _write_config(
        context_dir, [{"kind": "skill", "target": "some-skill", "version": None}]
    )

    fake = _FakePrompt("y")
    monkeypatch.setattr(wire, "_PROMPT", fake)

    code = dispatch(["wire", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert fake.calls == [], "a skill must never be prompted to wire"
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert "must be added manually" in out
    assert "some-skill" in out


@pytest.mark.unit
def test_yes_flag_auto_affirms_without_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--yes wires every plugin WITHOUT ever calling the prompt seam."""
    import dummyindex.cli.wire as wire
    from dummyindex.cli import dispatch

    context_dir = _indexed(tmp_path)
    target = "superpowers@claude-plugins-official"
    _write_config(context_dir, [{"kind": "plugin", "target": target, "version": None}])

    fake = _FakePrompt("n")  # would decline if ever called
    monkeypatch.setattr(wire, "_PROMPT", fake)

    code = dispatch(["wire", "--root", str(tmp_path), "--yes"])
    out = capsys.readouterr().out

    assert code == 0
    assert fake.calls == [], "--yes must auto-affirm, never call input"
    assert _enabled_plugins(tmp_path).get(target) is True
    assert "1 wired" in out


@pytest.mark.unit
def test_non_tty_without_yes_does_not_hang(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Piped/CI invocation: prints the would-prompt list, exits 0, no prompt."""
    import dummyindex.cli.wire as wire
    from dummyindex.cli import dispatch

    context_dir = _indexed(tmp_path)
    target = "superpowers@claude-plugins-official"
    _write_config(context_dir, [{"kind": "plugin", "target": target, "version": None}])

    fake = _FakePrompt("y")
    monkeypatch.setattr(wire, "_PROMPT", fake)
    # Simulate a non-interactive stdin without --yes.
    monkeypatch.setattr(wire.sys.stdin, "isatty", lambda: False)

    code = dispatch(["wire", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert fake.calls == [], "a non-TTY run must never block on input"
    assert target not in _enabled_plugins(tmp_path)
    assert "not a TTY" in out
    assert "would prompt" in out


@pytest.mark.unit
def test_no_config_is_graceful(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.context/` exists but no config → friendly message, exit 0, no mutation."""
    from dummyindex.cli import dispatch

    _indexed(tmp_path)
    before = _snapshot(tmp_path)

    code = dispatch(["wire", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "no config" in out.lower()
    assert _snapshot(tmp_path) == before


@pytest.mark.unit
def test_no_context_dir_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `.context/` → error on stderr, exit 2, mirroring onboard/status."""
    from dummyindex.cli import dispatch

    code = dispatch(["wire", "--root", str(tmp_path)])
    err = capsys.readouterr().err

    assert code == 2
    assert "does not exist" in err


@pytest.mark.unit
def test_nothing_to_do_does_not_mutate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], _tty: None
) -> None:
    """An already-satisfied plugin → nothing wired, no filesystem change."""
    from dummyindex.cli import dispatch

    context_dir = _indexed(tmp_path)
    target = "superpowers@claude-plugins-official"
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"enabledPlugins": {target: True}}) + "\n", encoding="utf-8"
    )
    _write_config(context_dir, [{"kind": "plugin", "target": target, "version": None}])

    before = _snapshot(tmp_path)
    config_bytes = (context_dir / "config.json").read_bytes()
    settings_bytes = (settings_dir / "settings.json").read_bytes()

    code = dispatch(["wire", "--root", str(tmp_path)])
    out = capsys.readouterr().out

    assert code == 0
    assert "1 already satisfied" in out
    assert _snapshot(tmp_path) == before
    assert (context_dir / "config.json").read_bytes() == config_bytes
    assert (settings_dir / "settings.json").read_bytes() == settings_bytes


@pytest.mark.unit
def test_headless_reconciler_never_calls_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: the HEADLESS reconciler classifies-and-reports only —
    it must never call builtins.input, even for a needs-user plugin install."""
    import builtins

    from dummyindex.context.default_plugins import (
        RunResult,
        WiredEntry,
        WiredKind,
        wire_default_plugins,
    )

    def _no_input(*_a: object, **_k: object) -> str:  # pragma: no cover - guard
        raise AssertionError("headless reconcile must never call input()")

    monkeypatch.setattr(builtins, "input", _no_input)

    def _untrusted_runner(argv: list[str], cwd: Path) -> RunResult:
        if argv[:2] == ["claude", "--version"]:
            return RunResult(0, "1.0.0", "")
        return RunResult(1, "", "untrusted source: pass --yes")

    wired = (
        WiredEntry(
            kind=WiredKind.PLUGIN,
            target="superpowers@claude-plugins-official",
            version=None,
        ),
        WiredEntry(kind=WiredKind.SKILL, target="some-skill", version=None),
    )
    result = wire_default_plugins(
        wired, tmp_path, enabled=True, runner=_untrusted_runner
    )

    # It classified — never prompted: the install failure + the skill both land
    # in needs_user, reported on the result, not via input().
    assert result.needs_user, "needs-user entries must be classified, not dropped"
    assert any("some-skill" == t for t, _ in result.needs_user)
