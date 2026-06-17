"""`dummyindex context statusline` — print the cached ``.context/`` freshness badge.

This is the **cold-path fallback** for the freshness statusline (spec §5). The
per-prompt hot path is a shipped shell/PowerShell wrapper (``statusline.sh`` /
``statusline.ps1``, under :data:`SCRIPT_DIR`) that ``cat``s the gitignored badge
cache directly — no Python, no import cost. This command exists for shells that
would rather call one tool than special-case ``cat``, and it reads the *same*
cache file the ``plan-update`` writer populates, resolved through the single
:func:`~dummyindex.cli.plan_update.badge_cache_path` source of truth (never a
second hard-coded name).

Output contract (CRITICAL — this runs on every prompt):

- Stdout: the badge cache's exact contents (e.g. ``[ctx ✓]`` / ``[ctx: 3 drift]``)
  when present and readable; **empty** otherwise.
- Exit code: **always 0**. A missing ``.context/``, a missing cache, an
  unreadable/malformed cache, or *any* other exception collapse to empty
  stdout + exit 0 — it must never crash a user's shell.
- It **never recomputes drift**: it only echoes the pre-computed cache. Refresh
  is owned by the ``plan-update`` SessionStart path.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import parse_path_and_root, resolve_context_root
from .plan_update import badge_cache_path

# Directory holding the shipped hot-path wrappers (``statusline.sh`` /
# ``statusline.ps1``). They live with the packaged skills assets and are
# exported via ``pyproject``'s ``package-data`` so a ``pip``-installed
# dummyindex ships them too. Tests assert both files exist here.
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "skills" / "statusline"


def run(argv: list[str]) -> int:
    """Print the cached freshness badge; swallow everything → empty out, rc 0.

    The whole body is wrapped in a single broad ``except`` on purpose: this is
    invoked on every prompt and must never propagate an error into the user's
    shell. There is deliberately no error message and no non-zero exit — a
    silent empty line is the correct degraded behaviour.
    """
    try:
        scope, explicit_root, _rest = parse_path_and_root(argv)
        project_root = resolve_context_root(scope, explicit_root=explicit_root)
        context_dir = project_root / ".context"
        if not context_dir.is_dir():
            # Not a ``.context`` project — print nothing, exit clean.
            return 0

        cache_path = badge_cache_path(context_dir)
        if not cache_path.is_file():
            # Badge not cached yet (no ``plan-update`` has run) — silent.
            return 0

        # Read the pre-computed badge verbatim and echo it with no trailing
        # newline, so the host's statusLine renders exactly what was cached.
        badge = cache_path.read_text(encoding="utf-8")
        if badge:
            print(badge, end="")
        return 0
    except Exception:
        # Best-effort by contract: any failure → empty stdout, exit 0.
        return 0
