"""The unconditional real-tree write path for one skill family.

See the package docstring (``install/__init__.py``) for the split rationale.
"""

from __future__ import annotations

import shutil
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


def _install_skill_family(base: Path, platform: str, src: Path) -> None:
    """Copy the main skill, companions, and sibling skills for one host."""
    dst = base / skill_rel(platform)
    skill_dir = dst.parent
    # The write path stays unconditional (spec: "The preflight admission"):
    # never write through a family-dir symlink, even an OURS_HEALTHY one —
    # link mode replaces a link via `create_family_links`' safe-replacement
    # rename dance, it never writes through it. A MATERIALIZED placeholder
    # (a regular file occupying this slot) is refused the same way: without
    # this guard, `mkdir(exist_ok=True)` below raises `FileExistsError` for
    # either state, uncaught by this function's own callers unless they
    # classify first (`install()`'s direct-write loop does; a caller that
    # reaches here despite a symlinked/materialized family dir has skipped
    # that precheck).
    if skill_dir.is_symlink() or (skill_dir.exists() and not skill_dir.is_dir()):
        raise OSError(
            f"refusing to write skill family through {skill_dir}: not a "
            "plain directory (symlink or materialized link placeholder)"
        )
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Copy the SKILL.md (entry point) plus every companion markdown under
    # skills/agents/, skills/council/, skills/retrieval/. The orchestrator
    # references them as relative paths so the whole tree must ship.
    # The SKILL.md gets a `__VERSION__` placeholder substituted with the
    # installed package version so the user can verify what's running.
    if dst.is_symlink():
        dst.unlink()
    dst.write_text(
        render_skill(src.read_text(encoding="utf-8"), platform=platform),
        encoding="utf-8",
    )
    skills_pkg_dir = _SKILLS_DIR
    for subdir in ("agents", "council", "retrieval"):
        src_sub = skills_pkg_dir / subdir
        if not src_sub.is_dir():
            continue
        dst_sub = skill_dir / subdir
        dst_sub.mkdir(parents=True, exist_ok=True)
        # Drop any stale markdowns from a prior version first, so an upgrade
        # leaves exactly the current source set. v0.14 removed the chairman /
        # senior-developer / stage1-3 files; without this wipe they'd linger
        # beside the new pipeline docs and the orchestrator would see
        # contradictory personas.
        for stale in dst_sub.glob("*.md"):
            stale.unlink()
        for md in sorted(src_sub.glob("*.md")):
            shutil.copy(md, dst_sub / md.name)

    skills_root = base / skills_root_rel(platform)
    for sub_name, skill_label in _SIBLING_SKILLS:
        bl_src = _SKILLS_DIR / sub_name / "SKILL.md"
        if not bl_src.is_file():
            continue
        bl_dst = skills_root / skill_label / "SKILL.md"
        sibling_dir = bl_dst.parent
        if sibling_dir.is_symlink() or (
            sibling_dir.exists() and not sibling_dir.is_dir()
        ):
            # Same "never write through a symlink or materialized
            # placeholder" rule as the main family dir's guard above,
            # applied per sibling: the direct-write loop only classifies the
            # MAIN family before deciding whether to call this function at
            # all, so a SIBLING independently left OURS_DANGLING/MATERIALIZED
            # by an earlier partial run must not crash this one —
            # `create_family_links` heals every family, siblings included,
            # after this run's `execute_repairs` (the pinned sequencing).
            continue
        sibling_dir.mkdir(parents=True, exist_ok=True)
        if bl_dst.is_symlink():
            bl_dst.unlink()
        bl_dst.write_text(
            render_skill(bl_src.read_text(encoding="utf-8"), platform=platform),
            encoding="utf-8",
        )
        # Ship each skill's companion subtree alongside its SKILL.md (e.g.
        # audit's persona `agents/`, read from the installed dir). Copied
        # verbatim (no __VERSION__ substitution), like the main skill's
        # companions. `*.tmpl` render templates are SKIPPED: equip's renderer
        # resolves them package-relative (`equip/generate/render.py`), never
        # from the installed skill dir, so copying them ships inert files
        # that mislead agents and pollute reconcile/lint surfaces. Installs
        # <= 0.25.0 did copy them — purge those stale twins on upgrade.
        for companion in ("templates", "agents"):
            comp_src = _SKILLS_DIR / sub_name / companion
            comp_dst = bl_dst.parent / companion
            if comp_dst.is_dir():
                for stale in comp_dst.glob("*.tmpl"):
                    stale.unlink()
                if not any(comp_dst.iterdir()):
                    comp_dst.rmdir()
            if not comp_src.is_dir():
                continue
            items = [
                item
                for item in sorted(comp_src.glob("*"))
                if item.is_file() and item.suffix != ".tmpl"
            ]
            if not items:
                continue
            comp_dst.mkdir(parents=True, exist_ok=True)
            for item in items:
                item_dst = comp_dst / item.name
                if item_dst.is_symlink():
                    item_dst.unlink()
                shutil.copy(item, item_dst)
        # HIGH-1 fix (spec: symlink-single-source-install): stamp every
        # sibling too, not just the main family dir below — every prior
        # release stamped main only, so `create_family_links` (which
        # requires the stamp specifically before replacing a real directory
        # with a link) could never convert a fresh sibling either,
        # permanently duplicating it instead of linking it.
        sibling_version_file = sibling_dir / ".dummyindex_version"
        if sibling_version_file.is_symlink():
            sibling_version_file.unlink()
        sibling_version_file.write_text(PACKAGE_VERSION, encoding="utf-8")
        print(f"  {platform} skill installed  ->  {bl_dst}")

    version_file = skill_dir / ".dummyindex_version"
    if version_file.is_symlink():
        version_file.unlink()
    version_file.write_text(PACKAGE_VERSION, encoding="utf-8")
    print(f"  {platform} skill installed  ->  {dst}")
    print(
        f"  companions       ->  {sum(1 for _ in skill_dir.rglob('*.md')) - 1} markdown(s)"
    )


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
