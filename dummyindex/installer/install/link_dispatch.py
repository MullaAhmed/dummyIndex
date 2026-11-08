"""Link-mode dispatch helpers: the AUTO/LINK/COPY decision support `install()`
calls into, plus the transcript lines it prints for that dispatch.

See the package docstring (``install/__init__.py``) for the split rationale.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

from ..common import (
    _SIBLING_SKILLS,
    _VERSION_STAMP_NAME,
    PACKAGE_VERSION,
    LinkMode,
    _compare_stamp,
    _first_symlink_component,
    _read_stamp,
    skill_rel,
    skills_root_rel,
)
from ..link import FamilyLinkClassification, FamilyLinkState, LinkInstallResult


def _all_claude_families_missing(base: Path) -> bool:
    """Whether no Claude-side family slot (main + `_SIBLING_SKILLS`, never a
    glob) exists, not even as a dangling symlink."""
    claude_skills_root = base / skills_root_rel("claude")
    family_names = ("dummyindex", *(label for _sub_name, label in _SIBLING_SKILLS))
    return all(
        not (claude_skills_root / name).is_symlink()
        and not (claude_skills_root / name).exists()
        for name in family_names
    )


def _backfill_sibling_stamps(
    base: Path, host: str, *, allowed_symlinks: frozenset[Path] = frozenset()
) -> None:
    """Fill missing sibling version hints only when per-file ownership is proven.

    Retained for compatibility callers. The main stamp supplies the version;
    byte-level proof and the existing parent-chain guard authorize each write.
    """
    main_dir = (base / skill_rel(host)).parent
    from ..ownership import family_is_pristine

    stamp_value = _read_stamp(main_dir / _VERSION_STAMP_NAME)
    if not stamp_value:
        return
    skills_root = base / skills_root_rel(host)
    for _sub_name, label in _SIBLING_SKILLS:
        sibling_dir = skills_root / label
        try:
            sibling_stat = sibling_dir.lstat()
        except OSError:
            continue
        if not stat.S_ISDIR(sibling_stat.st_mode):
            continue
        if _read_stamp(sibling_dir / _VERSION_STAMP_NAME) is not None:
            continue
        if (
            _first_symlink_component(
                base, sibling_dir, allowed_symlinks=allowed_symlinks
            )
            is not None
        ):
            continue
        if not family_is_pristine(sibling_dir):
            continue
        try:
            (sibling_dir / _VERSION_STAMP_NAME).write_text(
                stamp_value, encoding="utf-8"
            )
        except OSError:
            continue


def _link_state_report_line(
    classification: FamilyLinkClassification, *, base: Path, scope: str
) -> str:
    """The --copy-mode report line for a family stuck OURS_DANGLING/MATERIALIZED.

    Only `create_family_links` (AUTO/LINK) heals either state, so under
    ``--copy`` this line, with a named remediation, is the only signal.
    """
    scope_flag = (
        f"--scope project --dir {base}" if scope == "project" else "--scope user"
    )
    fix = (
        f"dummyindex install {scope_flag} (without --copy) to relink, or "
        "`git config core.symlinks true` and re-checkout"
    )
    if classification.state is FamilyLinkState.MATERIALIZED:
        kind = (
            "a materialized link placeholder (a core.symlinks=false checkout "
            "wrote the link's target text as a regular file)"
        )
    else:
        kind = (
            "a dangling dummyindex-owned symlink (its .agents/skills target is missing)"
        )
    return (
        f"  claude family    ->  {classification.family}: {classification.path} "
        f"is {kind} — fix with: {fix}"
    )


def _agents_family_stamp_state(base: Path, family: str = "dummyindex") -> str:
    """ "missing" | "older" | "equal" | "newer" | "unknown" for the main
    ``.agents/skills/<family>`` version stamp vs the installed package.

    For the ``--platform claude`` narrowing: repair never freshens an
    out-of-scope ``.agents`` copy, so linking onto it first needs proof that it
    is current. Only "missing" is decided here; the rest is `_compare_stamp`.
    """
    stamp = _read_stamp(base / skills_root_rel("codex") / family / _VERSION_STAMP_NAME)
    if stamp is None:
        return "missing"
    return _compare_stamp(stamp, PACKAGE_VERSION)


def _claude_narrowing_link_gate(
    base: Path, *, link_mode: LinkMode, force_downgrade: bool
) -> bool:
    """Whether ``--platform claude`` (agents not selected) may link this run.

    Returns ``True`` when linking may proceed. Under strict `LinkMode.LINK` a
    refusal prints the CLI message and exits 1: a missing ``.agents`` family
    names ``--platform both``; an older, newer or unknown stamp also names
    ``--force-downgrade``. Under any other mode a refusal returns ``False``.
    """
    stamp_state = _agents_family_stamp_state(base)
    if stamp_state == "equal":
        return True
    if stamp_state != "missing" and force_downgrade:
        return True
    if link_mode is LinkMode.LINK:
        if stamp_state == "missing":
            print(
                "error: --link --platform claude has no .agents family to "
                f"link to at {base} — pass --platform both to write one "
                "this run",
                file=sys.stderr,
            )
        else:
            print(
                "error: --link --platform claude found an .agents family at "
                f"{base} whose stamp is {stamp_state} relative to this "
                "installed package — pass --force-downgrade to link anyway, "
                "or --platform both to refresh it first",
                file=sys.stderr,
            )
        sys.exit(1)
    return False


def _print_link_install_result(base: Path, result: LinkInstallResult) -> None:
    """Print one line per family outcome from a `run_link_install` dispatch.

    ``created`` families print "linked". ``replaced`` families (a proven real
    copy, a dangling link, a materialized placeholder or a normalized link) are
    all now the canonical relative link, so one "migrated" label covers them.
    """
    for warning in result.warnings:
        print(f"  {warning}", file=sys.stderr)
    link_result = result.link_result
    if link_result is None:
        return
    claude_skills_root = base / skills_root_rel("claude")
    for family in link_result.created:
        print(f"  claude skill linked    ->  {claude_skills_root / family}")
    for family in link_result.replaced:
        print(f"  claude skill migrated  ->  {claude_skills_root / family}")
    for skipped_line in link_result.skipped:
        print(f"  link report      ->  {skipped_line}")
    for error_line in link_result.errors:
        print(f"  link error       ->  {error_line}", file=sys.stderr)
