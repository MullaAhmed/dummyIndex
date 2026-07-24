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
    """Whether EVERY one of the 8 enumerated Claude-side family slots (main +
    `_SIBLING_SKILLS`, never a glob) is entirely absent — a genuinely blank
    slate, matching the bug's own reproduction (a fresh install with nothing
    pre-existing on the Claude side at all).

    Gates how narrowly the direct-write loop's MISSING-state deferral
    applies: skipping the whole `_install_skill_family` call is only safe
    when nothing would be lost by skipping it. If even one sibling already
    has a real (possibly unproven) directory — e.g. an old <=0.25.0 partial
    install with a stale `templates/*.tmpl` twin — that existing content
    still needs `_install_skill_family`'s own repair/purge pass, so a mixed
    state keeps today's unconditional-write behavior exactly as it was
    before this fix.
    """
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
    """Mint ``.dummyindex_version`` on every sibling REAL directory whose
    family main dir already carries a stamp of its own, for one host tree.

    Root cause (HIGH-1, spec: symlink-single-source-install): every prior
    release's `_install_skill_family` stamped the MAIN family dir only — the
    7 `_SIBLING_SKILLS` real directories shipped unstamped, on both hosts.
    `create_family_links`'s replace-a-real-directory plan requires the
    STAMP specifically (`_has_version_stamp`, stricter than `is_owned_copy`)
    before it will convert a real directory into a link, so migrating a
    realistic pre-existing install (main stamped, every sibling real and
    unstamped) converted only the main family and left every sibling
    duplicated permanently. Called once per selected host tree, after
    `execute_repairs` and immediately before the link dispatch
    (`run_link_install`), so a repo carrying this shape heals itself on the
    very next flagless install — main + siblings alike become eligible for
    `create_family_links`'s replace-a-real-directory plan on the Claude
    side, and the `.agents`-side sibling targets gain the ownership
    evidence `classify_family_link`'s OURS_HEALTHY already requires.

    A sibling is minted a stamp only when ALL of:
    - the host's MAIN family dir carries a non-empty `.dummyindex_version`
      stamp (`_read_stamp`, the STAMP specifically, never the weaker legacy
      heading — minting new evidence requires the same strength
      `_has_version_stamp` itself demands before destroying a real
      directory);
    - the sibling path is a REAL directory by `lstat` (never a symlink —
      already converted, or foreign, either way never written through or
      followed);
    - it carries no `.dummyindex_version` of its own yet (never overwrites
      an existing stamp);
    - its parent chain is clean under ``allowed_symlinks`` (the identical
      parent-chain safety every other write path in this module already
      applies — never mint a stamp through a symlinked
      `.claude`/`.claude/skills` or the equivalent host root).

    The minted VALUE is the MAIN's own stamp value, never `PACKAGE_VERSION`
    — the sibling content already on disk is whatever version the main's
    run actually wrote, so the main's value is the only honest one to
    assert for it. Enumerates strictly from `_SIBLING_SKILLS` (never a
    `dummyindex*` glob, which would also catch the equip-generated
    `dummyindex-verify` skill — not part of this family).
    """
    main_dir = (base / skill_rel(host)).parent
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

    `create_family_links` is the only place that heals either state (dispatched
    after `execute_repairs`, under AUTO/LINK); under `--copy` nothing heals
    them this run, so this line is the entire user-facing signal — never the
    `mkdir(exist_ok=True)` crash this task fixes, always a named remediation.
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

    Used only by the ``--platform claude`` narrowing (``codex`` not
    selected): `plan_repairs`/`execute_repairs` never freshen an
    out-of-scope `.agents` copy this run, so the link dispatch must
    independently know whether that copy is provably current before linking
    onto it. Delegates the parse+compare step to `common.py`'s
    `_compare_stamp` — the same comparator `repair.py` uses for its own
    staleness check — rather than duplicating the ordering logic locally;
    only the "missing" (no stamp file at all) state is decided here, since
    `_compare_stamp` itself only distinguishes older/equal/newer/unknown.
    """
    stamp = _read_stamp(base / skills_root_rel("codex") / family / _VERSION_STAMP_NAME)
    if stamp is None:
        return "missing"
    return _compare_stamp(stamp, PACKAGE_VERSION)


def _claude_narrowing_link_gate(
    base: Path, *, link_mode: LinkMode, force_downgrade: bool
) -> bool:
    """Whether ``--platform claude`` (agents not selected) may link this run.

    Returns ``True`` when linking may proceed as requested. Under strict
    `LinkMode.LINK`, a refusal prints the CLI-facing message and exits 1
    directly — this function owns both the gate and its message, matching
    the strict-mode contract: "no `.agents` family to link to" names
    ``--platform both``; a newer/unknown stamp also names
    ``--force-downgrade``. Under `LinkMode.AUTO`, a refusal instead returns
    ``False`` so the caller falls back to copy mode for the Claude side only
    — exactly today's `--platform claude` behavior, never a hard failure.
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

    ``created`` families had nothing real to convert (a fresh link).
    ``replaced`` families print the acceptance criterion's "migrated ->"
    line — whether the prior state was a proven real copy (the forced-
    migration case), a dangling link, a materialized placeholder, or an
    absolute-but-correct link being normalized, they are all now the
    canonical relative link, so one consistent label covers every case
    `LinkResult.replaced` bundles together (its own docstring: "bare family
    names, ready to print").
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
