"""Wire equip's catalog hooks into ``.claude/settings.json`` (spec §5).

Installs via :mod:`dummyindex.context.claude_settings`, keyed by
:data:`EQUIP_SENTINEL` so it coexists with, and uninstalls separately from, the
auto-refresh SessionStart hook. Never clobbers: an unparseable ``settings.json``
raises :class:`MalformedSettingsError`; the caller skips the hook and still
writes the generated files.
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.context.claude_settings import install_hook_entry, remove_hook_entries

from ..constants import EQUIP_SENTINEL
from ..models import HookSpec

# Pre-cleanup equip wrote a bare `# DUMMYINDEX_EQUIP` comment (no event suffix).
# The trailing newline keeps this from matching the new suffixed form, so the
# scrub below removes only legacy entries on upgrade.
_LEGACY_SENTINEL = f"{EQUIP_SENTINEL}\n"


def wire_hooks(settings_path: Path, hooks: tuple[HookSpec, ...]) -> tuple[str, ...]:
    """Install each ``HookSpec`` into ``settings_path``; return the events wired.

    One entry per hook, keyed by ``EQUIP_SENTINEL:<event>`` so a re-run refreshes
    in place. Legacy unsuffixed-sentinel entries are scrubbed first so a hook
    never fires twice after upgrade. An event appears once per hook targeting it.
    Raises :class:`~dummyindex.context.claude_settings.MalformedSettingsError`
    when the file exists but is not a JSON object.
    """
    remove_hook_entries(settings_path, sentinel=_LEGACY_SENTINEL)
    wired: list[str] = []
    for hook in hooks:
        body = {
            "matcher": hook.matcher,
            "hooks": [{"type": "command", "command": hook.command}],
        }
        install_hook_entry(
            settings_path, hook.event, body, sentinel=f"{EQUIP_SENTINEL}:{hook.event}"
        )
        wired.append(hook.event)
    return tuple(wired)
