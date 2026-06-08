"""Stop-hook handoff nudge: decide whether to prompt for a session handoff.

Deterministic. No prose — the rich handoff is the agent's job via
/dummyindex-remember. This module only decides *whether* to nudge and
renders the `additionalContext` payload the Stop hook prints to stdout.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Optional

from dummyindex.usage.models import TurnUsage
from dummyindex.usage.transcripts import load_session

from .._io import write_text_atomic
from ._parse import read_text_or_empty, section_date, split_sections
from .detect import remember_plugin_present
from .enums import AUTO_BREADCRUMB_TAG, MemoryTier
from .store import memory_dir

# A session is "long" once its main-thread output crosses this many tokens.
# Starting constant — calibrated by observation, not user-configurable in v1.
LONG_OUTPUT_TOKENS = 40_000


def total_main_output_tokens(main_turns: Iterable[TurnUsage]) -> int:
    """Sum of main-thread output tokens across the session's turns."""
    return sum(turn.output_tokens for turn in main_turns)


def is_significant(
    main_turns: tuple[TurnUsage, ...], subagent_file_count: int
) -> bool:
    """True when the session is worth prompting a handoff for.

    Significant if any subagent ran, or the main-thread output crossed the
    long-session threshold.
    """
    if subagent_file_count > 0:
        return True
    return total_main_output_tokens(main_turns) >= LONG_OUTPUT_TOKENS


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
    main_turns, _subagent_turns, subagent_file_count = load_session(main_transcript)
    if not is_significant(main_turns, subagent_file_count):
        return None
    mark_nudged(context_dir, session_id, now)
    return render_additional_context(
        total_output_tokens=total_main_output_tokens(main_turns),
        subagent_file_count=subagent_file_count,
    )
