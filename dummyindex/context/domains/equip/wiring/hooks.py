"""Wire equip's catalog hooks into ``.claude/settings.json`` (spec §5).

The catalog decides *which* settings hooks equip should install
(:class:`HookSpec`); this module performs the actual install through the shared
:mod:`dummyindex.context.claude_settings` machinery, keyed by equip's own
sentinel (:data:`EQUIP_SENTINEL`) so it coexists with — and uninstalls
independently of — the auto-refresh SessionStart hook.

:func:`wire_hooks` is the only seam the CLI apply path touches. It is idempotent
(re-installing the same body is a no-op, a changed body refreshes in place) and
preserve-or-refuse: an unparseable ``settings.json`` raises
:class:`MalformedSettingsError` rather than clobbering the user's file — the
caller catches it, skips the hook, and still writes the generated files.
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

    One settings entry per hook, keyed by ``EQUIP_SENTINEL:<event>`` in the command
    body so a re-run refreshes in place instead of duplicating. Legacy entries
    carrying the unsuffixed sentinel are scrubbed first, so upgraders never end
    up with the same hook firing twice. Returns the event names that received
    (or refreshed) an entry — the same event may appear once per hook targeting
    it. Raises
    :class:`~dummyindex.context.claude_settings.MalformedSettingsError` when the
    file exists but cannot be parsed as a JSON object (the caller decides what
    to do — equip skips the hook and reports).
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
