"""Relocate stray planning docs out of ``docs/`` into their managed homes.

Strays move to ``.context/proposals/<slug>/`` (spec/plan) or ``.context/audits/<slug>/``
(report), preserving git history. Three steps so the CLI can preview before
mutating: :func:`enumerate_strays`, :func:`plan_moves` (raises before any move on a
slug/containment failure) and :func:`apply_moves` (dry-run unless ``yes=True``;
never overwrites a non-empty target). No ``print`` — the CLI owns stdout.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from ...git import is_git_repo, is_tracked, run_git
from ..audit.workspace import ensure_audit
from ..audit.workspace import validate_slug as validate_audit_slug
from ..config import CouncilMode, ModelChoice
from ..proposals.enums import ProposalStatus
from ..proposals.store import validate_slug as validate_proposal_slug
from ..proposals.store import write_proposal_json
from .classify import group_strays
from .constants import DOCS_DIR_NAME, MARKDOWN_SUFFIX
from .enums import DocKind
from .errors import MigrationContainmentError
from .models import MoveItem, MovePlan, MoveResult, MoveSkip, PlannedGroup, StrayGroup

# ``ensure_audit`` requires a mode + model, but a migrated report is finished and
# never re-run by the council, so these are neutral defaults.
_MIGRATED_AUDIT_MODE = CouncilMode.STANDARD
_MIGRATED_AUDIT_MODEL = ModelChoice.SONNET

# How a relocation was executed (recorded on the applied ``MoveItem``).
_METHOD_GIT_MV = "git-mv"
_METHOD_REPLACE = "replace"
_METHOD_REPLACE_ADD = "replace+add"


def enumerate_strays(repo_root: Path, context_dir: Path) -> tuple[StrayGroup, ...]:
    """Group every placeable stray planning doc under ``docs/`` (sorted).

    Walks ``<repo_root>/docs/`` for ``*.md`` (the classifier is lexical, so the
    walk is ours), **skipping symlinked strays** and never descending into
    symlinked dirs, then groups via ``classify.group_strays``. ``context_dir`` is
    unused, accepted for symmetry with the domain. ``()`` when there is no ``docs/``.
    """
    docs_root = Path(repo_root) / DOCS_DIR_NAME
    if not docs_root.is_dir():
        return ()

    paths: list[Path] = []
    # ``followlinks=False`` (the default) keeps us out of symlinked directories;
    # the per-file ``is_symlink`` check skips a symlinked stray file itself.
    for dirpath, _dirnames, filenames in os.walk(docs_root, followlinks=False):
        for name in filenames:
            if not name.lower().endswith(MARKDOWN_SUFFIX):
                continue
            candidate = Path(dirpath) / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            paths.append(candidate)

    return group_strays(repo_root, sorted(paths))


def plan_moves(
    repo_root: Path,
    context_dir: Path,
    groups: tuple[StrayGroup, ...],
    *,
    force: bool = False,
) -> MovePlan:
    """Pre-validate the whole batch and build the transactional move plan.

    Pass 1 validates **every** group's slug and realpath containment, raising
    ``MigrationContainmentError`` / the typed slug error on the first failure,
    before :func:`apply_moves` can move anything. Pass 2 builds a
    :class:`PlannedGroup` per group (title from its primary source's H1), or a
    :class:`MoveSkip` for an already-existing managed home unless ``force``.
    """
    repo_root = Path(repo_root)
    context_dir = Path(context_dir)
    docs_root = repo_root / DOCS_DIR_NAME

    # --- pass 1: whole-plan validation (raise before any move executes)
    for group in groups:
        _validate_group_slug(group)
        for source_rel, target_rel in _moves_for(group):
            _assert_within(repo_root / source_rel, docs_root, source_rel)
            _assert_within(repo_root / target_rel, context_dir, target_rel)

    # --- pass 2: build planned groups + report existing-home skips
    planned: list[PlannedGroup] = []
    skipped: list[MoveSkip] = []
    for group in groups:
        home_abs = repo_root / group.suggested_home
        if home_abs.exists() and not force:
            skipped.append(
                MoveSkip(
                    slug=group.slug,
                    kind=group.kind,
                    target_rel=group.suggested_home,
                    reason="managed home already exists; pass --force to fill missing files",
                )
            )
            continue
        title = _read_title(repo_root, group)
        moves = tuple(
            MoveItem(
                slug=group.slug,
                kind=group.kind,
                source_rel=source_rel,
                target_rel=target_rel,
            )
            for source_rel, target_rel in _moves_for(group)
        )
        planned.append(
            PlannedGroup(
                slug=group.slug,
                kind=group.kind,
                home_rel=group.suggested_home,
                title=title,
                moves=moves,
            )
        )

    return MovePlan(
        repo_root=repo_root,
        context_dir=context_dir,
        groups=tuple(planned),
        skipped=tuple(skipped),
    )


def apply_moves(
    plan: MovePlan, *, yes: bool = False, force: bool = False
) -> MoveResult:
    """Execute the plan (``yes=True``) or preview it (``yes=False``, moves nothing).

    A dry run echoes the planned skips back. Otherwise, per group, the managed head
    is written (:func:`_ensure_head`), then each stray is relocated by
    :func:`_relocate`, **never overwriting a non-empty target** (``--force`` only
    fills missing files). A missing source is skipped and reported, never raised.
    """
    if not yes:
        return MoveResult(moved=(), skipped=plan.skipped, dry_run=True)

    repo_root = plan.repo_root
    context_dir = plan.context_dir
    # Branch on git presence ONCE, up front: the whole batch shares one answer.
    git_repo = is_git_repo(repo_root)

    moved: list[MoveItem] = []
    skipped: list[MoveSkip] = list(plan.skipped)

    for group in plan.groups:
        home_abs = repo_root / group.home_rel
        _ensure_head(context_dir, home_abs, group)
        for item in group.moves:
            src = repo_root / item.source_rel
            dst = repo_root / item.target_rel
            if _is_present(dst):
                # Clobber-protection: a non-empty target is never overwritten,
                # so ``--force`` only ever *fills* missing files.
                reason = (
                    "target already present; --force fills missing files only"
                    if force
                    else "target already present; left byte-identical"
                )
                skipped.append(
                    MoveSkip(
                        slug=group.slug,
                        kind=group.kind,
                        target_rel=item.target_rel,
                        reason=reason,
                    )
                )
                continue
            if not src.is_file():
                # Source vanished / not a regular file — skip, never raise.
                skipped.append(
                    MoveSkip(
                        slug=group.slug,
                        kind=group.kind,
                        target_rel=item.source_rel,
                        reason="source is missing or not a regular file",
                    )
                )
                continue
            method = _relocate(repo_root, src, dst, git_repo=git_repo)
            moved.append(dataclasses.replace(item, method=method))

    return MoveResult(moved=tuple(moved), skipped=tuple(skipped), dry_run=False)


# --- managed-home materialisation


def _ensure_head(context_dir: Path, home_abs: Path, group: PlannedGroup) -> None:
    """Write the managed head for a group, never clobbering an existing one.

    Proposal: write only ``proposal.json`` (status ``done``; no template spec/plan
    to collide with the relocation), and only when missing or empty. Audit:
    scaffold via ``ensure_audit`` only when the home does not exist yet (the stray
    report relocates onto ``report.md`` afterwards).
    """
    if group.kind is DocKind.AUDIT:
        if not home_abs.exists():
            ensure_audit(
                context_dir,
                description=group.title,
                mode=_MIGRATED_AUDIT_MODE,
                model=_MIGRATED_AUDIT_MODEL,
                slug=group.slug,
                roster=None,
            )
        return
    if not _is_present(home_abs / "proposal.json"):
        write_proposal_json(
            context_dir, group.slug, group.title, status=ProposalStatus.DONE
        )


def _relocate(repo_root: Path, src: Path, dst: Path, *, git_repo: bool) -> str:
    """Move ``src`` to ``dst``, picking the mechanism by git status.

    Non-git tree: ``Path.replace`` and no git call at all. Tracked source:
    ``git mv`` (history preserved). Untracked source: ``Path.replace`` then
    ``git add``. A ``git mv`` that unexpectedly refuses falls back to replace + add.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not git_repo:
        src.replace(dst)
        return _METHOD_REPLACE
    if is_tracked(repo_root, src):
        completed = run_git(repo_root, "mv", str(src), str(dst))
        if completed.returncode == 0:
            return _METHOD_GIT_MV
        # Unexpected refusal — fall back so a single hiccup never wedges the run.
        src.replace(dst)
        run_git(repo_root, "add", str(dst))
        return _METHOD_REPLACE_ADD
    src.replace(dst)
    run_git(repo_root, "add", str(dst))
    return _METHOD_REPLACE_ADD


# --- planning helpers


def _moves_for(group: StrayGroup) -> tuple[tuple[str, str], ...]:
    """The ``(source_rel, target_rel)`` relocations a group implies.

    Proposal: the ``-design`` spec member → ``spec.md`` and the plain plan member
    → ``plan.md``. Audit: the report content lands on ``report.md`` (the plan
    member if present, else a lone spec member); a paired audit's extra spec
    member is preserved at ``spec.md`` so no data is dropped.
    """
    home = group.suggested_home
    if group.kind is DocKind.AUDIT:
        moves: list[tuple[str, str]] = []
        if group.plan_path:
            moves.append((group.plan_path, f"{home}/report.md"))
        if group.spec_path:
            target = "spec.md" if group.plan_path else "report.md"
            moves.append((group.spec_path, f"{home}/{target}"))
        return tuple(moves)

    moves = []
    if group.spec_path:
        moves.append((group.spec_path, f"{home}/spec.md"))
    if group.plan_path:
        moves.append((group.plan_path, f"{home}/plan.md"))
    return tuple(moves)


def _validate_group_slug(group: StrayGroup) -> None:
    """Run the group's kind-specific slug validator (raises on an unsafe slug)."""
    if group.kind is DocKind.AUDIT:
        validate_audit_slug(group.slug)
    else:
        validate_proposal_slug(group.slug)


def _assert_within(path: Path, root: Path, rel: str) -> None:
    """Raise ``MigrationContainmentError`` if ``path`` escapes ``root`` (realpath)."""
    if not _is_within(path, root):
        raise MigrationContainmentError(rel, str(root))


def _is_within(path: Path, root: Path) -> bool:
    """Whether ``path`` resolves to inside ``root`` (symlinks followed).

    Reimplements ``gc/delete.py``'s realpath containment rather than importing it,
    keeping this feature's zero cross-domain private-imports invariant. A missing
    target tail resolves lexically (3.10 non-strict ``resolve``), which suffices.
    """
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _is_present(path: Path) -> bool:
    """Whether ``path`` is an existing **non-empty** regular file.

    The clobber-protection predicate: an empty (0-byte) placeholder may be
    filled, but a non-empty ``spec.md`` / ``plan.md`` / ``proposal.json`` is
    never overwritten.
    """
    return path.is_file() and path.stat().st_size > 0


def _read_title(repo_root: Path, group: StrayGroup) -> str:
    """Title from the primary source's first H1, falling back to the base slug.

    The primary source is the spec member if present, else the plan member.
    Scans for the first ATX ``# `` heading; an unreadable file or a doc with no
    H1 yields the deterministic ``group.base_slug`` fallback (always non-empty).
    """
    source_rel = group.spec_path or group.plan_path
    fallback = group.base_slug
    if source_rel is None:
        return fallback
    try:
        text = (repo_root / source_rel).read_text(encoding="utf-8")
    except OSError:
        return fallback
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if title:
                return title
    return fallback
