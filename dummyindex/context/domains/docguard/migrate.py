"""Relocate stray planning docs out of ``docs/`` into their managed homes.

Capability 1 of the managed-doc-home feature: detect planning-doc markdown that
leaked under ``docs/`` and move each stray into ``.context/proposals/<slug>/``
(spec/plan) or ``.context/audits/<slug>/`` (report), preserving git history and
minting a valid ``proposal.json`` — codifying exactly the manual relocation that
commit ``0bd6d0b`` did by hand.

Three steps, deliberately separated so the CLI can preview before mutating:

- :func:`enumerate_strays` — walk the real filesystem under ``docs/`` for
  ``*.md``, skip **symlinked** strays, and group the rest via the pure
  classifier (``classify.group_strays``). Deterministic, sorted.
- :func:`plan_moves` — **whole-plan transactional pre-validation**: every slug
  valid and every source/target realpath-contained under ``docs/`` → ``.context/``.
  It raises (aborting the *entire* plan) before any move executes; a managed home
  that already exists is recorded as a skip (not a failure) unless ``--force``.
- :func:`apply_moves` — dry-run by default (``yes=False`` moves nothing). On
  ``yes=True``, per group it writes **only** ``proposal.json`` (terminal status
  ``done``, no template ``spec.md`` / ``plan.md`` / ``checklist.md`` to collide
  with the relocation) and relocates each stray. It branches on
  :func:`git.is_git_repo` **first**: a non-git tree moves every file with
  ``Path.replace`` and makes no git call; a tracked source uses ``git mv`` (history
  preserved); an untracked source in a real repo is ``Path.replace``'d then staged.

Containment, clobber-protection (``--force`` fills only *missing* files, never
overwriting a non-empty target), and the symlink skip mean one bad stray is
skipped + reported, never raised out of the batch, and nothing outside ``docs/``
is ever touched. No ``print`` here — the CLI owns stdout.
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

# How a migrated *audit* workspace is stamped. A relocated audit report is a
# finished artifact, so it lands on ``report.md``; the council never re-runs it,
# but ``ensure_audit`` requires a mode + model, so we stamp neutral defaults
# (the council mode/model only matter for a *live* panel, never a migrated one).
_MIGRATED_AUDIT_MODE = CouncilMode.STANDARD
_MIGRATED_AUDIT_MODEL = ModelChoice.SONNET_4_6

# How a relocation was executed (recorded on the applied ``MoveItem``).
_METHOD_GIT_MV = "git-mv"
_METHOD_REPLACE = "replace"
_METHOD_REPLACE_ADD = "replace+add"


def enumerate_strays(repo_root: Path, context_dir: Path) -> tuple[StrayGroup, ...]:
    """Group every placeable stray planning doc under ``docs/`` (sorted).

    Walks the real filesystem under ``<repo_root>/docs/`` for ``*.md`` files,
    **skipping symlinked strays** (``Path.is_symlink``) and never descending into
    symlinked directories, then hands the deterministic file list to the pure
    ``classify.group_strays`` (the classifier is lexical, so the filesystem walk
    is *our* job). ``context_dir`` is accepted for symmetry with the rest of the
    domain (the managed homes live under it) though grouping needs only the
    repo-relative shapes. Returns ``()`` when there is no ``docs/`` tree.
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

    Pass 1 validates **every** group — each slug through its kind's validator
    and each source/target through the realpath containment guard — and raises
    (``MigrationContainmentError`` / the typed slug error) on the first failure,
    aborting the entire plan *before* :func:`apply_moves` can move anything. Pass
    2 builds a :class:`PlannedGroup` per group, recording a :class:`MoveSkip`
    (rather than planning a move) for a managed home that already exists unless
    ``force`` is set. Reads each group's title from its primary source's H1.
    """
    repo_root = Path(repo_root)
    context_dir = Path(context_dir)
    docs_root = repo_root / DOCS_DIR_NAME

    # --- pass 1: whole-plan validation (raise before any move executes) ------
    for group in groups:
        _validate_group_slug(group)
        for source_rel, target_rel in _moves_for(group):
            _assert_within(repo_root / source_rel, docs_root, source_rel)
            _assert_within(repo_root / target_rel, context_dir, target_rel)

    # --- pass 2: build planned groups + report existing-home skips -----------
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

    Dry-run by default: with ``yes=False`` nothing is touched and the planned
    skips are echoed back for the CLI to print. With ``yes=True``, per group the
    managed head is materialised — ``proposal.json`` (terminal status ``done``,
    written **only** when missing so ``--force`` never clobbers a non-empty one)
    for a proposal, or an ``ensure_audit`` workspace for an audit — then each
    stray is relocated, **never overwriting a present (non-empty) target**. The
    relocation branches on :func:`git.is_git_repo` first (the seam contract): a
    non-git tree uses ``Path.replace`` with no git call, a tracked source uses
    ``git mv``, an untracked source is replaced then staged.
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


# ----- managed-home materialisation -----------------------------------------


def _ensure_head(context_dir: Path, home_abs: Path, group: PlannedGroup) -> None:
    """Write the managed head for a group, never clobbering an existing one.

    Proposal: write ``proposal.json`` (status ``done``) only when it is missing
    — fresh dirs get it, a ``--force`` fill writes it only if absent, an existing
    non-empty one is untouched. Audit: scaffold the workspace via
    ``ensure_audit`` only when the home does not yet exist (the stray report
    relocates onto ``report.md`` afterwards).
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

    Branches on ``git_repo`` **first** (the seam's documented non-git semantics):
    a non-git tree moves with ``Path.replace`` and issues no git call at all. In
    a real repo a tracked source uses ``git mv`` (preserving history); an
    untracked source is ``Path.replace``'d then ``git add``'d at the target. A
    ``git mv`` that unexpectedly refuses falls back to replace + add so the batch
    still completes.
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


# ----- planning helpers -----------------------------------------------------


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

    A local reimplementation of the realpath-containment pattern used by
    ``gc/delete.py`` — written here rather than imported so this feature keeps
    its zero cross-domain private-imports invariant. Both sides are
    ``resolve()``'d so a ``..`` segment or an escaping symlink is caught; a
    non-existent target tail resolves lexically (3.10 non-strict ``resolve``),
    which is fine for the containment question.
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
