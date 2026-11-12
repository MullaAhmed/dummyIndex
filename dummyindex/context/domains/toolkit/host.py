"""Project and user host-config layout, JSON read/write, and the backup session.

Host files are edited by merge, never overwrite: an object is read, one key is
changed, and the rest of the object is written back unchanged. Before the first
write to a file in one run, a timestamped copy is made: for project scope under
``.context/toolkit/backups/``, for user scope next to the file. The first copy of
the run is reported as ``backup_path``. Every write is atomic.

Secrets: the stash (``disabled.json``) and the backups hold full MCP server
definitions, which can carry tokens in ``env`` or ``headers``. Both live under
``.context/toolkit/`` (project) or ``<claude>/toolkit/`` (user) and must never be
committed. Before a project write, the managed ``.context/.gitignore`` is brought
up to date so ``/toolkit/`` is ignored; user scope lives outside any repo.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...build.upgrade import ensure_context_gitignore
from ..atomic_io import write_text_atomic
from .constants import PROJECT_STASH_DIR, STASH_FILE, USER_STASH_DIR
from .errors import ToolkitError
from .paths import safe_target


@dataclass(frozen=True)
class Layout:
    """Where one host scope keeps its MCP servers, skills, plugin toggles, stash."""

    scope: str  # "project" or "user"
    mcp_base: Path
    mcp_parts: tuple[str, ...]
    claude_base: Path
    settings_parts: tuple[str, ...]
    skills_parts: tuple[str, ...]
    stash_parts: tuple[str, ...]
    backup_in_toolkit: bool = False

    def mcp_path(self) -> Path:
        return safe_target(self.mcp_base, *self.mcp_parts)

    def settings_path(self) -> Path:
        return safe_target(self.claude_base, *self.settings_parts)

    def skills_dir(self) -> Path:
        return safe_target(self.claude_base, *self.skills_parts)

    def skill_file(self, name: str) -> Path:
        return safe_target(self.claude_base, *self.skills_parts, name, "SKILL.md")

    def stash_path(self) -> Path:
        return safe_target(self.claude_base, *self.stash_parts)

    def backup_root(self) -> Path:
        """``<toolkit dir>/backups``: skill copies, and host backups at project scope."""
        return safe_target(self.claude_base, *self.stash_parts[:-1], "backups")

    def host_backup_dir(self) -> Path | None:
        """Where host-file backups go, or ``None`` to sit next to the file (user scope)."""
        return self.backup_root() if self.backup_in_toolkit else None


def project_layout(root: Path) -> Layout:
    return Layout(
        scope="project",
        mcp_base=root,
        mcp_parts=(".mcp.json",),
        claude_base=root,
        settings_parts=(".claude", "settings.json"),
        skills_parts=(".claude", "skills"),
        stash_parts=(*PROJECT_STASH_DIR, STASH_FILE),
        backup_in_toolkit=True,
    )


def user_claude_dir(home: Path) -> Path:
    """``$CLAUDE_CONFIG_DIR`` when set, else ``<home>/.claude``."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) if override else home / ".claude"


def user_layout(home: Path) -> Layout:
    claude_dir = user_claude_dir(home)
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        mcp_base = claude_dir
    else:
        mcp_base = home
    return Layout(
        scope="user",
        mcp_base=mcp_base,
        mcp_parts=(".claude.json",),
        claude_base=claude_dir,
        settings_parts=("settings.json",),
        skills_parts=("skills",),
        stash_parts=(*USER_STASH_DIR, STASH_FILE),
    )


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _guard_toolkit_dir(path: Path) -> None:
    """Ignore ``.context/toolkit/`` before writing under ``path``; no-op outside ``.context/``."""
    for parent in (path, *path.parents):
        if parent.name == ".context":
            ensure_context_gitignore(parent)
            return


@dataclass
class WriteSession:
    """One CLI run. Backs up each host file once, before its first write.

    ``backup_dir`` set: copies go there. Unset: copies go next to the file.
    """

    backup_path: str | None = None
    backup_dir: Path | None = None
    _seen: set[str] = field(default_factory=set)

    def backup(self, path: Path) -> None:
        key = str(path)
        if key in self._seen:
            return
        self._seen.add(key)
        if not path.exists():
            return
        folder = self.backup_dir or path.parent
        if self.backup_dir is not None:
            _guard_toolkit_dir(folder)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = _stamp()
        dest = folder / f"{path.name}.bak-{stamp}"
        counter = 1
        while dest.exists():
            dest = folder / f"{path.name}.bak-{stamp}-{counter}"
            counter += 1
        shutil.copy2(path, dest)
        if self.backup_path is None:
            self.backup_path = str(dest)


def preserve_skill(layout: Layout, live: Path, name: str) -> Path:
    """Copy a live single-file skill's SKILL.md into the backups before it is deleted."""
    folder = safe_target(layout.backup_root(), "skills", name)
    _guard_toolkit_dir(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"SKILL.md.bak-{_stamp()}"
    counter = 1
    while dest.exists():
        dest = folder / f"SKILL.md.bak-{_stamp()}-{counter}"
        counter += 1
    shutil.copy2(live, dest)
    return dest


def read_object(path: Path) -> dict[str, Any]:
    """A JSON object from ``path``, ``{}`` when absent. Refuses anything unparsable."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolkitError(
            "malformed_config",
            f"{path} is not valid JSON ({exc}); left unchanged, fix it by hand",
        ) from exc
    if not isinstance(data, dict):
        raise ToolkitError(
            "malformed_config",
            f"{path} is not a JSON object; left unchanged, fix it by hand",
        )
    return data


def write_object(path: Path, data: dict[str, Any], session: WriteSession) -> None:
    session.backup(path)
    write_text_atomic(path, json.dumps(data, indent=2) + "\n")


def read_stash(layout: Layout) -> list[dict[str, Any]]:
    """Disabled definitions held for one host scope (``[]`` when none)."""
    data = read_object(layout.stash_path())
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ToolkitError("malformed_config", "toolkit stash 'items' is not a list")
    return [i for i in items if isinstance(i, dict)]


def write_stash(layout: Layout, items: list[dict[str, Any]]) -> None:
    _guard_toolkit_dir(layout.stash_path())
    write_text_atomic(
        layout.stash_path(),
        json.dumps({"schema_version": 1, "items": items}, indent=2) + "\n",
    )


def find_stash(
    items: list[dict[str, Any]], kind: str, name: str
) -> dict[str, Any] | None:
    for item in items:
        if item.get("kind") == kind and item.get("name") == name:
            return item
    return None
