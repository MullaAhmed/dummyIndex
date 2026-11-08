"""`dummyindex context statusline`: print the cached ``.context/`` freshness badge.

Cold-path fallback for the shipped ``statusline.sh`` / ``.ps1`` (:data:`SCRIPT_DIR`), which
``cat`` the same gitignored cache ``plan-update`` writes (path via ``badge_cache_path``).
Prints it verbatim: ``[ctx ✓]`` when fresh, else a drift count such as
``[ctx: 2 edited · 1 anchored]``; empty when absent. Always exits 0 so it must never crash
the user's shell, and it never recomputes drift.
"""

from __future__ import annotations

from pathlib import Path

from .common import parse_path_and_root, resolve_context_root
from .plan_update import badge_cache_path

# The shipped hot-path wrappers (``statusline.sh`` / ``statusline.ps1``), packaged
# via ``pyproject`` ``package-data`` so a pip install ships them. Tests assert both
# files exist here.
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "skills" / "statusline"


def run(argv: list[str]) -> int:
    """Print the cached freshness badge; swallow everything → empty out, rc 0.

    The single broad ``except`` is deliberate: this runs on every prompt and must
    never propagate an error, message or non-zero exit into the user's shell.
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
