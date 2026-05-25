"""Always-on auto-refresh hooks.

Installs three event-driven triggers so the `.context/` index never lags
the code:

1. **git post-commit** — runs ``dummyindex context rebuild --changed`` after
   every commit. Lives at ``.git/hooks/post-commit`` as a shell script.
2. **Claude Code PostToolUse** — runs ``dummyindex context rebuild --changed``
   after Edit / Write / MultiEdit / Bash(mv|rm|cp). Lives in
   ``.claude/settings.json`` under ``hooks.PostToolUse``.
3. **Claude Code SessionStart** — runs ``dummyindex context check --auto-refresh
   --quiet`` so every session starts with a current index. Lives in
   ``.claude/settings.json`` under ``hooks.SessionStart``.

All three are idempotent — re-running ``install`` doesn't duplicate. The
sentinel marker ``DUMMYINDEX_AUTO_REFRESH`` identifies our entries among
others the user may have configured.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Marker so install/uninstall/status can identify our hook entries among the
# user's other hooks. Embedded in every command we write.
_SENTINEL = "DUMMYINDEX_AUTO_REFRESH"

_GIT_HOOK_TEMPLATE = """#!/usr/bin/env bash
# {sentinel}
# Installed by `dummyindex context hooks install`.
# Refreshes the .context/ index after every commit. Safe to remove; the
# `dummyindex context check` SessionStart hook will catch drift on the
# next Claude session.
set -e
if ! command -v dummyindex >/dev/null 2>&1; then
  exit 0
fi
dummyindex context rebuild --changed --root "$(git rev-parse --show-toplevel)" >/dev/null 2>&1 &
exit 0
"""

# Claude Code settings.json hook bodies — both shell out to dummyindex.
_POST_TOOL_USE_HOOK = {
    "matcher": "Edit|Write|MultiEdit",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {_SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context rebuild --changed --root "$CLAUDE_PROJECT_DIR" '
                ">/dev/null 2>&1 &\n"
                "exit 0\n"
            ),
        }
    ],
}

_SESSION_START_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {_SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context check --auto-refresh --quiet '
                '--root "$CLAUDE_PROJECT_DIR" >/dev/null 2>&1 || true\n'
                "exit 0\n"
            ),
        }
    ],
}


@dataclass(frozen=True)
class HookStatus:
    git_post_commit: bool
    claude_post_tool_use: bool
    claude_session_start: bool

    @property
    def all_installed(self) -> bool:
        return all(
            (self.git_post_commit, self.claude_post_tool_use, self.claude_session_start)
        )


@dataclass(frozen=True)
class HookResult:
    """Outcome of an install / uninstall call."""

    installed: tuple[str, ...]
    skipped: tuple[str, ...]   # already present (install) or absent (uninstall)
    removed: tuple[str, ...]   # uninstall only
    errors: tuple[tuple[str, str], ...]  # (hook_name, error_message)


# ----- install --------------------------------------------------------------


def install(project_root: Path) -> HookResult:
    """Install all three hooks at ``project_root``. Idempotent."""
    project_root = project_root.resolve()
    installed: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    # 1. Git post-commit
    git_hooks_dir = project_root / ".git" / "hooks"
    if git_hooks_dir.parent.is_dir():
        try:
            inserted = _install_git_post_commit(git_hooks_dir)
            (installed if inserted else skipped).append("git/post-commit")
        except OSError as exc:
            errors.append(("git/post-commit", str(exc)))
    else:
        skipped.append("git/post-commit")  # not a git repo

    # 2. Claude Code PostToolUse + SessionStart
    settings_path = project_root / ".claude" / "settings.json"
    try:
        inserted = _install_claude_hook(settings_path, "PostToolUse", _POST_TOOL_USE_HOOK)
        (installed if inserted else skipped).append("claude/PostToolUse")
    except OSError as exc:
        errors.append(("claude/PostToolUse", str(exc)))

    try:
        inserted = _install_claude_hook(settings_path, "SessionStart", _SESSION_START_HOOK)
        (installed if inserted else skipped).append("claude/SessionStart")
    except OSError as exc:
        errors.append(("claude/SessionStart", str(exc)))

    return HookResult(
        installed=tuple(installed),
        skipped=tuple(skipped),
        removed=(),
        errors=tuple(errors),
    )


def _install_git_post_commit(hooks_dir: Path) -> bool:
    """Write .git/hooks/post-commit if missing or owned by us. Returns True if
    a new hook was written, False if our hook was already there."""
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "post-commit"
    body = _GIT_HOOK_TEMPLATE.format(sentinel=_SENTINEL)
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _SENTINEL in existing:
            # Already installed — refresh body in case the template changed.
            if existing != body:
                target.write_text(body, encoding="utf-8")
            _chmod_executable(target)
            return False
        # User has their own post-commit hook. Be conservative — refuse to
        # overwrite. They can run uninstall or manually chain ours in.
        raise OSError(
            f"{target} exists but is not managed by dummyindex; "
            "remove or chain it manually before installing."
        )
    target.write_text(body, encoding="utf-8")
    _chmod_executable(target)
    return True


def _install_claude_hook(
    settings_path: Path, event: str, hook_body: dict[str, Any]
) -> bool:
    """Add our entry under settings['hooks'][event] if not already present.

    Returns True if added, False if already present (idempotent).
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    hooks_block = settings.setdefault("hooks", {})
    events = hooks_block.setdefault(event, [])

    # Check for an existing entry of ours (by sentinel)
    for entry in events:
        for h in entry.get("hooks", []):
            if _SENTINEL in (h.get("command") or ""):
                # Already installed. Refresh in case the body changed.
                # Replace the entry in place to keep ordering.
                idx = events.index(entry)
                events[idx] = hook_body
                _write_json(settings_path, settings)
                return False

    events.append(hook_body)
    _write_json(settings_path, settings)
    return True


