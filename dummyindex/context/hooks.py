"""SessionStart drift hook.

Installs a single Claude Code SessionStart hook so every fresh session
in a repo with `.context/` starts with a drift report appended to the
system prompt. The drift report is plain markdown printed to stdout by
``dummyindex context plan-update``; Claude Code's SessionStart hook
contract reads stdout as `additionalContext`.

History note: pre-0.13.5, this module also installed a ``git
post-commit`` hook and a Claude ``PostToolUse`` hook, both of which
ran ``dummyindex context rebuild --changed`` automatically. That
mechanism re-ran deterministic feature scaffolding on every edit and
overwrote council-enriched feature folders with raw `community-N`
placeholders. The fix flipped the model: hooks no longer rebuild the
backbone at all — instead, the SessionStart hook surfaces drift and
the running Claude session updates `.context/` itself, in-session,
where it has the full picture of *what* changed and *why*. `install`
actively scrubs the legacy post-commit + PostToolUse entries on
upgrade so a single ``dummyindex context hooks install`` removes the
broken behaviour and replaces it with the new drift hook.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Marker so install/uninstall/status can identify our hook entries among the
# user's other hooks. Embedded in every command we write.
_SENTINEL = "DUMMYINDEX_AUTO_REFRESH"

# Claude Code SessionStart body: emit drift to stdout, which Claude Code
# appends to the session's additionalContext. Background-detach is not
# used: the hook needs to finish before the session prompt is composed.
_SESSION_START_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {_SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context plan-update --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        }
    ],
}

# Claude Code events we currently install into. Anything in
# ``_LEGACY_CLAUDE_EVENTS`` is scrubbed on install for backwards-compat.
_CURRENT_CLAUDE_EVENTS: tuple[str, ...] = ("SessionStart",)
_LEGACY_CLAUDE_EVENTS: tuple[str, ...] = ("PostToolUse",)


@dataclass(frozen=True)
class HookStatus:
    claude_session_start: bool

    @property
    def all_installed(self) -> bool:
        return self.claude_session_start


@dataclass(frozen=True)
class HookResult:
    """Outcome of an install / uninstall call."""

    installed: tuple[str, ...]
    skipped: tuple[str, ...]   # already present (install) or absent (uninstall)
    removed: tuple[str, ...]   # uninstall only, or legacy-scrub on install
    errors: tuple[tuple[str, str], ...]  # (hook_name, error_message)


# ----- install --------------------------------------------------------------


def install(project_root: Path) -> HookResult:
    """Install the SessionStart drift hook at ``project_root``. Idempotent.

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
    git_post_commit = project_root / ".git" / "hooks" / "post-commit"
    if git_post_commit.exists():
        try:
            if _SENTINEL in git_post_commit.read_text(encoding="utf-8"):
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

    # Install the current SessionStart drift hook.
    try:
        inserted = _install_claude_hook(
            settings_path, "SessionStart", _SESSION_START_HOOK
        )
        (installed if inserted else skipped).append("claude/SessionStart")
    except OSError as exc:
        errors.append(("claude/SessionStart", str(exc)))

    return HookResult(
        installed=tuple(installed),
        skipped=tuple(skipped),
        removed=tuple(removed),
        errors=tuple(errors),
    )


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

    # Check for an existing entry of ours (by sentinel) and refresh it
    # in place so the body stays current after upgrades.
    for entry in events:
        for h in entry.get("hooks", []):
            if _SENTINEL in (h.get("command") or ""):
                idx = events.index(entry)
                if events[idx] == hook_body:
                    return False
                events[idx] = hook_body
                _write_json(settings_path, settings)
                return False

    events.append(hook_body)
    _write_json(settings_path, settings)
    return True


def _scrub_legacy_claude_hooks(settings_path: Path) -> list[str]:
    """Drop any of our (sentinel-bearing) entries under legacy event keys.

    Returns the event names that had at least one entry removed. Leaves
    user-authored entries intact.
    """
    if not settings_path.exists():
        return []
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
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
            if not any(_SENTINEL in (h.get("command") or "") for h in e.get("hooks", []))
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
        _write_json(settings_path, settings)
    return removed_events


# ----- uninstall ------------------------------------------------------------


def uninstall(project_root: Path) -> HookResult:
    """Remove every hook we've ever installed (current + legacy events)."""
    project_root = project_root.resolve()
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    # Git post-commit (legacy)
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

    # Claude Code hooks: scrub our entries under both current and legacy events.
    settings_path = project_root / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
        hooks_block = settings.get("hooks", {}) or {}
        changed = False
        for event in (*_CURRENT_CLAUDE_EVENTS, *_LEGACY_CLAUDE_EVENTS):
            events = hooks_block.get(event, []) or []
            new_events = [
                e for e in events
                if not any(_SENTINEL in (h.get("command") or "") for h in e.get("hooks", []))
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
                _write_json(settings_path, settings)
            except OSError as exc:
                errors.append(("claude/settings.json", str(exc)))
    else:
        for event in _CURRENT_CLAUDE_EVENTS:
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
        _SENTINEL in (h.get("command") or "")
        for entry in events
        for h in entry.get("hooks", [])
    )


# ----- internals ------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
