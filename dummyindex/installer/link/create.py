"""The safe replacement dance: `create_family_links` and its per-family helpers.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Callable
from pathlib import Path, PurePath

from ..common import (
    _remove_owned_tree_no_follow,
    is_owned_copy,
    skills_root_rel,
)
from .classify import (
    _parent_chain_clean,
    _readlink_parts,
    _resolves_to_target,
    classify_family_link,
    relative_link_value,
)
from .families import (
    _CAPABILITY_HINT,
    _MAIN_FAMILY,
    _TMP_LINK_SUFFIX,
    _TMP_OLD_SUFFIX,
    _dotfiles_hint,
    _family_names,
)
from .models import FamilyLinkState, LinkResult, _CapabilityFailure, _FamilyOutcome

# --- creation: the safe replacement dance


def _silently_remove(path: Path) -> None:
    """Best-effort unlink of a disposable path of ours (temp link, probe).

    Never recurses: being a directory is not ownership evidence. Callers pass our
    own temp symlink or a family path our symlink was just promoted into; a
    directory squatting a disposable name is reported, never destroyed. Only
    `_remove_owned_tree_no_follow` (gated on `family_is_pristine`) deletes a real
    tree. Swallows `OSError`: cleanup is never a required step.
    """
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
    except OSError:
        pass


def _is_canonical_relative_link(family_dir: Path, family: str) -> bool:
    try:
        raw = os.readlink(family_dir)
    except OSError:
        return False
    return _readlink_parts(raw) == PurePath(relative_link_value(family)).parts


def _agents_family_target_is_dir(scope_root: Path, family: str) -> bool:
    """Whether ``.agents/skills/<family>`` is a real directory (lstat, no follow).

    Precondition for creating or healing any link: the post-create
    `_resolves_to_target` check is purely lexical, so without this a missing
    ``.agents`` tree would yield dangling links reported as ``created``. A symlink
    squatting the family name does not count.
    """
    try:
        target_stat = (scope_root / skills_root_rel("codex") / family).lstat()
    except OSError:
        return False
    return stat.S_ISDIR(target_stat.st_mode)


def _recover_leftover_temp_artifacts(
    family_dir: Path,
    tmp_link: Path,
    tmp_old: Path,
    scope_root: Path,
    family: str,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> str:
    """Undo an interrupted replacement dance for one family.

    Callers must pass `_parent_chain_clean` first: this renames and may delete a tree.
    A temp link is always discarded. ``tmp_old`` returns to an empty ``family_dir``
    only if `is_owned_copy` proves it ours (holding the temp name is no proof), and is
    deleted only if ``family_dir`` is `OURS_HEALTHY` and it is still provably ours.
    Returns a detail naming a surviving ``tmp_old`` for the outcome, else ``""``.
    """
    if tmp_link.is_symlink() or tmp_link.exists():
        _silently_remove(tmp_link)

    if not (tmp_old.exists() or tmp_old.is_symlink()):
        return ""

    occupied = family_dir.exists() or family_dir.is_symlink()
    if not occupied:
        if not is_owned_copy(tmp_old):
            # Never relocate an unproven dir that merely squats our temp name.
            return (
                f"{tmp_old} occupies this family's reserved temp-old name "
                "but carries no dummyindex ownership evidence — left in "
                f"place, NOT moved into {family_dir}"
            )
        try:
            tmp_old.rename(family_dir)
        except OSError as exc:
            return f"{tmp_old} could not be restored to {family_dir}: {exc}"
        return ""

    classification = classify_family_link(
        family_dir, scope_root, allowed_symlinks=allowed_symlinks
    )
    if classification.state is not FamilyLinkState.OURS_HEALTHY:
        # Not our healthy promotion: never touch the leftover on occupancy alone.
        return (
            f"{tmp_old} is a leftover from an earlier run; {family_dir} is "
            "not (yet) a healthy dummyindex link — left in place, not touched"
        )

    if not is_owned_copy(tmp_old):
        # An earlier partial delete may have destroyed the stamp/SKILL.md: maybe
        # ours, but no longer provably, and the security model never deletes on a
        # heuristic. Surface it on every run, even when family_dir is healthy.
        return (
            f"{tmp_old} survives from an earlier run and no longer carries "
            "dummyindex ownership evidence (an earlier delete likely failed "
            "partway through and destroyed its .dummyindex_version/SKILL.md "
            "first) — left in place; inspect and remove it manually"
        )

    try:
        _remove_owned_tree_no_follow(tmp_old)
    except OSError as exc:
        return f"{tmp_old} could not be fully removed ({exc}) — left in place"
    return ""


def _restore_renamed_aside(tmp_old: Path, family_dir: Path) -> str:
    """Best-effort restore of the rename-aside tree back to ``family_dir``.

    On failure returns a detail suffix naming the stranded path: if promote and
    restore both fail, ``tmp_old`` is the user's only real copy and must never go
    unreported.
    """
    try:
        tmp_old.rename(family_dir)
    except OSError as restore_exc:
        return (
            f"; additionally, restoring the original copy to {family_dir} "
            f"also failed ({restore_exc}) — the only remaining real copy "
            f"is stranded at {tmp_old}, do not delete it"
        )
    return ""


def _is_capability_error(exc: OSError) -> bool:
    """Whether ``exc`` looks like "this environment cannot create symlinks"
    (Windows without Developer Mode/admin, or a POSIX EPERM) rather than an
    ordinary, family-scoped filesystem failure."""
    return exc.errno == errno.EPERM or getattr(exc, "winerror", None) is not None


def _finish_simple_replace(
    family_dir: Path,
    tmp_link: Path,
    scope_root: Path,
    family: str,
    *,
    caveat: bool,
    kind: str,
) -> _FamilyOutcome:
    """Promote ``tmp_link`` over ``family_dir`` directly — no real tree to
    preserve (covers MISSING/DANGLING-heal/MATERIALIZED-replace/normalize)."""
    try:
        os.replace(tmp_link, family_dir)
    except OSError as exc:
        _silently_remove(tmp_link)
        return _FamilyOutcome("error", f"could not promote link into place: {exc}")
    ok, detail = _resolves_to_target(family_dir, scope_root, family)
    if not ok:
        _silently_remove(family_dir)
        return _FamilyOutcome("error", f"{detail}{_dotfiles_hint(scope_root)}")
    if caveat:
        # Printed only now that the promotion is known to have succeeded —
        # never before an operation whose success is still unknown.
        print("  pristine installed files replaced by one shared skill reference")
    return _FamilyOutcome(kind)


def _finish_replace_real(
    family_dir: Path,
    tmp_link: Path,
    tmp_old: Path,
    scope_root: Path,
    family: str,
) -> _FamilyOutcome:
    """Rename the proven real tree aside, re-verify, promote, delete last."""
    try:
        family_dir.rename(tmp_old)
    except OSError as exc:
        _silently_remove(tmp_link)
        return _FamilyOutcome("error", f"could not rename aside for replace: {exc}")

    from ..ownership import family_is_pristine

    if not family_is_pristine(tmp_old, family=family):
        # Recheck the same byte-level proof after rename, using the original name.
        restore_note = _restore_renamed_aside(tmp_old, family_dir)
        _silently_remove(tmp_link)
        return _FamilyOutcome(
            "error", f"ownership evidence vanished during rename{restore_note}"
        )

    try:
        os.replace(tmp_link, family_dir)
    except OSError as exc:
        restore_note = _restore_renamed_aside(tmp_old, family_dir)
        _silently_remove(tmp_link)
        return _FamilyOutcome(
            "error", f"could not promote link into place: {exc}{restore_note}"
        )

    ok, detail = _resolves_to_target(family_dir, scope_root, family)
    if not ok:
        _silently_remove(family_dir)
        restore_note = _restore_renamed_aside(tmp_old, family_dir)
        return _FamilyOutcome(
            "error", f"{detail}{_dotfiles_hint(scope_root)}{restore_note}"
        )

    # Printed only now that every step above is known to have succeeded.
    print("  pristine installed files replaced by one shared skill reference")
    try:
        _remove_owned_tree_no_follow(tmp_old)
    except OSError as exc:
        # The link landed and is verified; only cleanup of the old copy failed.
        # Report `replaced` (an error would claim the link never landed) plus a
        # warning naming the stranded tmp_old.
        return _FamilyOutcome(
            "replaced",
            warning=(
                f"the old copy renamed aside to {tmp_old} could not be "
                f"fully deleted after the link was promoted ({exc}) — the "
                "link itself is healthy; remove the stranded leftover "
                "manually (or fix the underlying issue, e.g. a permission "
                "error, and rerun)"
            ),
        )
    return _FamilyOutcome("replaced")


def _fold_recovery_detail(
    outcome: _FamilyOutcome, recovery_detail: str
) -> _FamilyOutcome:
    """Name a surviving `tmp_old` in the outcome on every run.

    Never overwrites a real kind (``created``/``replaced``/``skipped``/``error``):
    it gains the detail as a ``warning`` unless it has its own. ``noop`` records
    nothing, so it becomes ``skipped`` with the detail; otherwise a leftover
    would stay invisible behind a healthy link.
    """
    if not recovery_detail:
        return outcome
    if outcome.kind == "noop":
        return _FamilyOutcome("skipped", recovery_detail)
    if outcome.warning:
        return outcome  # already carries its own, more specific warning
    return _FamilyOutcome(outcome.kind, outcome.detail, warning=recovery_detail)


def _plan_and_execute_one_family(
    family_dir: Path,
    tmp_link: Path,
    tmp_old: Path,
    scope_root: Path,
    family: str,
    *,
    symlink_fn: Callable[..., None],
    allowed_symlinks: frozenset[Path] = frozenset(),
    _retry: bool = True,
) -> _FamilyOutcome:
    """Classify, plan, and execute one family's link — everything AFTER the
    parent-chain precondition and crash-recovery pass, which `_link_one_family`
    (the sole caller) has already run before this is ever reached."""
    if not _agents_family_target_is_dir(scope_root, family):
        return _FamilyOutcome("skipped", "no .agents family to link to")

    classification = classify_family_link(
        family_dir, scope_root, allowed_symlinks=allowed_symlinks
    )
    state = classification.state

    if state is FamilyLinkState.FOREIGN:
        return _FamilyOutcome("skipped", classification.detail)

    if state is FamilyLinkState.NOT_A_LINK:
        from ..ownership import family_is_pristine

        if not family_is_pristine(family_dir):
            return _FamilyOutcome(
                "skipped",
                f"preserving edited or unproven family {family_dir}; stamp alone is not ownership",
            )
        plan = "replace_real"
    elif state is FamilyLinkState.MATERIALIZED:
        plan = "replace_materialized"
    elif state is FamilyLinkState.MISSING:
        plan = "create"
    elif state is FamilyLinkState.OURS_DANGLING:
        plan = "replace_dangling"
    else:  # OURS_HEALTHY
        if _is_canonical_relative_link(family_dir, family):
            return _FamilyOutcome("noop")
        plan = "normalize"

    try:
        symlink_fn(
            str(Path(relative_link_value(family))), tmp_link, target_is_directory=True
        )
    except FileExistsError:
        if _retry:
            _silently_remove(tmp_link)
            return _link_one_family(
                family_dir,
                scope_root,
                family,
                symlink_fn=symlink_fn,
                allowed_symlinks=allowed_symlinks,
                _retry=False,
            )
        return _FamilyOutcome("error", "temp link path still exists after retry")
    except OSError as exc:
        if _is_capability_error(exc):
            raise _CapabilityFailure(str(exc)) from exc
        return _FamilyOutcome("error", str(exc))

    if plan == "replace_real":
        return _finish_replace_real(family_dir, tmp_link, tmp_old, scope_root, family)
    if plan == "replace_materialized":
        return _finish_simple_replace(
            family_dir, tmp_link, scope_root, family, caveat=True, kind="replaced"
        )
    if plan == "create":
        return _finish_simple_replace(
            family_dir, tmp_link, scope_root, family, caveat=False, kind="created"
        )
    # "replace_dangling" or "normalize" — a link already occupied the spot;
    # nothing real is at stake, so no hand-edits caveat.
    return _finish_simple_replace(
        family_dir, tmp_link, scope_root, family, caveat=False, kind="replaced"
    )


def _link_one_family(
    family_dir: Path,
    scope_root: Path,
    family: str,
    *,
    symlink_fn: Callable[..., None],
    allowed_symlinks: frozenset[Path] = frozenset(),
    _retry: bool = True,
) -> _FamilyOutcome:
    # PRECONDITION, checked first, before ANYTHING else touches this family
    # (including crash recovery below): a `.claude -> /victim` layout must
    # never let recovery/removal reach into the victim tree.
    unsafe_detail = _parent_chain_clean(
        scope_root, family_dir, allowed_symlinks=allowed_symlinks
    )
    if unsafe_detail is not None:
        return _FamilyOutcome("skipped", unsafe_detail)

    tmp_link = family_dir.parent / f".{family}{_TMP_LINK_SUFFIX}"
    tmp_old = family_dir.parent / f".{family}{_TMP_OLD_SUFFIX}"
    recovery_detail = _recover_leftover_temp_artifacts(
        family_dir,
        tmp_link,
        tmp_old,
        scope_root,
        family,
        allowed_symlinks=allowed_symlinks,
    )

    outcome = _plan_and_execute_one_family(
        family_dir,
        tmp_link,
        tmp_old,
        scope_root,
        family,
        symlink_fn=symlink_fn,
        allowed_symlinks=allowed_symlinks,
        _retry=_retry,
    )
    return _fold_recovery_detail(outcome, recovery_detail)


def create_family_links(
    scope_root: Path,
    *,
    symlink_fn: Callable[..., None] = os.symlink,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> LinkResult:
    """Create/heal/replace the Claude-side link for every family, in order.

    Per family: link at a sibling temp name first (probing capability before
    anything is destroyed), rename a proven real copy aside and re-verify it,
    promote the temp link, delete the renamed-aside tree last. ``symlink_fn`` is a
    plain parameter, never `Path.symlink_to` (which ignores a patched `os.symlink`
    on Python 3.10), so tests can inject a raising fake. ``allowed_symlinks``: fail
    closed, never derived from an environment variable (package invariant).

    Error isolation: a capability-shaped `OSError` (`EPERM`, Windows `winerror`)
    aborts the remaining families, keeps earlier links and names every uncovered
    family in ``errors``. Any other `OSError` fails only its own family; none escape.
    """
    families = _family_names()
    claude_skills_root = scope_root / skills_root_rel("claude")

    # The per-family parent-chain precondition, hoisted above `mkdir` so a
    # `.claude -> victim` layout never gets even a directory written in the
    # victim tree. Every family shares this parent, so a refusal here names
    # every family in `errors` and nothing is attempted.
    unsafe_detail = _parent_chain_clean(
        scope_root, claude_skills_root / _MAIN_FAMILY, allowed_symlinks=allowed_symlinks
    )
    if unsafe_detail is not None:
        errors = tuple(
            f"{family}: not attempted — {unsafe_detail}" for family in families
        )
        return LinkResult(created=(), replaced=(), skipped=(), errors=errors)

    try:
        claude_skills_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors = tuple(
            f"{family}: not attempted — could not create {claude_skills_root} ({exc})"
            for family in families
        )
        return LinkResult(created=(), replaced=(), skipped=(), errors=errors)

    created: list[str] = []
    replaced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for index, family in enumerate(families):
        family_dir = claude_skills_root / family
        try:
            outcome = _link_one_family(
                family_dir,
                scope_root,
                family,
                symlink_fn=symlink_fn,
                allowed_symlinks=allowed_symlinks,
            )
        except _CapabilityFailure as exc:
            errors.append(f"{family}: {exc} — {_CAPABILITY_HINT}")
            for uncovered in families[index + 1 :]:
                errors.append(
                    f"{uncovered}: not attempted — symlink capability failed "
                    "earlier this run"
                )
            break
        except OSError as exc:
            errors.append(
                f"{family}: unexpected error ({exc}) — continuing with remaining "
                "families"
            )
            continue

        if outcome.kind == "created":
            created.append(family)
        elif outcome.kind == "replaced":
            replaced.append(family)
        elif outcome.kind == "skipped":
            skipped.append(f"{family}: {outcome.detail}")
        elif outcome.kind == "error":
            errors.append(f"{family}: {outcome.detail}")
        # "noop" (already a canonical healthy link) -> nothing recorded.

        # A surviving `tmp_old` adds an extra `skipped` line whatever `kind`
        # was: success must never hide a stranded leftover.
        if outcome.warning:
            skipped.append(f"{family}: {outcome.warning}")

    return LinkResult(
        created=tuple(created),
        replaced=tuple(replaced),
        skipped=tuple(skipped),
        errors=tuple(errors),
    )
