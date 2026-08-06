"""Resolve the host transcript store — never hardcode it.

Ported (as a technique, not copied source; see the package docstring in
``__init__.py`` for the Apache-2.0 attribution) from headroom's
``learn/_shared.claude_config_dir()`` and the ``claude_dir=`` constructor
escape hatch on ``learn/plugins/claude.ClaudeCodePlugin``: Claude Code
relocates its whole config directory (including ``projects/``) when
``CLAUDE_CONFIG_DIR`` is set, so the config dir — not ``projects/`` itself —
is what must honor the env var. `dummyindex/context/domains/memory/transcript.py`
already reimplements this same env-var read for its own narrower need
(finding *this* session's transcript); this module adds the one thing that
reader doesn't need: an explicit override parameter for a store the env var
cannot reach at all, e.g. a fixture directory in tests or a store relocated
outside Claude Code's own convention.
"""

from __future__ import annotations

import os
from pathlib import Path

_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"


def resolve_claude_config_dir(*, override: Path | None = None) -> Path:
    """The Claude Code config directory: ``override``, else ``$CLAUDE_CONFIG_DIR``,
    else ``~/.claude``."""
    if override is not None:
        return override
    env = os.environ.get(_CONFIG_DIR_ENV)
    return Path(env) if env else Path.home() / ".claude"


def resolve_claude_config_dirs(
    *,
    override: Path | None = None,
) -> tuple[Path, ...]:
    """Return every local Claude profile that can contribute feedback.

    An explicit override is deliberately exclusive. Normal hook runs union the
    active profile, the standard profile, and existing ``.claude-*`` siblings.
    The caller still checks whether each profile contains this repo.
    """
    if override is not None:
        return (override,)

    home = Path.home()
    candidates = {home / ".claude"}
    env = os.environ.get(_CONFIG_DIR_ENV)
    if env:
        candidates.add(Path(env))
    try:
        candidates.update(path for path in home.glob(".claude-*") if path.is_dir())
    except OSError:
        pass
    return tuple(sorted(candidates, key=lambda path: str(path)))


def resolve_transcript_store(*, override: Path | None = None) -> Path:
    """The ``projects/`` transcript store under the resolved config dir.

    ``override`` names the config directory (matching
    ``ClaudeCodePlugin(claude_dir=...)``'s escape hatch), not the store
    itself, so a caller pointing at a non-standard machine layout only ever
    has to know one directory.
    """
    return resolve_claude_config_dir(override=override) / "projects"
