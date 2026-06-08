"""Session hooks: SessionStart drift, Stop handoff nudge, PreCompact breadcrumb.

Installs three Claude Code hooks so every session in a repo with `.context/`
benefits from automated context management:

1. **SessionStart** — emits a drift report and the last session-memory block
   as ``additionalContext`` before the session's first turn.
2. **Stop** — nudges the user to checkpoint a handoff when the session is
   substantial (long output or subagents ran) and no handoff was saved yet.
3. **PreCompact** — writes a deterministic breadcrumb entry to ``now.md``
   before context is discarded by compaction, so the session is never blank.

History note: pre-0.13.5, this module also installed a ``git post-commit``
hook and a Claude ``PostToolUse`` hook, both of which ran
``dummyindex context rebuild --changed`` automatically. That mechanism
re-ran deterministic feature scaffolding on every edit and overwrote
council-enriched feature folders with raw ``community-N`` placeholders.
The fix flipped the model: hooks no longer rebuild the backbone at all —
instead, the SessionStart hook surfaces drift and the running Claude session
updates ``.context/`` itself, in-session, where it has the full picture of
*what* changed and *why*. ``install`` actively scrubs the legacy post-commit
+ PostToolUse entries on upgrade so a single
``dummyindex context hooks install`` removes the broken behaviour and
replaces it with the three new hooks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dummyindex.pipeline.io import resolve_git_dir

from .claude_settings import (
    MalformedSettingsError,
    install_hook_entry,
    load_settings,
    write_settings,
)

# Marker so install/uninstall/status can identify our hook entries among the
# user's other hooks. Embedded in every command we write.
SENTINEL = "DUMMYINDEX_AUTO_REFRESH"

# Re-exported for back-compat: callers historically imported the error type
# from this module. The implementation now lives in ``claude_settings``.
__all__ = [
    "MalformedSettingsError",
    "SENTINEL",
    "HookResult",
    "HookStatus",
    "install",
    "status",
    "uninstall",
]

# Claude Code SessionStart body: emit drift to stdout, which Claude Code
# appends to the session's additionalContext. Background-detach is not
# used: the hook needs to finish before the session prompt is composed.
_SESSION_START_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context plan-update --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context memory session-start --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
    ],
}

_STOP_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context memory nudge --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        }
    ],
}

_PRE_COMPACT_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context memory breadcrumb --root "$CLAUDE_PROJECT_DIR" '
                ">/dev/null 2>&1 || true\n"
                "exit 0\n"
            ),
        }
    ],
}

# (event_name, hook_body) installed under our sentinel, in install order.
_CLAUDE_HOOKS: tuple[tuple[str, dict], ...] = (
    ("SessionStart", _SESSION_START_HOOK),
    ("Stop", _STOP_HOOK),
    ("PreCompact", _PRE_COMPACT_HOOK),
)

# Claude Code events we currently install into. Anything in
# ``_LEGACY_CLAUDE_EVENTS`` is scrubbed on install for backwards-compat.
CURRENT_CLAUDE_EVENTS: tuple[str, ...] = tuple(name for name, _ in _CLAUDE_HOOKS)
_LEGACY_CLAUDE_EVENTS: tuple[str, ...] = ("PostToolUse",)


@dataclass(frozen=True)
class HookStatus:
    claude_session_start: bool
    claude_stop: bool = False
    claude_pre_compact: bool = False

    @property
    def all_installed(self) -> bool:
        return (
            self.claude_session_start
            and self.claude_stop
            and self.claude_pre_compact
        )


@dataclass(frozen=True)
class HookResult:
    """Outcome of an install / uninstall call."""

    installed: tuple[str, ...]
    skipped: tuple[str, ...]   # already present (install) or absent (uninstall)
    removed: tuple[str, ...]   # uninstall only, or legacy-scrub on install
    errors: tuple[tuple[str, str], ...]  # (hook_name, error_message)


def _legacy_post_commit_path(project_root: Path) -> Path | None:
    """Where the retired ``git post-commit`` hook would live for this repo.

    Resolves the real git dir so submodules (``.git`` is a file → real dir
    under the superproject's ``.git/modules/<name>``) and worktrees (hooks
    live in the common dir) are scrubbed too — not just plain checkouts.
    Returns ``None`` when ``project_root`` isn't a git repo.
    """
    git_dir = resolve_git_dir(project_root)
    if git_dir is None:
        return None
    return git_dir / "hooks" / "post-commit"


# ----- install --------------------------------------------------------------


def install(project_root: Path) -> HookResult:
    """Install the SessionStart drift, Stop nudge, and PreCompact breadcrumb
    hooks at ``project_root``. Idempotent.

    Also scrubs any legacy ``git post-commit`` script we previously
    installed and any ``PostToolUse`` entry carrying our sentinel, so
    users upgrading from <=0.13.4 land in the clean configuration with
    a single ``dummyindex context hooks install``. Hooks the user
    installed themselves (no sentinel) are left untouched.
    """
    project_root = project_root.resolve()
    installed: list[str] = []
    skipped: list[str] = []
    removed: list[str] = []
    errors: list[tuple[str, str]] = []

    # Scrub the legacy git post-commit hook so upgraders aren't left with
    # the broken `rebuild --changed` behaviour.
    git_post_commit = _legacy_post_commit_path(project_root)
    if git_post_commit is not None and git_post_commit.exists():
        try:
            if SENTINEL in git_post_commit.read_text(encoding="utf-8"):
                git_post_commit.unlink()
                removed.append("git/post-commit (legacy)")
        except OSError as exc:
            errors.append(("git/post-commit", str(exc)))

    settings_path = project_root / ".claude" / "settings.json"

    # Scrub legacy Claude hook events (currently just PostToolUse).
    try:
        legacy_removed = _scrub_legacy_claude_hooks(settings_path)
        for ev in legacy_removed:
            removed.append(f"claude/{ev} (legacy)")
    except OSError as exc:
        errors.append(("claude/settings.json", str(exc)))

    # Install the current Claude hooks (SessionStart drift + Stop nudge +
    # PreCompact breadcrumb), all under our sentinel.
    for event, body in _CLAUDE_HOOKS:
        try:
            inserted = install_hook_entry(
                settings_path, event, body, sentinel=SENTINEL
            )
            (installed if inserted else skipped).append(f"claude/{event}")
        except (OSError, MalformedSettingsError) as exc:
            errors.append((f"claude/{event}", str(exc)))

    return HookResult(
        installed=tuple(installed),
        skipped=tuple(skipped),
        removed=tuple(removed),
        errors=tuple(errors),
    )


def _scrub_legacy_claude_hooks(settings_path: Path) -> list[str]:
    """Drop any of our (sentinel-bearing) entries under legacy event keys.

    Returns the event names that had at least one entry removed. Leaves
    user-authored entries intact. Never writes over an unparseable file —
    the real error is surfaced by the install step that follows.
    """
    try:
        settings = load_settings(settings_path)
    except MalformedSettingsError:
        return []
    hooks_block = settings.get("hooks") or {}
    removed_events: list[str] = []
    changed = False
    for event in _LEGACY_CLAUDE_EVENTS:
        events = hooks_block.get(event)
        if not isinstance(events, list):
            continue
        new_events = [
            e for e in events
            if not any(SENTINEL in (h.get("command") or "") for h in e.get("hooks", []))
        ]
        if len(new_events) == len(events):
            continue
        removed_events.append(event)
        changed = True
        if new_events:
            hooks_block[event] = new_events
        else:
            hooks_block.pop(event, None)
    if changed:
        if not hooks_block:
            settings.pop("hooks", None)
        else:
            settings["hooks"] = hooks_block
        write_settings(settings_path, settings)
    return removed_events


# ----- uninstall ------------------------------------------------------------


def uninstall(project_root: Path) -> HookResult:
    """Remove every hook we've ever installed (current + legacy events)."""
    project_root = project_root.resolve()
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    # Git post-commit (legacy)
    target = _legacy_post_commit_path(project_root)
    if target is not None and target.exists():
        try:
            if SENTINEL in target.read_text(encoding="utf-8"):
                target.unlink()
                removed.append("git/post-commit")
            else:
                skipped.append("git/post-commit (not managed by dummyindex)")
        except OSError as exc:
            errors.append(("git/post-commit", str(exc)))
    else:
        skipped.append("git/post-commit (absent)")

    # Claude Code hooks: scrub our entries under both current and legacy events.
    settings_path = project_root / ".claude" / "settings.json"
    if settings_path.exists():
        # Preserve-or-refuse: never overwrite a file we can't parse.
        try:
            settings = load_settings(settings_path)
        except MalformedSettingsError as exc:
            errors.append(("claude/settings.json", str(exc)))
            settings = None
        if settings is not None:
            hooks_block = settings.get("hooks", {}) or {}
            changed = False
            for event in (*CURRENT_CLAUDE_EVENTS, *_LEGACY_CLAUDE_EVENTS):
                events = hooks_block.get(event, []) or []
                new_events = [
                    e for e in events
                    if not any(SENTINEL in (h.get("command") or "") for h in e.get("hooks", []))
                ]
                if len(new_events) != len(events):
                    removed.append(f"claude/{event}")
                    changed = True
                else:
                    skipped.append(f"claude/{event} (absent)")
                if not new_events:
                    hooks_block.pop(event, None)
                else:
                    hooks_block[event] = new_events
            if changed:
                if not hooks_block:
                    settings.pop("hooks", None)
                try:
                    write_settings(settings_path, settings)
                except OSError as exc:
                    errors.append(("claude/settings.json", str(exc)))
    else:
        for event in CURRENT_CLAUDE_EVENTS:
            skipped.append(f"claude/{event} (absent)")

    return HookResult(
        installed=(), skipped=tuple(skipped), removed=tuple(removed),
        errors=tuple(errors),
    )


# ----- status ---------------------------------------------------------------


def status(project_root: Path) -> HookStatus:
    project_root = project_root.resolve()
    return HookStatus(
        claude_session_start=_claude_hook_installed(project_root, "SessionStart"),
        claude_stop=_claude_hook_installed(project_root, "Stop"),
        claude_pre_compact=_claude_hook_installed(project_root, "PreCompact"),
    )


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
        SENTINEL in (h.get("command") or "")
        for entry in events
        for h in entry.get("hooks", [])
    )
