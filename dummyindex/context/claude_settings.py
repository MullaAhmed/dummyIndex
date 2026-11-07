"""Shared ``.claude/settings.json`` hook machinery.

Used by the managed hooks (:mod:`context.hooks`) and equip's PostToolUse format
hook (:mod:`context.domains.equip.wiring.hooks`), so preserve-or-refuse,
install-by-sentinel and the atomic write live in one place. We never overwrite a
file we can't round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MalformedSettingsError(ValueError):
    """Raised when ``.claude/settings.json`` exists but isn't a valid JSON object.

    We refuse to write over it: replacing it with just our hook would destroy the
    user's permissions, env and other hooks.
    """


def load_settings(settings_path: Path) -> dict[str, Any]:
    """Parse ``settings.json`` into a dict, or ``{}`` when the file is absent.

    Raises :class:`MalformedSettingsError` when the file is invalid JSON or not a
    top-level object (``[]``, ``42``, …); callers must not write in that case.
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

    # Refresh our entry (found by sentinel) in place so it stays current. Merge per
    # HOOK, not per entry: users wire their own hooks into our managed entry's
    # `hooks` array, and replacing the entry would drop them on every upgrade.
    # Canonical hooks first, preserved user hooks after.
    for entry in events:
        for h in entry.get("hooks", []):
            if sentinel in (h.get("command") or ""):
                idx = events.index(entry)
                preserved = [
                    hook
                    for hook in entry.get("hooks", [])
                    if sentinel not in (hook.get("command") or "")
                ]
                desired = {
                    **hook_body,
                    "hooks": [*hook_body.get("hooks", []), *preserved],
                }
                if events[idx] == desired:
                    return False
                events[idx] = desired
                write_settings(settings_path, settings)
                return False

    events.append(hook_body)
    write_settings(settings_path, settings)
    return True


def remove_hook_entries(settings_path: Path, *, sentinel: str) -> list[str]:
    """Strip every ``sentinel``-bearing hook from every event.

    Filters per HOOK, like :func:`install_hook_entry`: an entry that also holds a
    user hook keeps it; an entry left empty is dropped, as is an empty ``hooks``
    block. Entries without ``sentinel`` are untouched. Returns the event names
    that lost at least one of our hooks. Raises
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
        new_events: list[dict] = []
        event_changed = False
        for e in events:
            entry_hooks = e.get("hooks", [])
            kept_hooks = [
                h for h in entry_hooks if sentinel not in (h.get("command") or "")
            ]
            if len(kept_hooks) == len(entry_hooks):
                new_events.append(e)  # no sentinel hooks here → untouched
                continue
            event_changed = True
            if kept_hooks:
                # Keep the entry for its co-located user hook(s) only.
                new_events.append({**e, "hooks": kept_hooks})
            # else: entry held only our hooks → drop it entirely.
        if not event_changed:
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
