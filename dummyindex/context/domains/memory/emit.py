"""Render the SessionStart memory block (read-only).

Returns ``None`` (emit nothing) when the remember plugin is present or
the store has no meaningful content yet.
"""
from __future__ import annotations

from pathlib import Path

from ._parse import read_text_or_empty
from .detect import remember_plugin_present
from .enums import MemoryTier
from .store import memory_dir

_MAX_CHARS = 4000
_RECENT_HEAD = 1500


def _body_after_title(raw: str) -> str:
    """Everything below the leading ``# Title`` line, stripped."""
    lines = raw.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _head(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "\n…"


def render_session_start(root: Path, *, max_chars: int = _MAX_CHARS) -> str | None:
    if remember_plugin_present(root):
        return None
    mdir = memory_dir(root / ".context")
    if not mdir.is_dir():
        return None

    now = _body_after_title(read_text_or_empty(mdir / MemoryTier.NOW.value))
    recent = _body_after_title(read_text_or_empty(mdir / MemoryTier.RECENT.value))
    core = _body_after_title(read_text_or_empty(mdir / MemoryTier.CORE.value))
    if not (now or recent or core):
        return None

    parts: list[str] = ["=== MEMORY ==="]
    if now:
        parts.append(f"--- now.md ---\n{now}")
    if recent:
        parts.append(f"--- recent.md (head) ---\n{_head(recent, _RECENT_HEAD)}")
    if core:
        parts.append(f"--- core-memories.md ---\n{core}")

    handoff = (
        "=== HANDOFF ===\n"
        f"Write next handoff to: {mdir} — run /dummyindex-remember to save."
    )
    block = handoff + "\n\n" + "\n\n".join(parts)
    if len(block) > max_chars:
        block = block[:max_chars].rstrip() + "\n…(truncated)"
    return block
