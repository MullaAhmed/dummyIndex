"""Tests for the SessionStart drift hook (v0.13.5+) and the `hooks` CLI verb.

Pre-0.13.5 also installed a ``git post-commit`` hook and a Claude
``PostToolUse`` hook. Those were retired because they re-ran the
deterministic backbone on every edit and clobbered council-enriched
feature folders. Several tests below exercise the upgrade path —
``install`` must scrub the legacy entries it finds.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.hooks import (
    HookStatus,
    install,
    status,
    uninstall,
)

_LEGACY_SENTINEL_HOOK = {
    "matcher": "Edit|Write|MultiEdit",
    "hooks": [
        {
            "type": "command",
            "command": (
                "# DUMMYINDEX_AUTO_REFRESH\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context rebuild --changed --root "$CLAUDE_PROJECT_DIR" '
                ">/dev/null 2>&1 &\n"
                "exit 0\n"
            ),
        }
    ],
}

_LEGACY_GIT_HOOK_BODY = "#!/usr/bin/env bash\n# DUMMYINDEX_AUTO_REFRESH\nexit 0\n"


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q"], cwd=str(path), check=True, capture_output=True
    )


def _write_settings(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ----- install --------------------------------------------------------------


@pytest.mark.integration
def test_install_writes_session_start_hook(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = install(tmp_path)
    assert "claude/SessionStart" in result.installed
    assert result.errors == ()

    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "SessionStart" in settings["hooks"]
    cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "DUMMYINDEX_AUTO_REFRESH" in cmd
    assert "plan-update" in cmd


@pytest.mark.integration
def test_install_does_not_create_git_post_commit(tmp_path: Path) -> None:
    """The post-commit shell hook was retired in 0.13.5."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    assert not (tmp_path / ".git" / "hooks" / "post-commit").exists()


@pytest.mark.integration
def test_install_is_idempotent(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    second = install(tmp_path)
    assert second.installed == ()
    assert "claude/SessionStart" in second.skipped
    # An unchanged re-install reports nothing as refreshed.
    assert second.refreshed == ()


@pytest.mark.integration
def test_install_reports_refreshed_when_body_changes(tmp_path: Path) -> None:
    """When an upgrade rewrites a managed hook's body in place, install must
    report it as `refreshed`, not `skipped (already current)`."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    # An OLD-style managed Stop entry: our sentinel, but a stale body.
    _write_settings(
        settings_path,
        {
            "hooks": {
                "Stop": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "# DUMMYINDEX_AUTO_REFRESH\nold body\n",
                            }
                        ],
                    }
                ]
            }
        },
    )

    result = install(tmp_path)
    assert "claude/Stop" in result.refreshed
    assert "claude/Stop" not in result.skipped
    # The body was actually rewritten to the canonical reconcile-gate hook.
    after = json.loads(settings_path.read_text())
    cmds = [h["command"] for e in after["hooks"]["Stop"] for h in e["hooks"]]
    assert any("reconcile-gate" in c for c in cmds)


@pytest.mark.integration
def test_install_refreshed_line_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI prints a distinct 'refreshed' line, not 'already current'."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {
            "hooks": {
                "Stop": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "# DUMMYINDEX_AUTO_REFRESH\nstale\n",
                            }
                        ],
                    }
                ]
            }
        },
    )
    rc = dispatch(["hooks", "install", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "refreshed" in out
    assert "claude/Stop" in out


@pytest.mark.integration
def test_install_works_without_git(tmp_path: Path) -> None:
    """No .git/ → SessionStart still installs; nothing depends on git anymore."""
    result = install(tmp_path)
    assert "claude/SessionStart" in result.installed


@pytest.mark.integration
def test_install_preserves_user_authored_hooks(tmp_path: Path) -> None:
    """User entries (no sentinel) survive a fresh install."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo user"}],
                    }
                ]
            }
        },
    )

    install(tmp_path)
    after = json.loads(settings_path.read_text())
    # User's entry + our entry → 2 entries total.
    assert len(after["hooks"]["SessionStart"]) == 2


