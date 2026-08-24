"""Extract a SWE-bench-style model patch from a finished agent workspace.

The official harness consumes ``{"instance_id", "model_patch"}`` rows where
``model_patch`` is a unified git diff of the agent's changes relative to the
task's base commit — including newly created files, excluding nothing else.
Recipe: stage everything (``git add -A``, which picks up untracked files),
diff the index against the base commit, then reset the index so the
workspace stays inspectable afterwards.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class PatchError(Exception):
    """Raised when the workspace cannot yield a diff."""


def _git(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PatchError(
            f"git {' '.join(argv)} exited {result.returncode}: {result.stderr[-300:]!r}"
        )
    return result.stdout


def extract_model_patch(workspace: Path, base_commit: str) -> str:
    """Unified diff of all changes in ``workspace`` vs ``base_commit``.

    Returns an empty string when the agent changed nothing (a legitimate
    outcome; the harness will score it as unresolved).
    """
    if not (workspace / ".git").exists():
        raise PatchError(f"not a git checkout: {workspace}")
    _git(["add", "-A"], cwd=workspace)
    try:
        return _git(["diff", "--cached", base_commit], cwd=workspace)
    finally:
        subprocess.run(
            ["git", "reset", "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )


def head_commit(workspace: Path) -> str:
    """Current HEAD sha of a workspace (pin verification helper)."""
    out = _git(["rev-parse", "HEAD"], cwd=workspace)
    return out.strip()
