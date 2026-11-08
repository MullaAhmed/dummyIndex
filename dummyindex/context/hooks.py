"""Managed Claude Code hooks for `.context/` repos. Invariant: never rebuild the backbone.

Installs five Claude Code hook events so every session in a repo with `.context/`
benefits from automated context management:

1. **UserPromptSubmit** — injects a compact project behavior contract plus
   bounded correction feedback beside every prompt. This keeps the always-on
   ADHD output shape and automatic skill routing live in long sessions and
   works across alternate Claude profiles without relying on per-profile
   plugin materialisation.
2. **SessionStart** — refreshes local skill feedback, then emits a drift report
   and the last session-memory block as ``additionalContext`` before the
   session's first turn.
3. **Stop** — nudges the user to checkpoint a handoff when the session is
   substantial (long output or subagents ran) and no handoff was saved yet.
4. **PreCompact** — writes a deterministic breadcrumb entry to ``now.md``
   before context is discarded by compaction, so the session is never blank.
5. **PreToolUse** (matcher ``Write|Edit|MultiEdit``) — classifies a ``Write`` target and
   denies (with guidance) one that would create an internal planning doc in an
   unmanaged location, so the leak can't recur. Unlike the retired PostToolUse
   hook below, it mutates **nothing** (pure read→classify→deny), so it upholds
   the "hooks never rebuild the backbone" invariant.

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
replaces it with the current managed hook set.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from dummyindex.pipeline.io import resolve_git_dir

from .claude_settings import (
    MalformedSettingsError,
    install_hook_entry,
    load_settings,
    write_settings,
)
from .output.bootstrap import ALWAYS_ON_TURN_REMINDER

# Identifies our entries among the user's hooks (``SENTINEL in command``). The
# "AUTO_REFRESH" name is legacy, kept so upgrades still recognize and scrub
# entries older versions wrote; the hooks no longer auto-refresh.
SENTINEL = "DUMMYINDEX_AUTO_REFRESH"

# Header in every managed command: the legacy SENTINEL (for matching/scrubbing)
# plus an accurate description for anyone auditing settings.json.
_MANAGED_COMMENT = (
    f"# {SENTINEL}  DUMMYINDEX_HOOKS (managed by dummyindex; injects project "
    "contracts / reports drift / gates reconcile / nudges memory)\n"
)

# MalformedSettingsError is re-exported for callers that import it from here.
__all__ = [
    "MalformedSettingsError",
    "SENTINEL",
    "HookResult",
    "HookStatus",
    "install",
    "install_statusline",
    "status",
    "uninstall",
]

# SessionStart stdout lands in additionalContext; no background-detach, since it
# must finish before the prompt is composed. This self-gate reports a missing CLI
# once per session instead of silently disabling drift reporting. Only
# SessionStart stdout is free text, so the notice is safe only here.
_SESSION_START_GATE = (
    "command -v dummyindex >/dev/null 2>&1 || "
    "{ echo 'dummyindex CLI not found on PATH — drift reporting disabled'; "
    "exit 0; }\n"
)
# Fully silent self-gate for hooks whose stdout carries protocol meaning (e.g. the
# Stop gate's `decision: block` JSON), where a stray echo would be misread.
_SILENT_GATE = "command -v dummyindex >/dev/null 2>&1 || exit 0\n"

# UserPromptSubmit JSON stdout: ``additionalContext`` becomes a system reminder
# beside the prompt, not a visible hook message. The whole JSON is shell-quoted
# once; no project path, prompt text or other untrusted input is interpolated.
_USER_PROMPT_SUBMIT_PAYLOAD = json.dumps(
    {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ALWAYS_ON_TURN_REMINDER,
        },
        "suppressOutput": True,
    },
    separators=(",", ":"),
)
_USER_PROMPT_SUBMIT_HOOK = {
    # UserPromptSubmit has no matcher support and fires on every prompt.
    "hooks": [
        {
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + "printf '%s\\n' "
                + shlex.quote(_USER_PROMPT_SUBMIT_PAYLOAD)
                + "\nexit 0\n"
            ),
        },
        {
            # Independently valid and fail-open. stdout is deliberately not
            # redirected because it carries the UserPromptSubmit JSON.
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SILENT_GATE
                + "dummyindex context memory prompt-context --root "
                '"$CLAUDE_PROJECT_DIR" 2>/dev/null || true\n'
                "exit 0\n"
            ),
        },
    ],
}

_SESSION_START_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SESSION_START_GATE
                + 'dummyindex context plan-update --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
        {
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SESSION_START_GATE
                + "dummyindex context memory session-start --root "
                '"$CLAUDE_PROJECT_DIR" 2>/dev/null || true\n'
                "exit 0\n"
            ),
        },
        {
            # GC commit-throttle signal: silent unless ≥ N commits landed since the
            # last hygiene-sweep anchor, then a one-line "run /dummyindex-gc" nudge.
            # Always exits 0, so it is safe on every SessionStart.
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SESSION_START_GATE
                + 'dummyindex context gc signal --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
        {
            # Historical mining is SessionStart-only and fully silent. It
            # writes only the bounded, gitignored feedback cache.
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SILENT_GATE
                + 'dummyindex context memory mine --root "$CLAUDE_PROJECT_DIR" '
                ">/dev/null 2>&1 || true\n"
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
                _MANAGED_COMMENT
                + _SILENT_GATE
                + 'dummyindex context memory nudge --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
        {
            # Reconcile gate: block session exit once when `.context/` is
            # stale after a substantial session. stderr is muted, but stdout
            # is NOT — the gate's `decision: block` JSON must reach Claude Code.
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SILENT_GATE
                + 'dummyindex context reconcile-gate --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
    ],
}

_PRE_COMPACT_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SILENT_GATE
                + "dummyindex context memory breadcrumb --root "
                '"$CLAUDE_PROJECT_DIR" >/dev/null 2>&1 || true\n'
                "exit 0\n"
            ),
        }
    ],
}

_PRE_TOOL_USE_HOOK = {
    # Write|Edit|MultiEdit: Write also gets the stray-doc check; all three get
    # the citation guard. Re-install rewrites an older ``Write`` matcher.
    "matcher": "Write|Edit|MultiEdit",
    "hooks": [
        {
            # Doc-write guard: deny a ``Write`` that would create an internal
            # planning doc in an unmanaged location. Built on ``_SILENT_GATE`` so a
            # global install inserts its defer-check guard after it. stderr is muted,
            # stdout is NOT: the `permissionDecision: deny` JSON must reach Claude.
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SILENT_GATE
                + 'dummyindex context guard-doc-write --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        }
    ],
}

# (event_name, hook_body) installed under our sentinel, in install order.
_CLAUDE_HOOKS: tuple[tuple[str, dict], ...] = (
    ("UserPromptSubmit", _USER_PROMPT_SUBMIT_HOOK),
    ("SessionStart", _SESSION_START_HOOK),
    ("Stop", _STOP_HOOK),
    ("PreCompact", _PRE_COMPACT_HOOK),
    ("PreToolUse", _PRE_TOOL_USE_HOOK),
)

# Claude Code events we currently install into. Anything in
# ``_LEGACY_CLAUDE_EVENTS`` is scrubbed on install for backwards-compat.
CURRENT_CLAUDE_EVENTS: tuple[str, ...] = tuple(name for name, _ in _CLAUDE_HOOKS)
_LEGACY_CLAUDE_EVENTS: tuple[str, ...] = ("PostToolUse",)

# Guard prefixed onto every GLOBAL hook command so a repo with its own
# (``--local``) dummyindex hooks — the per-repo override — suppresses the
# global ones. ``defer-check`` exits 0 (success) when the project has a local
# install, so ``&& exit 0`` short-circuits before the real command runs.
_GLOBAL_GUARD = (
    'dummyindex context hooks defer-check --root "$CLAUDE_PROJECT_DIR" '
    "2>/dev/null && exit 0\n"
)
# Self-gate lines a command can open with (silent, or SessionStart's notice). The
# guard goes right after the gate so a missing ``dummyindex`` short-circuits first.
_GATE_VARIANTS: tuple[str, ...] = (_SILENT_GATE, _SESSION_START_GATE)


def _settings_path_for(project_root: Path, scope: str) -> Path:
    """Resolve the settings.json a given scope writes to."""
    if scope == "global":
        return Path.home() / ".claude" / "settings.json"
    return project_root / ".claude" / "settings.json"


# Install wires the freshness badge (not opt-in) when no ``statusLine`` exists in
# either scope. ``statusLine`` is an unsentinelled scalar, so the write is
# write-if-absent only: any existing value (ours or the user's) stays
# byte-identical (idempotent). A removed badge returns on the next install.
_STATUSLINE_COMMAND = "dummyindex context statusline"
_STATUSLINE_VALUE: dict[str, str] = {
    "type": "command",
    "command": _STATUSLINE_COMMAND,
}

# Advisory when the badge can't be wired because settings.json can't be read or
# parsed (writing would clobber it): the snippet to add by hand.
_STATUSLINE_UNWRITABLE_NUDGE = (
    "tip: could not wire the `.context/` freshness badge (unreadable "
    ".claude/settings.json) — add "
    '`"statusLine": {"type": "command", "command": "dummyindex context '
    'statusline"}` by hand.'
)


def _status_line_configured(settings_path: Path) -> bool:
    """True when ``settings_path`` parses and defines a truthy ``statusLine``.

    Read-only and never raises: an absent, unreadable or malformed file counts as
    "no statusLine here", as does a present but falsy (``null``/empty) value.
    """
    try:
        settings = load_settings(settings_path)
    except (MalformedSettingsError, OSError):
        return False
    return bool(settings.get("statusLine"))


def install_statusline(project_root: Path, *, scope: str = "local") -> str | None:
    """Wire the freshness badge when no ``statusLine`` exists in either scope.

    Write-if-absent, never clobber: returns ``None`` when the local or global
    settings already define a truthy ``statusLine`` (idempotent without a
    sentinel). Otherwise writes :data:`_STATUSLINE_VALUE` into ``scope``'s settings
    and returns the wired command. An unparseable file is never overwritten; it, or
    a failed write, returns :data:`_STATUSLINE_UNWRITABLE_NUDGE` instead.
    """
    for other in ("local", "global"):
        if _status_line_configured(_settings_path_for(project_root, other)):
            return None
    settings_path = _settings_path_for(project_root, scope)
    try:
        settings = load_settings(settings_path)
    except (MalformedSettingsError, OSError):
        return _STATUSLINE_UNWRITABLE_NUDGE
    settings["statusLine"] = dict(_STATUSLINE_VALUE)
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        write_settings(settings_path, settings)
    except OSError:
        return _STATUSLINE_UNWRITABLE_NUDGE
    return _STATUSLINE_COMMAND


def _guard_body(body: dict) -> dict:
    """Copy a hook body with the defer-check guard inserted after each command's
    ``command -v dummyindex`` self-gate (silent or SessionStart variant).

    The UserPromptSubmit policy hook has no self-gate on purpose: its static
    reminder must work for a Claude profile with no ``dummyindex`` on PATH. Only
    for a global install, the silent gate + guard go right after the managed
    comment so a repo-local install can still override it.
    """
    out = {**body, "hooks": []}
    for h in body["hooks"]:
        cmd = h["command"]
        guarded = False
        for gate in _GATE_VARIANTS:
            if gate in cmd:
                cmd = cmd.replace(gate, gate + _GLOBAL_GUARD, 1)
                guarded = True
                break
        if not guarded:
            if cmd.startswith(_MANAGED_COMMENT):
                cmd = cmd.replace(
                    _MANAGED_COMMENT,
                    _MANAGED_COMMENT + _SILENT_GATE + _GLOBAL_GUARD,
                    1,
                )
            else:  # defensive: every canonical body currently has the comment
                cmd = _SILENT_GATE + _GLOBAL_GUARD + cmd
        out["hooks"].append({**h, "command": cmd})
    return out


def _hooks_for_scope(scope: str) -> tuple[tuple[str, dict], ...]:
    """The (event, body) pairs to install for a scope — global bodies carry
    the defer-check guard; local bodies are used verbatim."""
    if scope == "global":
        return tuple((event, _guard_body(body)) for event, body in _CLAUDE_HOOKS)
    return _CLAUDE_HOOKS


def local_install_present(project_root: Path) -> bool:
    """True when the repo has at least one of our hooks in its own
    ``.claude/settings.json`` (the per-repo override)."""
    return any(
        _claude_hook_installed(project_root, event) for event in CURRENT_CLAUDE_EVENTS
    )


@dataclass(frozen=True)
class HookStatus:
    claude_session_start: bool
    claude_stop: bool = False
    claude_pre_compact: bool = False
    claude_pre_tool_use: bool = False
    claude_user_prompt_submit: bool = False

    @property
    def all_installed(self) -> bool:
        return (
            self.claude_session_start
            and self.claude_stop
            and self.claude_pre_compact
            and self.claude_pre_tool_use
            and self.claude_user_prompt_submit
        )


@dataclass(frozen=True)
class HookResult:
    """Outcome of an install / uninstall call.

    ``refreshed`` (install only) lists managed hooks rewritten in place, distinct
    from ``skipped`` (already identical), so an upgrade that changes
    ``settings.json`` isn't reported as 'already current'.
    """

    installed: tuple[str, ...]
    skipped: tuple[str, ...]  # already present (install) or absent (uninstall)
    removed: tuple[str, ...]  # uninstall only, or legacy-scrub on install
    errors: tuple[tuple[str, str], ...]  # (hook_name, error_message)
    refreshed: tuple[str, ...] = ()  # install only: body rewritten in place
    nudges: tuple[str, ...] = ()  # install only: advisories shown to the user,
    # never written to settings (e.g. statusLine blocked by unparseable settings).


def _legacy_post_commit_path(project_root: Path) -> Path | None:
    """Where the retired ``git post-commit`` hook would live for this repo.

    Resolves the real git dir so submodules (``.git`` file → superproject's
    ``.git/modules/<name>``) and worktrees (hooks in the common dir) are scrubbed
    too. Returns ``None`` when ``project_root`` isn't a git repo.
    """
    git_dir = resolve_git_dir(project_root)
    if git_dir is None:
        return None
    return git_dir / "hooks" / "post-commit"


# --- install


def install(project_root: Path, *, scope: str = "local") -> HookResult:
    """Install the managed Claude hooks and the statusLine badge. Idempotent.

    Scrubs our legacy ``PostToolUse`` entries; user hooks (no sentinel) are left
    untouched. ``scope="local"`` writes ``<root>/.claude/settings.json`` and removes
    the legacy ``git post-commit`` hook. ``scope="global"`` writes
    ``~/.claude/settings.json`` with defer-check-guarded bodies (a repo's own
    ``--local`` install wins) and skips git: it owns no single repo's hooks.
    """
    project_root = project_root.resolve()
    installed: list[str] = []
    skipped: list[str] = []
    removed: list[str] = []
    refreshed: list[str] = []
    errors: list[tuple[str, str]] = []

    # Scrub the legacy git post-commit hook (it ran `rebuild --changed`).
    if scope == "local":
        git_post_commit = _legacy_post_commit_path(project_root)
        if git_post_commit is not None and git_post_commit.exists():
            try:
                if SENTINEL in git_post_commit.read_text(encoding="utf-8"):
                    git_post_commit.unlink()
                    removed.append("git/post-commit (legacy)")
            except OSError as exc:
                errors.append(("git/post-commit", str(exc)))

    settings_path = _settings_path_for(project_root, scope)

    # Scrub legacy Claude hook events (currently just PostToolUse).
    try:
        legacy_removed = _scrub_legacy_claude_hooks(settings_path)
        for ev in legacy_removed:
            removed.append(f"claude/{ev} (legacy)")
    except OSError as exc:
        errors.append(("claude/settings.json", str(exc)))

    for event, body in _hooks_for_scope(scope):
        try:
            # Classify by on-disk change: install_hook_entry returns False for both
            # "refreshed" and "identical" and keeps co-located user hooks, so
            # comparing against `body` would report "refreshed" forever once a user
            # adds a hook beside ours. Before/after bytes are the honest signal.
            before = settings_path.read_bytes() if settings_path.exists() else b""
            inserted = install_hook_entry(settings_path, event, body, sentinel=SENTINEL)
            after = settings_path.read_bytes() if settings_path.exists() else b""
            if inserted:
                installed.append(f"claude/{event}")
            elif before != after:
                refreshed.append(f"claude/{event}")
            else:
                skipped.append(f"claude/{event}")
        except (OSError, MalformedSettingsError) as exc:
            errors.append((f"claude/{event}", str(exc)))

    # Freshness badge: `install_statusline` owns the write-if-absent decision.
    nudges: tuple[str, ...] = ()
    wired = install_statusline(project_root, scope=scope)
    if wired == _STATUSLINE_UNWRITABLE_NUDGE:
        nudges = (wired,)
    elif wired is not None:
        installed.append("claude/statusLine")

    return HookResult(
        installed=tuple(installed),
        skipped=tuple(skipped),
        removed=tuple(removed),
        errors=tuple(errors),
        refreshed=tuple(refreshed),
        nudges=nudges,
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
            e
            for e in events
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


# --- uninstall


def uninstall(project_root: Path, *, scope: str = "local") -> HookResult:
    """Remove every hook we've ever installed (current + legacy events).

    ``scope="global"`` targets ``~/.claude/settings.json`` and skips the git
    post-commit scrub (a user-level install owns no repo's git hooks)."""
    project_root = project_root.resolve()
    removed: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    # Git post-commit (legacy) — local scope only.
    if scope == "local":
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
    settings_path = _settings_path_for(project_root, scope)
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
                    e
                    for e in events
                    if not any(
                        SENTINEL in (h.get("command") or "") for h in e.get("hooks", [])
                    )
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
        installed=(),
        skipped=tuple(skipped),
        removed=tuple(removed),
        errors=tuple(errors),
    )


# --- status


def status(project_root: Path, *, scope: str = "local") -> HookStatus:
    project_root = project_root.resolve()
    settings_path = _settings_path_for(project_root, scope)
    return HookStatus(
        claude_session_start=_claude_hook_installed(
            project_root, "SessionStart", settings_path=settings_path
        ),
        claude_stop=_claude_hook_installed(
            project_root, "Stop", settings_path=settings_path
        ),
        claude_pre_compact=_claude_hook_installed(
            project_root, "PreCompact", settings_path=settings_path
        ),
        claude_pre_tool_use=_claude_hook_installed(
            project_root, "PreToolUse", settings_path=settings_path
        ),
        claude_user_prompt_submit=_claude_hook_installed(
            project_root, "UserPromptSubmit", settings_path=settings_path
        ),
    )


def _claude_hook_installed(
    project_root: Path, event: str, *, settings_path: Path | None = None
) -> bool:
    if settings_path is None:
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
