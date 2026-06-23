"""`dummyindex uninstall` — remove the skill tree from the chosen scope."""

from __future__ import annotations

import sys
from pathlib import Path

from .common import COMMANDS_REL, SKILL_REL, remove_commands


def uninstall(*, scope: str = "user", project_dir: Path | None = None) -> None:
    """Remove the skill (and version stamp) from the chosen scope."""
    if scope not in ("user", "project"):
        print(
            f"error: --scope must be 'user' or 'project', got {scope!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    base = (project_dir or Path(".")).resolve() if scope == "project" else Path.home()
    dst = base / SKILL_REL  # ~/.claude/skills/dummyindex/SKILL.md
    skill_dir = dst.parent  # ~/.claude/skills/dummyindex/

    removed: list[str] = []
    if dst.exists():
        dst.unlink()
        removed.append(str(dst))

    # Remove every companion markdown installed alongside.
    for subdir in ("agents", "council", "retrieval"):
        sub_dst = skill_dir / subdir
        if sub_dst.is_dir():
            for md in sub_dst.glob("*.md"):
                md.unlink()
            try:
                sub_dst.rmdir()
            except OSError:
                pass

    version_file = skill_dir / ".dummyindex_version"
    if version_file.exists():
        version_file.unlink()

    # Sibling top-level skills (memory + build-loop) live in their own dirs.
    skills_root = base / ".claude" / "skills"
    for sibling in (
        "dummyindex-remember",
        "dummyindex-plan",
        "dummyindex-equip",
        "dummyindex-build",
        "dummyindex-audit",
        "dummyindex-update",
    ):
        sib_dir = skills_root / sibling
        if not sib_dir.is_dir():
            continue
        for path in sorted(sib_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            sib_dir.rmdir()
        except OSError:
            pass
        removed.append(str(sib_dir))

    for name in remove_commands(base):
        removed.append(str(base / COMMANDS_REL / name))

    # Best-effort: remove now-empty parent directories up to the scope root,
    # stopping at the first non-empty one.
    for d in (skill_dir, skill_dir.parent, skill_dir.parent.parent):
        try:
            d.rmdir()
        except OSError:
            break

    if removed:
        print(f"  skill removed  ->  {removed[0]}")
    else:
        print("nothing to remove")
