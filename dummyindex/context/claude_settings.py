"""Shared ``.claude/settings.json`` hook machinery.

Both the auto-refresh SessionStart hook (:mod:`context.hooks`) and equip's
PostToolUse format hook (:mod:`context.domains.equip.wiring.hooks`) write entries
into the user's ``settings.json``. They share one proven implementation here so
the preserve-or-refuse safety, idempotent install-by-sentinel, and atomic write
live in exactly one place.

The contract:

- :func:`load_settings` — parse into a dict, ``{}`` when absent, *refuse* (raise
  :class:`MalformedSettingsError`) when the file exists but is invalid JSON or a
  non-object top level. We never overwrite a file we can't round-trip.
- :func:`install_hook_entry` — add our entry under ``settings['hooks'][event]``,
  keyed by an in-body ``sentinel`` comment; idempotent, refresh-in-place when the
  body changed. Returns ``True`` iff a new entry was *appended*.
- :func:`remove_hook_entries` — strip every entry carrying ``sentinel`` from
  every event, preserving user entries and other sentinels. Returns the event
  names that lost at least one entry.
- :func:`write_settings` — atomic tmp+rename JSON write.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MalformedSettingsError(ValueError):
    """Raised when ``.claude/settings.json`` exists but isn't valid JSON.

    We refuse to write over a file we can't parse — the user's permissions,
    env, and other hooks may be recoverable by hand, and silently replacing
    it with just our hook would destroy them.
    """


def load_settings(settings_path: Path) -> dict[str, Any]:
    """Parse ``settings.json`` into a dict, or ``{}`` when the file is absent.

    Preserve-or-refuse: raises :class:`MalformedSettingsError` when the file
    exists but is either invalid JSON or a non-object top level (``[]``, ``42``,
    …). Callers must not write in that case — overwriting an unparseable file
    would destroy the user's permissions / env / other hooks.
    """
    if not settings_path.exists():
        return {}
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MalformedSettingsError(
            f"{settings_path} is not valid JSON ({exc}); left unchanged. "
            "Fix it by hand, then re-run the install."
        ) from exc
    if not isinstance(data, dict):
        raise MalformedSettingsError(
            f"{settings_path} is not a JSON object (found {type(data).__name__}); "
            "left unchanged. Fix it by hand, then re-run the install."
        )
    return data


def install_hook_entry(
    settings_path: Path,
    event: str,
    hook_body: dict[str, Any],
    *,
    sentinel: str,
) -> bool:
    """Add ``hook_body`` under ``settings['hooks'][event]`` if not already present.

    Returns ``True`` if a new entry was appended, ``False`` if an entry of ours
    (matched by ``sentinel`` in any command) already existed — refreshed in
    place when its body differed. Raises :class:`MalformedSettingsError` when the
    file exists but can't be safely parsed as a JSON object.
    """
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = load_settings(settings_path)

    hooks_block = settings.setdefault("hooks", {})
    events = hooks_block.setdefault(event, [])

    # Check for an existing entry of ours (by sentinel) and refresh it
    # in place so the body stays current after upgrades.
    for entry in events:
        for h in entry.get("hooks", []):
            if sentinel in (h.get("command") or ""):
                idx = events.index(entry)
                if events[idx] == hook_body:
                    return False
                events[idx] = hook_body
                write_settings(settings_path, settings)
                return False

    events.append(hook_body)
    write_settings(settings_path, settings)
    return True


def remove_hook_entries(settings_path: Path, *, sentinel: str) -> list[str]:
    """Strip every entry carrying ``sentinel`` from every event.

    Returns the event names that lost at least one entry. User entries and
    entries carrying a *different* sentinel are preserved. An event left empty
    is dropped; an empty ``hooks`` block is dropped. Raises
    :class:`MalformedSettingsError` rather than clobbering an unparseable file.
    """
    if not settings_path.exists():
        return []
    settings = load_settings(settings_path)
    hooks_block = settings.get("hooks")
    if not isinstance(hooks_block, dict):
        return []

    removed_events: list[str] = []
    changed = False
    for event in list(hooks_block.keys()):
        events = hooks_block.get(event)
        if not isinstance(events, list):
            continue
        new_events = [
            e
            for e in events
            if not any(
                sentinel in (h.get("command") or "") for h in e.get("hooks", [])
            )
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


def write_settings(settings_path: Path, payload: Any) -> None:
    """Atomically write ``payload`` as indented JSON to ``settings_path``."""
    tmp = settings_path.with_suffix(settings_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(settings_path)