@pytest.mark.integration
def test_install_preserves_user_hook_co_located_in_managed_stop_entry(
    tmp_path: Path,
) -> None:
    """A user hook wired INTO our managed Stop entry survives an upgrade
    re-install even when the canonical Stop body changed (the v0.25.0
    DUMMYINDEX_BACKBONE_REFRESH-drop regression, end-to-end)."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"

    install(tmp_path)  # writes the canonical Stop entry

    # User appends their own hook into our managed Stop entry's hooks array.
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    stop_entries = data["hooks"]["Stop"]
    stop_entries[0]["hooks"].append(
        {"type": "command", "command": "DUMMYINDEX_BACKBONE_REFRESH\nrefresh\n"}
    )
    settings_path.write_text(json.dumps(data), encoding="utf-8")

    # Re-install (upgrade). The canonical hooks refresh; the user hook stays.
    install(tmp_path)

    after = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [h["command"] for e in after["hooks"]["Stop"] for h in e["hooks"]]
    assert any("DUMMYINDEX_BACKBONE_REFRESH" in c for c in commands)
    # Our canonical hooks are still present too (reconcile-gate + memory nudge).
    assert any("reconcile-gate" in c for c in commands)


@pytest.mark.integration
def test_install_with_co_located_user_hook_reports_no_false_refresh(
    tmp_path: Path,
) -> None:
    """A user hook co-located in our managed Stop entry must not make every
    subsequent install report 'refreshed' — the classify-by-canonical-body bug
    would compare the stored entry (incl. the user hook) against our hookless
    canonical body and always differ, lying that settings.json was rewritten."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"

    install(tmp_path)
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    data["hooks"]["Stop"][0]["hooks"].append(
        {"type": "command", "command": "DUMMYINDEX_BACKBONE_REFRESH\nrefresh\n"}
    )
    settings_path.write_text(json.dumps(data), encoding="utf-8")

    before = settings_path.read_bytes()
    result = install(tmp_path)
    after = settings_path.read_bytes()

    # Nothing changed → Stop is skipped, never refreshed, and the file is byte-stable.
    assert "claude/Stop" not in result.refreshed
    assert "claude/Stop" in result.skipped
    assert before == after


@pytest.mark.integration
def test_install_preserves_malformed_settings(tmp_path: Path) -> None:
    """A malformed settings.json must never be clobbered to just our hook.

    Regression: ``_install_claude_hook`` used to reset ``settings = {}`` on a
    ``JSONDecodeError`` and then overwrite the file — silently destroying the
    user's permissions / env / other hooks. The fix is preserve-or-refuse:
    leave the file byte-for-byte intact and surface the failure.
    """
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    broken = '{"permissions": {"allow": ["Bash"]}, OOPS not valid json'
    settings_path.write_text(broken, encoding="utf-8")

    result = install(tmp_path)

    # File left exactly as it was — no clobber.
    assert settings_path.read_text(encoding="utf-8") == broken
    # The failure is surfaced, not swallowed, and we did not claim success.
    assert any(name == "claude/SessionStart" for name, _ in result.errors)
    assert "claude/SessionStart" not in result.installed


@pytest.mark.integration
def test_install_refuses_non_object_settings(tmp_path: Path) -> None:
    """Valid JSON that isn't an object (e.g. a list) must not crash or clobber.

    Regression: ``settings.setdefault("hooks", {})`` raised an uncaught
    ``AttributeError`` when the top-level JSON was a list/number/string.
    """
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = '["not", "an", "object"]'
    settings_path.write_text(payload, encoding="utf-8")

    result = install(tmp_path)

    assert settings_path.read_text(encoding="utf-8") == payload
    assert any(name == "claude/SessionStart" for name, _ in result.errors)
    assert "claude/SessionStart" not in result.installed


# ----- legacy scrub (upgrade path) ----------------------------------------


