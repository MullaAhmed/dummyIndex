"""Required-setup gate and `.context/` upgrade hooks (sentinel ``DUMMYINDEX_REQUIREMENTS``).

Two Claude Code hooks, kept apart from :mod:`context.hooks` because they have their
own sentinel and never go through its ``_guard_body``:

- **UserPromptSubmit gate** blocks a prompt while ``.context/config.toml`` requirements
  are unmet. Fail-open: any missing piece exits 0 silently.
- **SessionStart upgrade** runs ``context upgrade --if-stale`` when the stamped
  ``.context/`` version differs from the CLI version baked in at install time.

The global variant defers to a project that already carries this sentinel, so a
repo's own install wins. Old local hooks (no sentinel) do not defer it.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from .claude_settings import install_hook_entry, remove_hook_entries

REQUIREMENTS_SENTINEL = "DUMMYINDEX_REQUIREMENTS"

__all__ = [
    "REQUIREMENTS_SENTINEL",
    "install_requirements_hooks",
    "uninstall_requirements_hooks",
]

_GATE_TIMEOUT_SECONDS = 20

_HEADER = (
    f"# {REQUIREMENTS_SENTINEL}  managed by dummyindex (required-setup gate / "
    "upgrade)\n"
)

# Global copies defer to a project that already has the local gate. Old local
# hooks without the sentinel do not defer.
_GLOBAL_DEFER = (
    'ROOT="${CLAUDE_PROJECT_DIR:-.}"\n'
    "grep -qs " + REQUIREMENTS_SENTINEL + ' "$ROOT/.claude/settings.json" '
    '"$ROOT/.claude/settings.local.json" && exit 0\n'
)

_GATE_BODY = (
    'ROOT="${CLAUDE_PROJECT_DIR:-.}"\n'
    '[ -f "$ROOT/.context/config.toml" ] || exit 0\n'
    'OK="$ROOT/.context/cache/requirements.ok"\n'
    'if [ -f "$OK" ]; then\n'
    "  stale=0\n"
    '  for f in "$ROOT/.context/config.toml" "$ROOT/.context/equipment.json" '
    '"$ROOT/.claude/settings.json" "$ROOT/.claude/settings.local.json" '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json" '
    '"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/installed_plugins.json"; do\n'
    '    if [ -f "$f" ] && [ "$f" -nt "$OK" ]; then stale=1; break; fi\n'
    "  done\n"
    '  [ "$stale" = 0 ] && exit 0\n'
    "fi\n"
    "command -v dummyindex >/dev/null 2>&1 || { printf '%s\\n' "
    '\'{"decision":"block","reason":"dummyindex CLI not found. Install: '
    "pip install --user dummyindex (or uv tool install dummyindex), then "
    "resend.\"}'; exit 0; }\n"
    # Fail open: a non-zero exit (missing verb, internal error) would block the prompt.
    "dummyindex context requirements gate || exit 0\n"
)


def _upgrade_body(cli_version: str) -> str:
    # Version pattern is regex-escaped for grep -E; the stamp check stays in shell.
    pattern = (
        '"dummyindex_version"[[:space:]]*:[[:space:]]*"' + re.escape(cli_version) + '"'
    )
    return (
        'ROOT="${CLAUDE_PROJECT_DIR:-.}"\n'
        '[ -f "$ROOT/.context/meta.json" ] || exit 0\n'
        f'grep -qsE {shlex.quote(pattern)} "$ROOT/.context/meta.json" && exit 0\n'
        "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
        'dummyindex context upgrade --if-stale --root "$ROOT" 2>/dev/null || true\n'
        "dummyindex context requirements sync --local-only >/dev/null 2>&1 || true\n"
        "exit 0\n"
    )


def _gate_entry(*, global_scope: bool) -> dict:
    body = _HEADER + (_GLOBAL_DEFER if global_scope else "") + _GATE_BODY
    return {
        "hooks": [
            {
                "type": "command",
                "command": body,
                "timeout": _GATE_TIMEOUT_SECONDS,
            }
        ]
    }


def _upgrade_entry(cli_version: str, *, global_scope: bool) -> dict:
    body = (
        _HEADER + (_GLOBAL_DEFER if global_scope else "") + _upgrade_body(cli_version)
    )
    return {"matcher": "*", "hooks": [{"type": "command", "command": body}]}


def install_requirements_hooks(
    settings_path: Path, *, cli_version: str, global_scope: bool = False
) -> list[str]:
    """Install the gate (UserPromptSubmit) and upgrade (SessionStart) hooks.

    Idempotent by sentinel. Returns ``claude/<event>`` for each event whose entry was
    written (new or refreshed). Raises ``MalformedSettingsError`` on an unreadable file.
    """
    written: list[str] = []
    bodies = (
        ("UserPromptSubmit", _gate_entry(global_scope=global_scope)),
        (
            "SessionStart",
            _upgrade_entry(cli_version, global_scope=global_scope),
        ),
    )
    for event, body in bodies:
        before = settings_path.read_bytes() if settings_path.exists() else b""
        install_hook_entry(settings_path, event, body, sentinel=REQUIREMENTS_SENTINEL)
        after = settings_path.read_bytes() if settings_path.exists() else b""
        if before != after:
            written.append(f"claude/{event}")
    return written


def uninstall_requirements_hooks(settings_path: Path) -> list[str]:
    """Remove only the sentinel-bearing requirements hooks. Returns events changed."""
    # remove_hook_entries raises MalformedSettingsError on an unreadable file.
    removed = remove_hook_entries(settings_path, sentinel=REQUIREMENTS_SENTINEL)
    return [f"claude/{event}" for event in removed]
