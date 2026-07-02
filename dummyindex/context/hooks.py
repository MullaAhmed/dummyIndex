"""Session hooks: SessionStart drift, Stop handoff nudge, PreCompact breadcrumb,
PreToolUse doc-write guard.

Installs four Claude Code hooks so every session in a repo with `.context/`
benefits from automated context management:

1. **SessionStart** — emits a drift report and the last session-memory block
   as ``additionalContext`` before the session's first turn.
2. **Stop** — nudges the user to checkpoint a handoff when the session is
   substantial (long output or subagents ran) and no handoff was saved yet.
3. **PreCompact** — writes a deterministic breadcrumb entry to ``now.md``
   before context is discarded by compaction, so the session is never blank.
4. **PreToolUse** (matcher ``Write``) — classifies a ``Write`` target and
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
# user's other hooks. Embedded in every command we write. The "AUTO_REFRESH"
# name is legacy — kept stable so upgrades still recognize (and scrub) entries
# written by older versions (recognition is ``SENTINEL in command``, so adding
# clearer text alongside it is safe); the managed hooks no longer auto-refresh,
# they report drift (SessionStart), gate the reconcile (Stop), and checkpoint
# session state (Stop/PreCompact).
SENTINEL = "DUMMYINDEX_AUTO_REFRESH"

# The header comment we now write into every managed command: the legacy
# SENTINEL substring (for matcher/scrub compatibility) plus a clear, accurate
# description of what these hooks actually do. Anyone auditing settings.json
# sees the truth, while ``SENTINEL in command`` recognition still holds.
_MANAGED_COMMENT = (
    f"# {SENTINEL}  DUMMYINDEX_HOOKS (managed by dummyindex; reports drift / "
    "gates reconcile / nudges memory)\n"
)

# Re-exported for back-compat: callers historically imported the error type
# from this module. The implementation now lives in ``claude_settings``.
__all__ = [
    "MalformedSettingsError",
    "SENTINEL",
    "HookResult",
    "HookStatus",
    "install",
    "status",
    "statusline_nudge",
    "uninstall",
]

# Claude Code SessionStart body: emit drift to stdout, which Claude Code
# appends to the session's additionalContext. Background-detach is not
# used: the hook needs to finish before the session prompt is composed.
# SessionStart self-gate: a broken/PATH-missing CLI surfaces ONCE per session
# on stdout (Claude Code folds it into additionalContext) instead of silently
# disabling drift reporting forever. SessionStart stdout is free text, so the
# notice is safe here only.
_SESSION_START_GATE = (
    "command -v dummyindex >/dev/null 2>&1 || "
    "{ echo 'dummyindex CLI not found on PATH — drift reporting disabled'; "
    "exit 0; }\n"
)
# Stop / PreCompact self-gate stays fully silent: their stdout carries protocol
# meaning (the Stop gate's `decision: block` JSON), so a stray echo would be
# misread.
_SILENT_GATE = "command -v dummyindex >/dev/null 2>&1 || exit 0\n"

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
            # GC commit-throttle signal: silent unless ≥ N commits have landed
            # since the last hygiene-sweep anchor, in which case it emits a
            # one-line "run /dummyindex-gc" nudge. Always exits 0, so it is safe
            # to run unconditionally on every SessionStart alongside the drift
            # report and the session-memory block.
            "type": "command",
            "command": (
                _MANAGED_COMMENT
                + _SESSION_START_GATE
                + 'dummyindex context gc signal --root "$CLAUDE_PROJECT_DIR" '
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
    # Matcher is ``Write`` only: Edit/MultiEdit require the target to pre-exist,
    # so they can only maintain an existing doc, never create a fresh leak.
    "matcher": "Write",
    "hooks": [
        {
            # Doc-write guard: classify the ``Write`` target and emit a deny
            # decision when it would create an internal planning doc in an
            # unmanaged location. Built from ``_SILENT_GATE`` (like the Stop
            # reconcile-gate) so a GLOBAL install gets the defer-check guard
            # inserted after the gate line. stderr is muted, but stdout is NOT —
            # the guard's `permissionDecision: deny` JSON must reach Claude Code.
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
# The self-gate line each hook command opens with; the guard is inserted right
# after it so a missing ``dummyindex`` still short-circuits first. There are two
# gate variants — the silent one (Stop/PreCompact) and the SessionStart one that
# echoes a degraded-mode notice — so the guard insertion tries both.
_GATE_VARIANTS: tuple[str, ...] = (_SILENT_GATE, _SESSION_START_GATE)


def _settings_path_for(project_root: Path, scope: str) -> Path:
    """Resolve the settings.json a given scope writes to."""
    if scope == "global":
        return Path.home() / ".claude" / "settings.json"
    return project_root / ".claude" / "settings.json"


# The one-line advisory surfaced (emit-only) when no ``statusLine`` is wired in
# either the local or global ``settings.json``. It carries the snippet to add:
# point the user at the shipped statusline command so they can opt in. We
# deliberately never *write* this — a ``statusLine`` is a scalar with no
# sentinel, so there's no way to make a write idempotent / un-clobber a user's
# own value later. Emit-only means we never even attempt the write (spec §5).
_STATUSLINE_NUDGE = (
    "tip: add a `.context/` freshness badge to your prompt — set "
    '`"statusLine": {"type": "command", "command": "dummyindex context '
    'statusline"}` in .claude/settings.json (dummyindex never writes this for you).'
)


def _status_line_configured(settings_path: Path) -> bool:
    """True when ``settings_path`` parses and defines a truthy ``statusLine``.

    Emit-only / read-only: never writes. An absent file, an unreadable file
    (``OSError``), or a malformed one (:class:`MalformedSettingsError`, raised by
    :func:`load_settings`) is treated as "no statusLine here" — the same
    swallow-and-degrade discipline the other hook paths use, so a broken
    settings.json never raises out of the nudge. A ``statusLine`` key present
    but falsy (``null``/empty) counts as unconfigured.
    """
    try:
        settings = load_settings(settings_path)
    except (MalformedSettingsError, OSError):
        return False
    return bool(settings.get("statusLine"))


def statusline_nudge(project_root: Path) -> str | None:
    """Emit-only nudge: advise wiring a ``statusLine`` when none is configured.

    Pure decision helper — reads ``statusLine`` from **both** the local
    (``<root>/.claude/settings.json``) and global (``~/.claude/settings.json``)
    settings and **writes nothing** to either. Returns ``None`` when *either*
    scope already defines a ``statusLine`` (already configured → stay silent);
    otherwise returns the one-line :data:`_STATUSLINE_NUDGE` carrying the
    snippet to add. Both ``MalformedSettingsError`` and ``OSError`` are
    swallowed (an unreadable settings file is treated as absent), so this never
    raises. This is the sole place the nudge decision lives; callers only
    surface its return value.
    """
    for scope in ("local", "global"):
        if _status_line_configured(_settings_path_for(project_root, scope)):
            return None
    return _STATUSLINE_NUDGE


def _guard_body(body: dict) -> dict:
    """Return a copy of a hook body with the defer-check guard inserted into
    each command, right after whichever ``command -v dummyindex`` self-gate
    line it opens with (silent or SessionStart degraded-mode)."""
    out = {**body, "hooks": []}
    for h in body["hooks"]:
        cmd = h["command"]
        for gate in _GATE_VARIANTS:
            if gate in cmd:
                cmd = cmd.replace(gate, gate + _GLOBAL_GUARD, 1)
                break
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

    @property
    def all_installed(self) -> bool:
        return (
            self.claude_session_start
            and self.claude_stop
            and self.claude_pre_compact
            and self.claude_pre_tool_use
        )


@dataclass(frozen=True)
class HookResult:
    """Outcome of an install / uninstall call.

    ``refreshed`` (install only) is the set of managed hooks whose body was
    rewritten in place because it differed from the canonical one — distinct
    from ``skipped`` (already identical), so an upgrade that silently changes
    ``settings.json`` is reported honestly rather than as 'already current'.
    Defaulted so existing constructions stay valid.
    """

    installed: tuple[str, ...]
    skipped: tuple[str, ...]  # already present (install) or absent (uninstall)
    removed: tuple[str, ...]  # uninstall only, or legacy-scrub on install
    errors: tuple[tuple[str, str], ...]  # (hook_name, error_message)
    refreshed: tuple[str, ...] = ()  # install only: body rewritten in place
    nudges: tuple[str, ...] = ()  # install only: emit-only advisories (e.g.
    # the statusLine nudge). Surfaced to the user, never written to settings.
    # Defaulted so existing constructions stay valid.


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


def install(project_root: Path, *, scope: str = "local") -> HookResult:
    """Install the SessionStart drift, Stop nudge/reconcile-gate, PreCompact
    breadcrumb, and PreToolUse doc-write guard hooks. Idempotent.

    ``scope="local"`` (default) writes the repo's ``.claude/settings.json``
    and scrubs the legacy ``git post-commit`` / ``PostToolUse`` entries so
    upgraders from <=0.13.4 land clean. ``scope="global"`` writes
    ``~/.claude/settings.json`` with defer-check-guarded bodies (so a repo's
    own ``--local`` install takes precedence) and performs no git scrub — a
    user-level install owns no single repo's git hooks. Hooks the user
    installed themselves (no sentinel) are left untouched.
    """
    project_root = project_root.resolve()
    installed: list[str] = []
    skipped: list[str] = []
    removed: list[str] = []
    refreshed: list[str] = []
    errors: list[tuple[str, str]] = []

    # Scrub the legacy git post-commit hook so upgraders aren't left with
    # the broken `rebuild --changed` behaviour. Local scope only — a global
    # install does not own any one repo's git hooks.
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

    # Install the current Claude hooks (SessionStart drift + Stop nudge +
    # reconcile-gate + PreCompact breadcrumb), all under our sentinel.
    for event, body in _hooks_for_scope(scope):
        try:
            # Classify by whether the file actually changed on disk:
            # install_hook_entry collapses "refreshed in place" and "already
            # identical" into one False, and it preserves co-located user hooks
            # in the managed entry — so comparing against the canonical `body`
            # would mis-report "refreshed" forever once a user wires their own
            # hook beside ours. A byte-level before/after is the honest signal
            # (install_hook_entry only rewrites when the merged body differs).
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

    # Emit-only statusline nudge: surface it on the result when no `statusLine`
    # is wired (local or global). The decision lives entirely in
    # `statusline_nudge`; install just carries the advisory. It writes NOTHING
    # to settings — the only mutation install performs is the hooks block above.
    nudges: tuple[str, ...] = ()
    nudge = statusline_nudge(project_root)
    if nudge is not None:
        nudges = (nudge,)

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


# ----- uninstall ------------------------------------------------------------


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


# ----- status ---------------------------------------------------------------


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
