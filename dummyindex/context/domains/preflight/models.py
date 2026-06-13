"""Frozen dataclasses: SettingsState + PreflightReport.

The preflight report is a read-only snapshot of what already exists under a
repo's ``.claude/`` (and its git state) *before* dummyindex writes anything.
It lets the running ``/dummyindex`` session show "what I will touch vs leave
alone" and refuse to clobber a setup it doesn't understand.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SettingsState:
    """What ``.claude/settings.json`` looks like right now."""

    exists: bool
    parseable: bool                       # valid JSON *object* (False ⇒ won't touch)
    user_hook_events: tuple[str, ...]     # events carrying non-dummyindex hooks
    dummyindex_hook_present: bool         # our SessionStart sentinel already there

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "parseable": self.parseable,
            "user_hook_events": list(self.user_hook_events),
            "dummyindex_hook_present": self.dummyindex_hook_present,
        }


@dataclass(frozen=True)
class PreflightReport:
    """Read-only inventory of a repo's existing Claude Code setup."""

    project_root: str
    is_git_repo: bool
    git_clean: Optional[bool]             # None ⇒ not a git repo / git unavailable
    settings: SettingsState
    rule_files: tuple[str, ...]           # repo-relative POSIX paths under .claude/rules
    project_agents: tuple[str, ...]       # agent names (file stems) under .claude/agents
    claude_md_exists: bool
    claude_md_has_managed_block: bool     # already carries a dummyindex managed block
    # Defaults keep older direct constructions working (additive fields).
    context_exists: bool = False          # a .context/ directory is present
    context_owned: Optional[bool] = None  # None ⇒ absent/empty; False ⇒ FOREIGN (hands off)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "is_git_repo": self.is_git_repo,
            "git_clean": self.git_clean,
            "settings": self.settings.to_dict(),
            "rule_files": list(self.rule_files),
            "project_agents": list(self.project_agents),
            "claude_md_exists": self.claude_md_exists,
            "claude_md_has_managed_block": self.claude_md_has_managed_block,
            "context_exists": self.context_exists,
            "context_owned": self.context_owned,
        }
