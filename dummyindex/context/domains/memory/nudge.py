"""Stop-hook handoff nudge: decide whether to prompt for a session handoff.

Deterministic. No prose — the rich handoff is the agent's job via
/dummyindex-remember. This module only decides *whether* to nudge and
renders the `additionalContext` payload the Stop hook prints to stdout.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .._io import write_text_atomic
from ._parse import read_text_or_empty, section_date, split_sections
from ._transcript import read_session_signal
from .detect import remember_plugin_present
from .enums import AUTO_BREADCRUMB_TAG, MemoryTier
from .store import memory_dir

# A session is "long" once its main-thread output crosses this many tokens.
# Starting constant — calibrated by observation, not user-configurable in v1.
LONG_OUTPUT_TOKENS = 40_000


def is_significant(output_tokens: int, subagent_file_count: int) -> bool:
    """True when the session is worth prompting a handoff for."""
    if subagent_file_count > 0:
        return True
    return output_tokens >= LONG_OUTPUT_TOKENS


def _state_path(context_dir: Path) -> Path:
    """Per-session nudge marker file (gitignored cache)."""
    return context_dir / "cache" / "nudge-state.json"


def _load_state(context_dir: Path) -> dict:
    path = _state_path(context_dir)
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return obj if isinstance(obj, dict) else {}


def already_nudged(context_dir: Path, session_id: str) -> bool:
    """True when a nudge has already fired for this session."""
    if not session_id:
        return False
    return session_id in _load_state(context_dir)


def mark_nudged(context_dir: Path, session_id: str, now: datetime) -> None:
    """Record that we nudged this session. No-op for an empty session id."""
    if not session_id:
        return
    state = _load_state(context_dir)
    state[session_id] = {"nudged_at": now.isoformat()}
    if len(state) > 100:
        keep = sorted(state.items(), key=lambda kv: kv[1].get("nudged_at", ""), reverse=True)[:100]
        state = dict(keep)
    write_text_atomic(_state_path(context_dir), json.dumps(state, indent=2) + "\n")


def real_handoff_saved_today(root: Path, now: datetime) -> bool:
    """True when now.md's newest entry is a real (non-breadcrumb) handoff
    dated today — meaning the user already saved, so don't nudge."""
    now_path = memory_dir(root / ".context") / MemoryTier.NOW.value
    _preamble, sections = split_sections(read_text_or_empty(now_path))
    if not sections:
        return False
    top = sections[0]
    iso = section_date(top.heading)
    return iso == now.date().isoformat() and AUTO_BREADCRUMB_TAG not in top.heading


def render_additional_context(
    *, total_output_tokens: int, subagent_file_count: int
) -> str:
    """The Stop-hook stdout payload that reaches the model and grants a turn."""
    message = (
        f"dummyindex: this session is substantial (subagents: {subagent_file_count}; "
        f"~{total_output_tokens:,} main-thread output tokens) and no handoff has been "
        f"saved this session. In one short line, offer the user the option to checkpoint "
        f"a session handoff, and only if they agree run /dummyindex-remember. "
        f"Do NOT save automatically."
    )
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": message,
            }
        }
    )


def decide_nudge(
    *,
    root: Path,
    main_transcript: Optional[Path],
    session_id: str,
    now: datetime,
) -> Optional[str]:
    """Return the additionalContext JSON to print, or None to stay silent.

    Cheap checks first (O(1) file stats) so the per-turn Stop hook only pays
    for the transcript parse on the rare turn that actually nudges.
    """
    if remember_plugin_present(root):
        return None
    context_dir = root / ".context"
    if already_nudged(context_dir, session_id):
        return None
    if real_handoff_saved_today(root, now):
        return None
    if main_transcript is None or not main_transcript.exists():
        return None
    signal = read_session_signal(main_transcript)
    if not is_significant(signal.output_tokens, signal.subagent_file_count):
        return None
    mark_nudged(context_dir, session_id, now)
    return render_additional_context(
        total_output_tokens=signal.output_tokens,
        subagent_file_count=signal.subagent_file_count,
    )
