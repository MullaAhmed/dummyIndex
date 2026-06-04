"""Build a :class:`PreflightReport` by inspecting a repo's existing setup.

Read-only. Touches nothing — it reads ``.claude/`` and queries git so the
caller can decide what is safe to write. The hook sentinel and the CLAUDE.md
managed-block marker are imported from their owning modules rather than
re-spelled here, so this stays in lock-step with what install actually writes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from dummyindex.context.hooks import CURRENT_CLAUDE_EVENTS, SENTINEL
from dummyindex.context.output.bootstrap import BEGIN_MARKER

from .models import PreflightReport, SettingsState

_RULE_GLOB = "**/*.md"
_AGENT_GLOB = "*.md"


def build_preflight_report(project_root: Path) -> PreflightReport:
    """Inventory the existing Claude Code setup at ``project_root``.

    Never writes. Safe to call before any ``.context/`` build so the running
    session can show the user what dummyindex will and won't touch.
    """
    project_root = project_root.resolve()
    claude_dir = project_root / ".claude"

    settings = _inspect_settings(claude_dir / "settings.json")
    rule_files = _list_rule_files(claude_dir / "rules", project_root)
    project_agents = _list_agent_names(claude_dir / "agents")

    claude_md = claude_dir / "CLAUDE.md"
    claude_md_exists = claude_md.is_file()
    claude_md_has_managed_block = claude_md_exists and _has_managed_block(claude_md)

    is_git_repo = (project_root / ".git").is_dir()
    git_clean = _git_clean(project_root) if is_git_repo else None

    return PreflightReport(
        project_root=str(project_root),
        is_git_repo=is_git_repo,
        git_clean=git_clean,
        settings=settings,
        rule_files=rule_files,
        project_agents=project_agents,
        claude_md_exists=claude_md_exists,
        claude_md_has_managed_block=claude_md_has_managed_block,
    )


def _inspect_settings(settings_path: Path) -> SettingsState:
    """Classify ``settings.json`` without ever rewriting it."""
    if not settings_path.is_file():
        return SettingsState(
            exists=False,
            parseable=True,
            user_hook_events=(),
            dummyindex_hook_present=False,
        )
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SettingsState(
            exists=True,
            parseable=False,
            user_hook_events=(),
            dummyindex_hook_present=False,
        )
    if not isinstance(data, dict):
        return SettingsState(
            exists=True,
            parseable=False,
            user_hook_events=(),
            dummyindex_hook_present=False,
        )

    # Tolerate any shape — a settings file in the wild may carry nulls,
    # non-string commands, or non-list values. Preflight must never crash on
    # one; it classifies and moves on.
    hooks_block = data.get("hooks")
    user_events: list[str] = []
    ours = False
    if isinstance(hooks_block, dict):
        for event, entries in hooks_block.items():
            if not isinstance(entries, list):
                continue
            event_has_user = False
            for entry in entries:
                inner = entry.get("hooks") if isinstance(entry, dict) else None
                for h in inner if isinstance(inner, list) else []:
                    command = h.get("command") if isinstance(h, dict) else None
                    if not isinstance(command, str):
                        command = ""
                    if SENTINEL in command:
                        # Only the event we actually install into (SessionStart)
                        # counts as "our hook present"; a leftover legacy
                        # sentinel under another event will be scrubbed, not
                        # refreshed, so it must not read as already-installed.
                        if event in CURRENT_CLAUDE_EVENTS:
                            ours = True
                    else:
                        event_has_user = True
            if event_has_user:
                user_events.append(event)

    return SettingsState(
        exists=True,
        parseable=True,
        user_hook_events=tuple(sorted(user_events)),
        dummyindex_hook_present=ours,
    )


def _list_rule_files(rules_dir: Path, project_root: Path) -> tuple[str, ...]:
    """Repo-relative POSIX paths of every markdown under ``.claude/rules``."""
    if not rules_dir.is_dir():
        return ()
    out: list[str] = []
    for path in rules_dir.glob(_RULE_GLOB):
        if not path.is_file():
            continue
        try:
            out.append(path.relative_to(project_root).as_posix())
        except ValueError:
            out.append(path.as_posix())
    return tuple(sorted(out))


def _list_agent_names(agents_dir: Path) -> tuple[str, ...]:
    """File stems of every agent markdown under ``.claude/agents``."""
    if not agents_dir.is_dir():
        return ()
    return tuple(sorted(p.stem for p in agents_dir.glob(_AGENT_GLOB) if p.is_file()))


def _has_managed_block(claude_md: Path) -> bool:
    try:
        return BEGIN_MARKER in claude_md.read_text(encoding="utf-8")
    except OSError:
        return False


def _git_clean(project_root: Path) -> Optional[bool]:
    """True when the working tree has no uncommitted changes.

    Returns None when git isn't available or the command fails — the caller
    treats an unknown state as "can't promise reversibility".
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() == ""
