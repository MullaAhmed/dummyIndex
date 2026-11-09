"""The committed GC anchor and the commit-throttled fire-once signal.

Two stores, deliberately split: the committed ``GC_STATE_REL`` anchor holds only
the last sweep's sha (``{"anchor": sha}``); the gitignored ``GC_MEMO_REL`` memo,
keyed by session id, fires the SessionStart nudge at most once per session
(best-effort, last-writer-wins, never committed). Both readers and the memo
mirror ``memory/nudge.py``; commit math reuses ``git_delta.commits_since``.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from ...build.git_delta import commits_since, head_commit
from ..atomic_io import write_text_atomic
from .constants import DEFAULT_COMMIT_THRESHOLD, GC_MEMO_REL, GC_STATE_REL

# The memo is pruned to the most-recent entries past this cap (mirrors
# ``memory/nudge.py`` — the marker file must not grow unbounded across sessions).
_MEMO_CAP = 100


def read_gc_anchor(context_dir: Path) -> str | None:
    """Return the committed GC anchor sha, or ``None``. Never raises.

    A missing file, bad JSON, a non-dict payload, or a missing / non-string /
    empty ``anchor`` all degrade to ``None``, never a garbage sha.
    """
    path = context_dir / GC_STATE_REL
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    if not isinstance(obj, dict):
        return None
    value = obj.get("anchor")
    return value if isinstance(value, str) and value else None


def write_gc_anchor(context_dir: Path, sha: str) -> None:
    """Atomically write ``{"anchor": sha}`` to ``context_dir / GC_STATE_REL``.

    The parent dir is created as needed; the trailing newline keeps the
    committed artifact ``end-of-file-fixer``-clean.
    """
    path = context_dir / GC_STATE_REL
    write_text_atomic(path, json.dumps({"anchor": sha}, indent=2) + "\n")


def gc_commits_since(context_dir: Path, root: Path) -> int | None:
    """Commits landed on HEAD since the recorded GC anchor, or ``None``.

    ``None`` (the signal goes safely dark) when no anchor is recorded, git is
    absent, HEAD is unborn, or a history rewrite orphaned the anchor.
    """
    return commits_since(root, read_gc_anchor(context_dir))


def _is_shallow(root: Path) -> bool:
    """True when ``root`` is a shallow clone. Any git failure reads as not shallow."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-shallow-repository"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.stdout.strip() == "true"


def anchor_orphaned(context_dir: Path, root: Path) -> bool:
    """True when a recorded anchor is unknown to the repo after a rewrite.

    The orphaned-anchor case: an anchor IS recorded, git IS present
    (``head_commit`` resolves), yet ``gc_commits_since`` is ``None`` — meaning
    the recorded sha no longer resolves in the repo (rebase / squash / never-
    fetched). Off-git or no-anchor is *not* orphaned: there's nothing a rewrite
    could have stranded. A shallow clone is never orphaned either: its missing
    history is silent truncation, not a rewrite.
    """
    if read_gc_anchor(context_dir) is None:
        return False
    if head_commit(root) is None:
        return False
    if _is_shallow(root):
        return False
    return gc_commits_since(context_dir, root) is None


def should_signal(
    context_dir: Path,
    root: Path,
    session_id: str,
    *,
    threshold: int = DEFAULT_COMMIT_THRESHOLD,
    now: datetime | None = None,
) -> bool:
    """Whether the SessionStart nudge should fire for ``session_id``.

    True iff this session has not already been signalled AND either at least
    ``threshold`` commits have landed since the GC anchor, or the anchor is
    orphaned. On a decision to signal the fire-once memo is marked (so a second
    call in the same session returns ``False``).

    The memo lives in the **gitignored** ``context_dir / GC_MEMO_REL``, keyed by
    ``session_id`` and pruned to a 100-entry cap — mirroring
    ``nudge.already_nudged`` / ``mark_nudged``. An empty / blank ``session_id``
    is never recorded and never suppresses: it degrades to "emit when the
    trigger holds" so the nudge is never silenced forever by a missing id.
    ``now`` is injectable for testability (defaults to wall-clock).
    """
    count = gc_commits_since(context_dir, root)
    if count is None:
        if not anchor_orphaned(context_dir, root):
            return False
    elif count < threshold:
        return False
    if _already_signalled(context_dir, session_id):
        return False
    _mark_signalled(context_dir, session_id, now or datetime.now())
    return True


def stamp_gc(
    context_dir: Path,
    root: Path,
    *,
    to: str | None = None,
) -> str | None:
    """Advance the GC anchor to ``to`` (else HEAD) and return the stamped sha.

    With no ``to`` and no resolvable HEAD (off-git or unborn) this is a graceful
    no-op returning ``None``, never a raise, like ``reconcile.stamp_reconciled``.
    """
    target = to if to is not None else head_commit(root)
    if target is None:
        return None
    write_gc_anchor(context_dir, target)
    return target


def _memo_path(context_dir: Path) -> Path:
    """The gitignored per-session fire-once memo file."""
    return context_dir / GC_MEMO_REL


def _load_memo(context_dir: Path) -> dict:
    """Load the fire-once memo, tolerating a missing / corrupt file (→ ``{}``)."""
    path = _memo_path(context_dir)
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _already_signalled(context_dir: Path, session_id: str) -> bool:
    """True when this session has already been signalled. Empty id → ``False``."""
    if not session_id:
        return False
    return session_id in _load_memo(context_dir)


def _mark_signalled(context_dir: Path, session_id: str, now: datetime) -> None:
    """Record that we signalled this session. No-op for an empty session id."""
    if not session_id:
        return
    memo = _load_memo(context_dir)
    memo[session_id] = {"signalled_at": now.isoformat()}
    if len(memo) > _MEMO_CAP:
        keep = sorted(
            memo.items(),
            key=lambda kv: kv[1].get("signalled_at", ""),
            reverse=True,
        )[:_MEMO_CAP]
        memo = dict(keep)
    write_text_atomic(_memo_path(context_dir), json.dumps(memo, indent=2) + "\n")
