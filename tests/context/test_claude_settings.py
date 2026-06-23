"""Tests for the shared ``.claude/settings.json`` hook machinery.

``context/claude_settings.py`` holds the preserve-or-refuse settings reader, the
idempotent hook installer (keyed by an in-body sentinel comment), the sentinel
remover, and the atomic JSON writer — extracted from ``context/hooks.py`` so both
the auto-refresh hook and equip's format hook share one proven implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.claude_settings import (
    MalformedSettingsError,
    install_hook_entry,
    load_settings,
    remove_hook_entries,
    write_settings,
)


def _body(sentinel: str, command_tail: str = "echo hi\n") -> dict:
    return {
        "matcher": "*",
        "hooks": [{"type": "command", "command": f"# {sentinel}\n{command_tail}"}],
    }


@pytest.mark.unit
def test_install_then_remove_by_sentinel(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    body = _body("S1")
    assert install_hook_entry(sp, "PostToolUse", body, sentinel="S1") is True
    assert (
        install_hook_entry(sp, "PostToolUse", body, sentinel="S1") is False
    )  # idempotent

    sp_data = json.loads(sp.read_text(encoding="utf-8"))
    sp_data["hooks"]["PostToolUse"].append(
        {"hooks": [{"type": "command", "command": "user-own"}]}
    )
    sp.write_text(json.dumps(sp_data), encoding="utf-8")

    removed = remove_hook_entries(sp, sentinel="S1")
    assert removed == ["PostToolUse"]

    left = json.loads(sp.read_text(encoding="utf-8"))
    assert any(
        "user-own" in h["command"]
        for e in left["hooks"]["PostToolUse"]
        for h in e["hooks"]
    )


@pytest.mark.unit
def test_install_refresh_in_place_when_body_changes(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    assert (
        install_hook_entry(sp, "PostToolUse", _body("S1", "echo old\n"), sentinel="S1")
        is True
    )
    # Same sentinel, different body → refresh in place (returns False = not added).
    assert (
        install_hook_entry(sp, "PostToolUse", _body("S1", "echo new\n"), sentinel="S1")
        is False
    )
    data = json.loads(sp.read_text(encoding="utf-8"))
    entries = data["hooks"]["PostToolUse"]
    assert len(entries) == 1
    assert "echo new" in entries[0]["hooks"][0]["command"]


@pytest.mark.unit
def test_load_settings_absent_is_empty(tmp_path: Path) -> None:
    assert load_settings(tmp_path / ".claude" / "settings.json") == {}


@pytest.mark.unit
def test_load_settings_malformed_refuses(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    broken = '{"permissions": {"allow": ["Bash"]}, OOPS'
    sp.write_text(broken, encoding="utf-8")
    with pytest.raises(MalformedSettingsError):
        load_settings(sp)
    # File left byte-for-byte intact.
    assert sp.read_text(encoding="utf-8") == broken


@pytest.mark.unit
def test_load_settings_non_object_refuses(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(MalformedSettingsError):
        load_settings(sp)


@pytest.mark.unit
def test_install_on_malformed_leaves_file_untouched(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    broken = '{"permissions": {"allow": ["Bash"]}, OOPS'
    sp.write_text(broken, encoding="utf-8")
    with pytest.raises(MalformedSettingsError):
        install_hook_entry(sp, "PostToolUse", _body("S1"), sentinel="S1")
    assert sp.read_text(encoding="utf-8") == broken


@pytest.mark.unit
def test_remove_preserves_other_sentinels_and_user_entries(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    install_hook_entry(sp, "PostToolUse", _body("S1"), sentinel="S1")
    install_hook_entry(sp, "PostToolUse", _body("S2"), sentinel="S2")
    # A user entry with no sentinel.
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["hooks"]["PostToolUse"].append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "user-own"}]}
    )
    sp.write_text(json.dumps(data), encoding="utf-8")

    removed = remove_hook_entries(sp, sentinel="S1")
    assert removed == ["PostToolUse"]
    left = json.loads(sp.read_text(encoding="utf-8"))
    commands = [h["command"] for e in left["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert any("S2" in c for c in commands)  # other sentinel preserved
    assert any("user-own" in c for c in commands)  # user entry preserved
    assert not any("S1" in c for c in commands)  # ours gone


@pytest.mark.unit
def test_remove_absent_sentinel_returns_empty(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    install_hook_entry(sp, "PostToolUse", _body("S1"), sentinel="S1")
    assert remove_hook_entries(sp, sentinel="NOPE") == []


@pytest.mark.unit
def test_refresh_preserves_user_hook_co_located_in_managed_entry(
    tmp_path: Path,
) -> None:
    """A user hook added INSIDE the managed entry's hooks array must survive a
    refresh-in-place when the canonical body changes (the v0.25.0 drop bug).
    """
    sp = tmp_path / ".claude" / "settings.json"
    install_hook_entry(sp, "Stop", _body("S1", "echo old\n"), sentinel="S1")

    # User wires their own hook into our managed entry (the natural place).
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["hooks"]["Stop"][0]["hooks"].append(
        {"type": "command", "command": "DUMMYINDEX_BACKBONE_REFRESH\nrebuild\n"}
    )
    sp.write_text(json.dumps(data), encoding="utf-8")

    # Canonical body changes (an upgrade) → refresh in place.
    install_hook_entry(sp, "Stop", _body("S1", "echo new\n"), sentinel="S1")

    left = json.loads(sp.read_text(encoding="utf-8"))
    entries = left["hooks"]["Stop"]
    assert len(entries) == 1
    commands = [h["command"] for h in entries[0]["hooks"]]
    # Canonical hook refreshed AND the user hook survived.
    assert any("echo new" in c for c in commands)
    assert any("DUMMYINDEX_BACKBONE_REFRESH" in c for c in commands)
    assert not any("echo old" in c for c in commands)


@pytest.mark.unit
def test_refresh_idempotent_after_user_hook_preserved(tmp_path: Path) -> None:
    """Once a user hook is co-located, a second identical install is a no-op
    (writes nothing new, leaves the preserved hook untouched)."""
    sp = tmp_path / ".claude" / "settings.json"
    install_hook_entry(sp, "Stop", _body("S1", "echo c\n"), sentinel="S1")
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["hooks"]["Stop"][0]["hooks"].append(
        {"type": "command", "command": "USERHOOK\nx\n"}
    )
    sp.write_text(json.dumps(data), encoding="utf-8")

    # First call merges (canonical first + user appended). Second is a no-op.
    install_hook_entry(sp, "Stop", _body("S1", "echo c\n"), sentinel="S1")
    before = sp.read_text(encoding="utf-8")
    assert (
        install_hook_entry(sp, "Stop", _body("S1", "echo c\n"), sentinel="S1") is False
    )
    after = sp.read_text(encoding="utf-8")
    assert before == after
    commands = [
        h["command"] for e in json.loads(after)["hooks"]["Stop"] for h in e["hooks"]
    ]
    assert any("USERHOOK" in c for c in commands)


@pytest.mark.unit
def test_remove_keeps_entry_when_user_hook_co_located(tmp_path: Path) -> None:
    """Uninstall strips our sentinel hooks from a shared entry but KEEPS the
    entry when a non-sentinel user hook remains in it."""
    sp = tmp_path / ".claude" / "settings.json"
    install_hook_entry(sp, "Stop", _body("S1"), sentinel="S1")
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["hooks"]["Stop"][0]["hooks"].append(
        {"type": "command", "command": "USERHOOK\nx\n"}
    )
    sp.write_text(json.dumps(data), encoding="utf-8")

    removed = remove_hook_entries(sp, sentinel="S1")
    assert removed == ["Stop"]
    left = json.loads(sp.read_text(encoding="utf-8"))
    commands = [h["command"] for e in left["hooks"]["Stop"] for h in e["hooks"]]
    assert any("USERHOOK" in c for c in commands)  # user hook kept
    assert not any("S1" in c for c in commands)  # our sentinel hook gone


@pytest.mark.unit
def test_remove_drops_entry_when_only_sentinel_hooks(tmp_path: Path) -> None:
    """An entry containing only our sentinel hooks is dropped entirely."""
    sp = tmp_path / ".claude" / "settings.json"
    install_hook_entry(sp, "Stop", _body("S1"), sentinel="S1")
    removed = remove_hook_entries(sp, sentinel="S1")
    assert removed == ["Stop"]
    left = json.loads(sp.read_text(encoding="utf-8"))
    assert "Stop" not in left.get("hooks", {})


@pytest.mark.unit
def test_write_settings_atomic_no_tmp_left(tmp_path: Path) -> None:
    sp = tmp_path / ".claude" / "settings.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    write_settings(sp, {"hooks": {}})
    assert sp.is_file()
    assert not (sp.parent / "settings.json.tmp").exists()
    assert json.loads(sp.read_text(encoding="utf-8")) == {"hooks": {}}