@pytest.mark.integration
def test_install_scrubs_legacy_post_tool_use(tmp_path: Path) -> None:
    """Upgrading from <=0.13.4 must remove our PostToolUse entry."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK]}},
    )

    result = install(tmp_path)
    assert "claude/PostToolUse (legacy)" in result.removed

    after = json.loads(settings_path.read_text())
    # The whole PostToolUse key is gone because the only entry was ours.
    assert "PostToolUse" not in after.get("hooks", {})


@pytest.mark.integration
def test_install_scrubs_legacy_git_post_commit(tmp_path: Path) -> None:
    """Upgrade path: our legacy post-commit script is deleted on install."""
    _init_git_repo(tmp_path)
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_GIT_HOOK_BODY, encoding="utf-8")

    result = install(tmp_path)
    assert "git/post-commit (legacy)" in result.removed
    assert not target.exists()


@pytest.mark.integration
def test_install_leaves_foreign_git_post_commit_alone(tmp_path: Path) -> None:
    """A user-authored post-commit hook (no sentinel) must survive."""
    _init_git_repo(tmp_path)
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/bin/bash\necho user\n", encoding="utf-8")

    result = install(tmp_path)
    assert "git/post-commit (legacy)" not in result.removed
    assert target.exists()


@pytest.mark.integration
def test_install_scrubs_legacy_post_commit_in_submodule(tmp_path: Path) -> None:
    """For a submodule, the real hooks dir lives under the superproject's
    ``.git/modules/<name>`` — the legacy scrub must follow the `.git` pointer
    file there, not look in ``<submodule>/.git/hooks`` (which doesn't exist)."""
    module_dir = tmp_path / ".git" / "modules" / "backend"
    (module_dir / "hooks").mkdir(parents=True)
    submodule = tmp_path / "backend"
    submodule.mkdir()
    (submodule / ".git").write_text(
        "gitdir: ../.git/modules/backend\n", encoding="utf-8"
    )
    target = module_dir / "hooks" / "post-commit"
    target.write_text(_LEGACY_GIT_HOOK_BODY, encoding="utf-8")

    result = install(submodule)
    assert "git/post-commit (legacy)" in result.removed
    assert not target.exists()


@pytest.mark.integration
def test_install_scrubs_legacy_post_tool_use_keeps_user_entries(
    tmp_path: Path,
) -> None:
    """Legacy scrub must remove only our PostToolUse entries, not the user's."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    user_entry = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "echo user-hook"}],
    }
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK, user_entry]}},
    )

    install(tmp_path)
    after = json.loads(settings_path.read_text())
    assert after["hooks"]["PostToolUse"] == [user_entry]


# ----- uninstall ------------------------------------------------------------


@pytest.mark.integration
def test_uninstall_removes_session_start(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert "claude/SessionStart" in result.removed


# ----- PreToolUse Write guard (enforce-managed-doc-homes) -------------------


def _pre_tool_use_commands(settings_path: Path) -> list[str]:
    """All command strings under the PreToolUse event."""
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    return [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]


@pytest.mark.integration
def test_install_wires_pre_tool_use_write_guard(tmp_path: Path) -> None:
    """Local install wires the PreToolUse Write guard: matcher ``Write``, our
    sentinel, the ``command -v dummyindex`` self-gate, and the guard-doc-write
    command with ``--root``. Local bodies are verbatim — no global guard."""
    from dummyindex.context import hooks as H

    _init_git_repo(tmp_path)
    install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text())
    entries = settings["hooks"]["PreToolUse"]
    assert len(entries) == 1
    entry = entries[0]
    # Edit/MultiEdit require the target to pre-exist, so only Write can leak.
    assert entry["matcher"] == "Write"
    cmd = entry["hooks"][0]["command"]
    assert "DUMMYINDEX_AUTO_REFRESH" in cmd  # sentinel recognised/scrubbable
    assert "command -v dummyindex" in cmd  # self-gate present
    assert H._SILENT_GATE in cmd  # built from the silent gate variant
    assert 'dummyindex context guard-doc-write --root "$CLAUDE_PROJECT_DIR"' in cmd
    # Local bodies carry no defer-check guard (that's a global-scope concern).
    assert H._GLOBAL_GUARD not in cmd
    assert "hooks defer-check" not in cmd


@pytest.mark.integration
def test_global_install_pre_tool_use_carries_self_gate_and_global_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A GLOBAL-scope install inserts the defer-check guard immediately after
    the PreToolUse hook's ``_SILENT_GATE`` self-gate — assert BOTH present and
    in that order (so a repo with its own --local install suppresses it)."""
    from dummyindex.context import hooks as H

    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    install(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    entry = settings["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Write"
    cmd = entry["hooks"][0]["command"]
    assert H._SILENT_GATE in cmd  # self-gate
    assert H._GLOBAL_GUARD in cmd  # defer-check guard inserted by _guard_body
    assert H._SILENT_GATE + H._GLOBAL_GUARD in cmd  # guard right after the gate
    assert "guard-doc-write" in cmd


@pytest.mark.integration
def test_pre_tool_use_guard_idempotent_byte_stable(tmp_path: Path) -> None:
    """A second install adds no duplicate guard and leaves settings.json
    byte-identical; exactly one PreToolUse guard entry remains."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    before = settings_path.read_bytes()
    install(tmp_path)
    after = settings_path.read_bytes()
    assert before == after
    data = json.loads(settings_path.read_text())
    assert len(data["hooks"]["PreToolUse"]) == 1
    cmds = _pre_tool_use_commands(settings_path)
    assert sum("guard-doc-write" in c for c in cmds) == 1


@pytest.mark.integration
def test_uninstall_removes_pre_tool_use_guard(tmp_path: Path) -> None:
    """uninstall scrubs the guard automatically (PreToolUse is in
    CURRENT_CLAUDE_EVENTS) — no manual uninstall edit needed."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert "claude/PreToolUse" in result.removed
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "PreToolUse" not in settings.get("hooks", {})


@pytest.mark.integration
def test_legacy_post_tool_use_scrub_keeps_pre_tool_use_guard(tmp_path: Path) -> None:
    """The legacy PostToolUse scrub removes the legacy entry but must NOT touch
    the new PreToolUse guard — PreToolUse is a different event key, not in
    _LEGACY_CLAUDE_EVENTS."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK]}},
    )

    result = install(tmp_path)

    # Legacy entry scrubbed...
    assert "claude/PostToolUse (legacy)" in result.removed
    after = json.loads(settings_path.read_text())
    assert "PostToolUse" not in after.get("hooks", {})
    # ...and the new PreToolUse guard is installed and intact alongside it.
    assert "claude/PreToolUse" in result.installed
    assert any("guard-doc-write" in c for c in _pre_tool_use_commands(settings_path))


@pytest.mark.integration
def test_pre_tool_use_preserves_co_located_and_foreign_user_hooks(
    tmp_path: Path,
) -> None:
    """A user hook co-located in our managed PreToolUse entry survives a
    re-install (upgrade); a SEPARATE foreign PreToolUse entry survives both
    install and uninstall — each byte-untouched. (The co-located hook rides
    its managed entry out on uninstall, matching the established entry-level
    Stop/SessionStart uninstall behaviour.)"""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"

    install(tmp_path)

    # User co-locates a hook in our managed entry AND adds a separate entry.
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    colocated_cmd = "echo COLOCATED_USER_HOOK\n"
    foreign = {
        "matcher": "Read",
        "hooks": [{"type": "command", "command": "echo FOREIGN_USER_HOOK\n"}],
    }
    data["hooks"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": colocated_cmd}
    )
    data["hooks"]["PreToolUse"].append(foreign)
    settings_path.write_text(json.dumps(data), encoding="utf-8")

    # Re-install (upgrade): both user hooks survive byte-untouched, guard stays.
    install(tmp_path)
    after = json.loads(settings_path.read_text(encoding="utf-8"))
    cmds = _pre_tool_use_commands(settings_path)
    assert colocated_cmd in cmds  # co-located preserved across re-install
    assert "echo FOREIGN_USER_HOOK\n" in cmds
    assert any("guard-doc-write" in c for c in cmds)
    assert foreign in after["hooks"]["PreToolUse"]  # foreign entry verbatim

    # Uninstall: the SEPARATE foreign entry survives byte-untouched; our managed
    # entry (carrying the co-located hook) is removed wholesale.
    uninstall(tmp_path)
    after = json.loads(settings_path.read_text(encoding="utf-8"))
    pre = after["hooks"]["PreToolUse"]
    assert foreign in pre  # foreign entry untouched
    cmds = [h["command"] for e in pre for h in e["hooks"]]
    assert "echo FOREIGN_USER_HOOK\n" in cmds
    assert not any("guard-doc-write" in c for c in cmds)  # guard scrubbed
    assert colocated_cmd not in cmds  # rode out with the managed entry


# ----- statusline nudge (emit-only) -----------------------------------------


from dummyindex.context.hooks import statusline_nudge  # noqa: E402


def _write_global_settings(home: Path, payload: dict) -> None:
    """Write ``~/.claude/settings.json`` under a fake home dir."""
    _write_settings(home / ".claude" / "settings.json", payload)


def test_statusline_nudge_silent_when_local_sets_status_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local settings already defines ``statusLine`` ⇒ no nudge, and the
    settings file is left byte-for-byte unchanged (emit-only: never writes)."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "proj"
    local_path = project / ".claude" / "settings.json"
    _write_settings(
        local_path,
        {"statusLine": {"type": "command", "command": "echo hi"}},
    )
    before = local_path.read_bytes()

    assert statusline_nudge(project) is None
    # Emit-only: the helper must not touch the settings file.
    assert local_path.read_bytes() == before


def test_statusline_nudge_silent_when_global_sets_status_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Global settings defines ``statusLine`` (local doesn't) ⇒ silent."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "proj"
    _write_global_settings(
        home,
        {"statusLine": {"type": "command", "command": "echo hi"}},
    )
    # Local has no statusLine.
    _write_settings(project / ".claude" / "settings.json", {"permissions": {}})

    assert statusline_nudge(project) is None


def test_statusline_nudge_emits_when_neither_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither local nor global defines ``statusLine`` ⇒ exactly one nudge,
    and NOTHING is written/created under either settings path."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "proj"
    local_path = project / ".claude" / "settings.json"
    global_path = home / ".claude" / "settings.json"

    nudge = statusline_nudge(project)

    assert isinstance(nudge, str)
    assert nudge  # non-empty, exactly one line
    assert "\n" not in nudge.strip()  # one-line nudge
    # It carries the snippet to add — point at the shipped statusline command.
    assert "statusLine" in nudge
    assert "dummyindex context statusline" in nudge
    # Emit-only: never writes or creates either settings file.
    assert not local_path.exists()
    assert not global_path.exists()


def test_statusline_nudge_emits_when_settings_absent_entirely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both settings files missing on disk ⇒ treated as absent ⇒ nudge."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "proj"

    assert statusline_nudge(project) is not None


def test_statusline_nudge_swallows_malformed_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed settings.json is swallowed, treated as absent, never raises.

    With both files unreadable-as-config and neither defining ``statusLine``,
    the helper degrades to "absent" and still emits the nudge."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "proj"
    local_path = project / ".claude" / "settings.json"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text("{ OOPS not valid json", encoding="utf-8")

    # Must not raise (MalformedSettingsError is swallowed) and, since no
    # parseable statusLine exists anywhere, still nudges.
    nudge = statusline_nudge(project)
    assert nudge is not None
    # The malformed file was not rewritten by the read.
    assert local_path.read_text(encoding="utf-8") == "{ OOPS not valid json"


def test_statusline_nudge_silent_when_malformed_global_but_local_sets_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed global is swallowed (treated absent); a local that defines
    ``statusLine`` still wins ⇒ silent."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "proj"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text("}{ broken", encoding="utf-8")
    _write_settings(
        project / ".claude" / "settings.json",
        {"statusLine": "string-form-is-also-truthy"},
    )

    assert statusline_nudge(project) is None


@pytest.mark.integration
def test_install_surfaces_statusline_nudge_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install() surfaces the nudge on HookResult when no statusLine is set,
    and writes the nudge to NO settings file (only the hooks block changes)."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _init_git_repo(tmp_path)

    result = install(tmp_path)

    assert any("statusLine" in n for n in result.nudges)
    # The hooks block was written, but statusLine was never added to it.
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "statusLine" not in settings


@pytest.mark.integration
def test_install_no_statusline_nudge_when_already_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When local settings already defines statusLine, install emits no nudge
    and the existing statusLine value is preserved untouched."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {"statusLine": {"type": "command", "command": "echo mine"}},
    )

    result = install(tmp_path)

    assert not any("statusLine" in n for n in result.nudges)
    after = json.loads(settings_path.read_text())
    assert after["statusLine"] == {"type": "command", "command": "echo mine"}


@pytest.mark.integration
def test_uninstall_also_scrubs_legacy_entries(tmp_path: Path) -> None:
    """Even if the install already happened, uninstall removes legacy stragglers."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {"hooks": {"PostToolUse": [_LEGACY_SENTINEL_HOOK]}},
    )
    target = tmp_path / ".git" / "hooks" / "post-commit"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_LEGACY_GIT_HOOK_BODY, encoding="utf-8")

    result = uninstall(tmp_path)
    assert "claude/PostToolUse" in result.removed
    assert "git/post-commit" in result.removed


@pytest.mark.integration
def test_uninstall_leaves_user_session_start_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": "echo user"}],
                    }
                ]
            }
        },
    )
    install(tmp_path)
    uninstall(tmp_path)
    after = json.loads(settings_path.read_text())
    remaining = after.get("hooks", {}).get("SessionStart", [])
    assert len(remaining) == 1
    assert remaining[0]["hooks"][0]["command"] == "echo user"


