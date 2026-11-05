"""Render one installed skill family without taking ownership of user edits."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ..common import (
    _SIBLING_SKILLS,
    _SKILLS_DIR,
    PACKAGE_VERSION,
    _first_symlink_component,
    render_skill,
    skill_rel,
    skills_root_rel,
)
from ..ownership import family_is_pristine, sync_family


def expected_families(
    platform: str, src: Path | None = None
) -> dict[str, dict[str, str]]:
    """The complete package-owned file set, without installing or deleting it."""
    main = src or _SKILLS_DIR / "skill.md"
    families = {
        "dummyindex": {
            "SKILL.md": render_skill(
                main.read_text(encoding="utf-8"), platform=platform
            )
        }
    }
    for folder in ("agents", "council", "retrieval"):
        for path in sorted((_SKILLS_DIR / folder).glob("*.md")):
            families["dummyindex"][f"{folder}/{path.name}"] = path.read_text(
                encoding="utf-8"
            )
    for folder, label in _SIBLING_SKILLS:
        entry = _SKILLS_DIR / folder / "SKILL.md"
        if not entry.is_file():
            continue
        files = {
            "SKILL.md": render_skill(
                entry.read_text(encoding="utf-8"), platform=platform
            )
        }
        for companion in ("templates", "agents"):
            for path in sorted((_SKILLS_DIR / folder / companion).glob("*")):
                if path.is_file() and path.suffix != ".tmpl":
                    files[f"{companion}/{path.name}"] = path.read_text(encoding="utf-8")
        families[label] = files
    return families


def _install_skill_family(
    base: Path, platform: str, src: Path, *, force_downgrade: bool = False
) -> bool:
    """Refresh package-owned files only; unknown companions are never swept."""
    root = base / skills_root_rel(platform)
    complete = True
    for family, files in expected_families(platform, src).items():
        directory = root / family
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            if family == "dummyindex":
                raise OSError(
                    f"refusing to write skill family through {directory}: not a plain directory"
                )
            print(f"  skill preserved  ->  {directory} (not a plain directory)")
            complete = False
            continue
        try:
            result = sync_family(
                directory,
                files,
                family=family,
                version=PACKAGE_VERSION,
                force_downgrade=force_downgrade,
            )
        except OSError as exc:
            print(f"  skill preparation failed -> {directory}: {exc}", file=sys.stderr)
            complete = False
            continue
        print(f"  {platform} skill installed  ->  {directory / 'SKILL.md'}")
        for name in result.preserved:
            print(f"  skill preserved  ->  {directory / name} (edited or unproven)")
        complete = complete and result.complete
    return complete


def reference_skill(base: Path, family: str, frontmatter_source: str) -> str:
    """A native discovery entry with no copy of the shared workflow body."""
    directory = base / skills_root_rel("claude") / family
    canonical = base / skills_root_rel("codex") / family / "SKILL.md"
    try:
        target = Path(
            os.path.relpath(canonical.resolve(), directory.resolve())
        ).as_posix()
    except ValueError:
        target = canonical.resolve().as_posix()
    close = (
        frontmatter_source.find("\n---\n", 4)
        if frontmatter_source.startswith("---\n")
        else -1
    )
    head = (
        frontmatter_source[: close + 5]
        if close != -1
        else f"---\nname: {family}\ndescription: Shared dummyindex workflow.\n---\n"
    )
    return (
        head
        + "\n<!-- dummyindex:skill-reference -->\n\n"
        + f"Read `{target}` relative to this file before doing this workflow.\n"
        + "That file owns the complete instructions. Resolve its companion paths "
        + "from its own directory and use the active host's native tools.\n"
    )


def _install_skill_references(
    base: Path, src: Path, *, force_downgrade: bool = False
) -> bool:
    complete = True
    for family, files in expected_families("codex", src).items():
        directory = base / skills_root_rel("claude") / family
        if directory.is_symlink():
            continue
        if directory.exists() and not directory.is_dir():
            print(f"  skill preserved  ->  {directory} (not a plain directory)")
            complete = False
            continue
        expected = {"SKILL.md": reference_skill(base, family, files["SKILL.md"])}
        if (
            directory.exists()
            and any(directory.iterdir())
            and not family_is_pristine(directory)
        ):
            print(
                f"  skill preserved  ->  {directory} (custom or unproven family; shared reference not installed)"
            )
            complete = False
            continue
        try:
            result = sync_family(
                directory,
                expected,
                family=family,
                version=PACKAGE_VERSION,
                layout="reference",
                force_downgrade=force_downgrade,
            )
        except OSError as exc:
            print(f"  native reference failed -> {directory}: {exc}", file=sys.stderr)
            complete = False
            continue
        print(f"  claude reference ->  {directory / 'SKILL.md'}")
        for name in result.preserved:
            print(f"  skill preserved  ->  {directory / name} (edited or unproven)")
        complete = complete and result.complete
    return complete


def _symlinked_skill_install_directory(
    base: Path,
    platform: str,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> Path | None:
    """Return a managed destination directory reached through a symlink."""
    main_dir = (base / skill_rel(platform)).parent
    directories = [
        main_dir,
        *(main_dir / name for name in ("agents", "council", "retrieval")),
    ]
    skills_root = base / skills_root_rel(platform)
    for _sub_name, skill_label in _SIBLING_SKILLS:
        sibling = skills_root / skill_label
        directories.extend((sibling, sibling / "templates", sibling / "agents"))
    for directory in directories:
        linked = _first_symlink_component(
            base, directory, allowed_symlinks=allowed_symlinks
        )
        if linked is not None:
            return linked
    return None
