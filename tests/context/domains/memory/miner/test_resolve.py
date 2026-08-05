"""Store resolution must honor CLAUDE_CONFIG_DIR and never hardcode a path."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import (
    resolve_claude_config_dir,
    resolve_transcript_store,
)

pytestmark = pytest.mark.unit


def test_falls_back_to_dot_claude_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert resolve_claude_config_dir() == Path.home() / ".claude"
    assert resolve_transcript_store() == Path.home() / ".claude" / "projects"


def test_honors_claude_config_dir_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/claude-os-home/.claude-os")
    assert resolve_claude_config_dir() == Path("/tmp/claude-os-home/.claude-os")
    assert resolve_transcript_store() == Path("/tmp/claude-os-home/.claude-os/projects")


def test_override_wins_over_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/should/not/be/used")
    override = tmp_path / "fixture-config-dir"
    assert resolve_claude_config_dir(override=override) == override
    assert resolve_transcript_store(override=override) == override / "projects"


def test_override_wins_with_no_env_var_either(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    override = tmp_path / "other-store"
    assert resolve_transcript_store(override=override) == override / "projects"