@pytest.mark.integration
def test_uninstall_idempotent_when_nothing_present(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = uninstall(tmp_path)
    assert result.removed == ()
    assert len(result.skipped) > 0


@pytest.mark.integration
def test_uninstall_preserves_malformed_settings(tmp_path: Path) -> None:
    """Uninstall must not clobber a malformed settings.json either."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    broken = '{"permissions": {"allow": ["Bash"]}, OOPS not valid json'
    settings_path.write_text(broken, encoding="utf-8")

    result = uninstall(tmp_path)

    assert settings_path.read_text(encoding="utf-8") == broken
    assert any(name == "claude/settings.json" for name, _ in result.errors)


# ----- status ---------------------------------------------------------------


@pytest.mark.integration
def test_status_false_when_absent(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    s = status(tmp_path)
    assert s == HookStatus(
        claude_session_start=False,
        claude_stop=False,
        claude_pre_compact=False,
        claude_pre_tool_use=False,
    )
    assert not s.all_installed


@pytest.mark.integration
def test_status_true_after_install(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    s = status(tmp_path)
    assert s.all_installed
    assert s.claude_session_start


# ----- CLI dispatch ---------------------------------------------------------


@pytest.mark.integration
def test_cli_hooks_install_status_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert dispatch(["hooks", "install"]) == 0
    assert "installed" in capsys.readouterr().out

    assert dispatch(["hooks", "status"]) == 0
    out = capsys.readouterr().out
    assert "✓" in out
    assert "claude/SessionStart" in out

    assert dispatch(["hooks", "uninstall"]) == 0
    assert "removed" in capsys.readouterr().out

    # Status now non-zero (not all installed).
    assert dispatch(["hooks", "status"]) == 1


@pytest.mark.integration
def test_cli_hooks_unknown_verb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = dispatch(["hooks", "fictional"])
    assert rc == 2
    assert "unknown hooks verb" in capsys.readouterr().err


# ----- ingest auto-installs hooks ------------------------------------------


@pytest.mark.integration
def test_ingest_auto_installs_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dummyindex ingest` should install the SessionStart hook by default."""
    import shutil

    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "auto_hook_ingest"
    shutil.copytree(fixture, target)
    _init_git_repo(target)

    monkeypatch.chdir(target)
    assert dispatch(["init"]) == 0

    s = status(target)
    assert s.all_installed, "ingest should install the SessionStart drift hook"


@pytest.mark.integration
def test_ingest_skips_hooks_with_no_hooks_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil

    fixture = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"
    target = tmp_path / "no_hooks_ingest"
    shutil.copytree(fixture, target)
    _init_git_repo(target)

    monkeypatch.chdir(target)
    assert dispatch(["init", "--no-hooks"]) == 0

    s = status(target)
    assert not s.claude_session_start


def test_install_writes_memory_session_start_command(tmp_path):
    import json

    from dummyindex.context.hooks import install

    install(tmp_path)
    settings = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    commands = [
        h["command"]
        for entry in settings["hooks"]["SessionStart"]
        for h in entry["hooks"]
    ]
    assert any("plan-update" in c for c in commands)
    assert any("memory session-start" in c for c in commands)


def _session_start_commands(settings_path: Path) -> list[str]:
    """All command strings under the SessionStart event."""
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    return [
        h["command"]
        for entry in settings["hooks"]["SessionStart"]
        for h in entry["hooks"]
    ]


@pytest.mark.integration
def test_install_writes_gc_signal_command_alongside_existing(tmp_path: Path) -> None:
    """SessionStart carries the gc-signal throttle probe ALONGSIDE the existing
    plan-update + memory session-start commands — none displaced."""
    install(tmp_path)
    commands = _session_start_commands(tmp_path / ".claude" / "settings.json")
    assert any("plan-update" in c for c in commands)
    assert any("memory session-start" in c for c in commands)
    assert any("gc signal" in c for c in commands)


@pytest.mark.integration
def test_gc_signal_command_matches_session_start_shape(tmp_path: Path) -> None:
    """The gc-signal entry uses the same managed-comment + self-gate + --root
    convention as the other SessionStart commands."""
    install(tmp_path)
    commands = _session_start_commands(tmp_path / ".claude" / "settings.json")
    gc_cmds = [c for c in commands if "gc signal" in c]
    assert len(gc_cmds) == 1
    gc_cmd = gc_cmds[0]
    assert "dummyindex context gc signal" in gc_cmd
    assert 'dummyindex context gc signal --root "$CLAUDE_PROJECT_DIR"' in gc_cmd
    assert "DUMMYINDEX_AUTO_REFRESH" in gc_cmd
    assert "drift reporting disabled" in gc_cmd  # SessionStart self-gate variant


@pytest.mark.integration
def test_install_idempotent_does_not_duplicate_gc_signal(tmp_path: Path) -> None:
    """Installing twice must not append a second gc-signal command — the
    SessionStart entry stays at exactly three managed commands."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    install(tmp_path)
    commands = _session_start_commands(tmp_path / ".claude" / "settings.json")
    assert sum("gc signal" in c for c in commands) == 1
    assert sum("plan-update" in c for c in commands) == 1
    assert sum("memory session-start" in c for c in commands) == 1


@pytest.mark.integration
def test_install_writes_stop_and_precompact_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = install(tmp_path)
    assert set(result.installed) == {
        "claude/SessionStart",
        "claude/Stop",
        "claude/PreCompact",
        "claude/PreToolUse",
    }
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    stop_cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    pre_cmd = settings["hooks"]["PreCompact"][0]["hooks"][0]["command"]
    assert "memory nudge" in stop_cmd
    assert "DUMMYINDEX_AUTO_REFRESH" in stop_cmd
    assert "memory breadcrumb" in pre_cmd


@pytest.mark.integration
def test_status_true_after_install_all_four(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    s = status(tmp_path)
    assert (
        s.claude_session_start
        and s.claude_stop
        and s.claude_pre_compact
        and s.claude_pre_tool_use
    )
    assert s.all_installed


@pytest.mark.integration
def test_uninstall_removes_stop_and_precompact(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert "claude/Stop" in result.removed
    assert "claude/PreCompact" in result.removed


@pytest.mark.integration
def test_cli_hooks_status_lists_all_four(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    dispatch(["hooks", "install"])
    capsys.readouterr()
    assert dispatch(["hooks", "status"]) == 0
    out = capsys.readouterr().out
    assert "claude/SessionStart" in out
    assert "claude/Stop" in out
    assert "claude/PreCompact" in out
    assert "claude/PreToolUse" in out


# ----- Stop gate + global scope (v0.23.0) -----------------------------------

from dummyindex.context import hooks as _H  # noqa: E402


def test_stop_entry_has_nudge_and_gate(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _H.install(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    stop = settings["hooks"]["Stop"]
    assert len(stop) == 1  # single entry...
    cmds = [h["command"] for h in stop[0]["hooks"]]
    assert any("memory nudge" in c for c in cmds)
    assert any("reconcile-gate" in c for c in cmds)  # ...two commands


def test_install_idempotent_with_gate(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _H.install(tmp_path)
    _H.install(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["Stop"]) == 1
    assert len(settings["hooks"]["Stop"][0]["hooks"]) == 2


def test_global_install_targets_home_and_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _H.install(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    cmds = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
    assert any("hooks defer-check" in c for c in cmds)


def test_global_bodies_guarded_local_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _init_git_repo(tmp_path)
    _H.install(tmp_path, scope="local")
    local = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    lcmds = [h["command"] for e in local["hooks"]["Stop"] for h in e["hooks"]]
    assert not any("defer-check" in c for c in lcmds)


def test_local_install_present_detects_sentinel(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    assert _H.local_install_present(tmp_path) is False
    _H.install(tmp_path, scope="local")
    assert _H.local_install_present(tmp_path) is True


def test_global_uninstall_scrubs_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _H.install(tmp_path, scope="global")
    _H.uninstall(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert "hooks" not in settings or not settings["hooks"]


def test_global_status_independent_of_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    _init_git_repo(tmp_path)
    _H.install(tmp_path, scope="local")
    assert _H.status(tmp_path, scope="local").all_installed is True
    assert _H.status(tmp_path, scope="global").all_installed is False


# ----- hook-body labelling + degraded-mode signal ---------------------------


def _all_managed_commands(settings_path: Path) -> list[str]:
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    return [
        h["command"]
        for entries in (data.get("hooks") or {}).values()
        for e in entries
        for h in e["hooks"]
        if "DUMMYINDEX_AUTO_REFRESH" in h.get("command", "")
    ]


@pytest.mark.integration
def test_new_bodies_carry_clearer_label_and_legacy_sentinel(tmp_path: Path) -> None:
    """New install bodies keep the legacy sentinel substring (matcher compat)
    AND carry the clearer managed-hooks comment."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    cmds = _all_managed_commands(settings_path)
    assert cmds  # something was installed under our sentinel
    for cmd in cmds:
        assert "DUMMYINDEX_AUTO_REFRESH" in cmd  # legacy recognition preserved
        assert "DUMMYINDEX_HOOKS" in cmd  # clearer label added


@pytest.mark.integration
def test_session_start_has_degraded_mode_echo(tmp_path: Path) -> None:
    """A PATH-broken CLI surfaces once per session via the SessionStart hook —
    Stop/PreCompact stay silent (their stdout has protocol meaning)."""
    _init_git_repo(tmp_path)
    install(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    ss_cmds = [h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]]
    assert any("drift reporting disabled" in c for c in ss_cmds)
    stop_cmds = [h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]]
    assert not any("drift reporting disabled" in c for c in stop_cmds)


@pytest.mark.integration
def test_uninstall_removes_old_style_bodies(tmp_path: Path) -> None:
    """Entries written with the OLD-style body (legacy sentinel only) are still
    recognised and scrubbed on uninstall."""
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write_settings(
        settings_path,
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "# DUMMYINDEX_AUTO_REFRESH\nold\n",
                            }
                        ],
                    }
                ]
            }
        },
    )
    result = uninstall(tmp_path)
    assert "claude/SessionStart" in result.removed