# ----- uninstall ------------------------------------------------------------


def uninstall(project_root: Path) -> HookResult:
    project_root = project_root.resolve()
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    # Git post-commit
    target = project_root / ".git" / "hooks" / "post-commit"
    if target.exists():
        try:
            if _SENTINEL in target.read_text(encoding="utf-8"):
                target.unlink()
                removed.append("git/post-commit")
            else:
                skipped.append("git/post-commit (not managed by dummyindex)")
        except OSError as exc:
            errors.append(("git/post-commit", str(exc)))
    else:
        skipped.append("git/post-commit (absent)")

    # Claude Code hooks
    settings_path = project_root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
        hooks_block = settings.get("hooks", {}) or {}
        changed = False
        for event in ("PostToolUse", "SessionStart"):
            events = hooks_block.get(event, []) or []
            new_events = [
                e for e in events
                if not any(_SENTINEL in (h.get("command") or "") for h in e.get("hooks", []))
            ]
            if len(new_events) != len(events):
                hooks_block[event] = new_events
                removed.append(f"claude/{event}")
                changed = True
            else:
                skipped.append(f"claude/{event} (absent)")
            # Clean up empty event keys.
            if not new_events:
                hooks_block.pop(event, None)
        if changed:
            if not hooks_block:
                settings.pop("hooks", None)
            try:
                _write_json(settings_path, settings)
            except OSError as exc:
                errors.append(("claude/settings.json", str(exc)))
    else:
        skipped.append("claude/PostToolUse (absent)")
        skipped.append("claude/SessionStart (absent)")

    return HookResult(
        installed=(), skipped=tuple(skipped), removed=tuple(removed),
        errors=tuple(errors),
    )


# ----- status ---------------------------------------------------------------


def status(project_root: Path) -> HookStatus:
    project_root = project_root.resolve()
    return HookStatus(
        git_post_commit=_git_post_commit_installed(project_root),
        claude_post_tool_use=_claude_hook_installed(project_root, "PostToolUse"),
        claude_session_start=_claude_hook_installed(project_root, "SessionStart"),
    )


def _git_post_commit_installed(project_root: Path) -> bool:
    target = project_root / ".git" / "hooks" / "post-commit"
    if not target.exists():
        return False
    try:
        return _SENTINEL in target.read_text(encoding="utf-8")
    except OSError:
        return False


def _claude_hook_installed(project_root: Path, event: str) -> bool:
    settings_path = project_root / ".claude" / "settings.json"
    if not settings_path.exists():
        return False
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    events = (settings.get("hooks") or {}).get(event, []) or []
    return any(
        _SENTINEL in (h.get("command") or "")
        for entry in events
        for h in entry.get("hooks", [])
    )


# ----- internals ------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _chmod_executable(path: Path) -> None:
    """chmod +x on POSIX; no-op on Windows."""
    if os.name != "posix":
        return
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
