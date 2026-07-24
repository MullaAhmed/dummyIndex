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
    _VERSION_STAMP_NAME,
    _read_stamp,
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

# ----- creation: the safe replacement dance -------------------------------------


def _silently_remove(path: Path) -> None:
    """Remove a disposable path of ours (temp link, probe) — UNLINK ONLY.

    Never recurses into a directory: `path.is_dir()` alone is not ownership
    evidence, only "is a directory". Every caller of this function passes it
    either our own just-created temp symlink, or the family path
    immediately after `os.replace` promoted our own symlink into it (so it
    is a symlink at that point too, never a real tree). A directory
    squatting one of our disposable names (a temp-link or probe path) is
    reported by the caller, never destroyed here — see
    `_remove_owned_tree_no_follow` (gated on `is_owned_copy`, `common.py`)
    for the one place in this module that is allowed to delete a real tree.

    Best-effort: swallows `OSError` because every caller treats this as
    "clean up if possible", never as a required step.
    """
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
    except OSError:
        pass


def _has_version_stamp(path: Path) -> bool:
    """Whether ``path`` carries the ``.dummyindex_version`` stamp specifically.

    Stricter than `is_owned_copy` (which also accepts the legacy heading
    alone) — replacing a REAL directory with a link requires the stronger
    stamp evidence; a heading-only copy is reported, never destroyed.
    """
    return _read_stamp(path / _VERSION_STAMP_NAME) is not None


def _is_canonical_relative_link(family_dir: Path, family: str) -> bool:
    try:
        raw = os.readlink(family_dir)
    except OSError:
        return False
    return _readlink_parts(raw) == PurePath(relative_link_value(family)).parts


def _agents_family_target_is_dir(scope_root: Path, family: str) -> bool:
    """Whether ``.agents/skills/<family>`` exists as a REAL directory (lstat,
    no follow) — the precondition for creating or healing any link.

    `_resolves_to_target`'s post-create check is purely lexical
    (`resolve(strict=False)`), so without this precondition
    `create_family_links` would happily report ``created`` for a fully
    dangling link whenever ``.agents`` is absent (e.g. a failed ``.agents``
    write earlier in the same run) — every link would dangle and the run
    would still look like a success. A symlink squatting the family name is
    not a real directory either.
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
    """Undo an interrupted safe-replacement dance for one family, deterministically.

    **Callers must run `_parent_chain_clean` and refuse to call this at all
    when it is unsafe** — this function performs renames and (conditionally)
    a recursive delete, and must never be reached through a symlinked
    ``.claude``/``.claude/skills``.

    Our own disposable temp names never carry meaning across runs: an
    unpromoted temp link is always discarded. A leftover renamed-aside real
    tree is never destroyed by a heuristic — when ``family_dir`` is empty
    (the rename-aside completed but nothing was ever promoted into its
    place, or the promotion itself was interrupted) it is moved straight
    back, so the normal classify-driven flow below redoes the dance from
    scratch on a clean, familiar starting state — but ONLY when ``tmp_old``
    itself carries ownership evidence (NEW-4): mere occupancy of the
    disposable temp NAME is not proof it is ours, so a foreign directory
    squatting it is never silently relocated into ``family_dir``. When
    ``family_dir`` is already occupied, mere occupancy is likewise a
    heuristic, not evidence — the leftover is only ever finish-deleted when
    ``family_dir`` itself classifies `FamilyLinkState.OURS_HEALTHY` (this
    run's own promotion is what occupies it now) AND the leftover is still
    provably ours. A foreign symlink or an unrelated real directory
    squatting the family path must never trigger a delete.

    Returns a non-empty, human-readable detail string naming ``tmp_old``
    whenever it SURVIVES this call — restore failed, finish-delete failed or
    was refused, or the leftover was never provably ours to touch at all
    (NEW-1). Callers must fold this into the reported outcome: a run that
    would otherwise report nothing (an already-healthy link's ``noop``) must
    never look silently clean while a stranded leftover sits on disk — see
    `_link_one_family`'s `_fold_recovery_detail`. Returns ``""`` when there
    is nothing left to report.
    """
    if tmp_link.is_symlink() or tmp_link.exists():
        _silently_remove(tmp_link)

    if not (tmp_old.exists() or tmp_old.is_symlink()):
        return ""

    occupied = family_dir.exists() or family_dir.is_symlink()
    if not occupied:
        if not is_owned_copy(tmp_old):
            # NEW-4: never relocate an unproven directory into family_dir
            # just because it happens to squat our own disposable temp
            # name — occupancy of the NAME is not ownership evidence.
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
        # Occupied by something other than our own healthy promotion —
        # never touch the leftover based on occupancy alone.
        return (
            f"{tmp_old} is a leftover from an earlier run; {family_dir} is "
            "not (yet) a healthy dummyindex link — left in place, not touched"
        )

    if not is_owned_copy(tmp_old):
        # NEW-1: a previous run's OWN finish-delete can fail partway
        # through and destroy the stamp/SKILL.md before the failure — this
        # leftover may well be ours, but it is no longer PROVABLY ours, and
        # the security model never force-deletes on a heuristic. It must
        # still be surfaced on every subsequent run rather than silently
        # ignored just because family_dir is already healthy.
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

    On failure, returns a non-empty, loud detail suffix naming the stranded
    path instead of silently swallowing the second failure — if both the
    promote AND the restore fail, ``tmp_old`` is the user's ONLY remaining
    real copy and that must never go unreported.
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
        print("  hand-edits to this installed copy are not preserved")
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

    if not _has_version_stamp(tmp_old):
        # Extremely defensive — we just proved this above — but never
        # destroy a tree whose ownership evidence vanished mid-rename. The
        # re-verify is the security-critical check, so it must be at least
        # as strict as the classify-time gate, never looser: stamp only,
        # not `is_owned_copy` (which also accepts the legacy heading alone).
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
    print("  hand-edits to this installed copy are not preserved")
    try:
        _remove_owned_tree_no_follow(tmp_old)
    except OSError as exc:
        # NEW-1: the conversion itself DID succeed — family_dir is already
        # a verified-healthy link — only cleanup of the old real copy
        # failed partway through. Report this as `replaced` (not `error`:
        # an error would wrongly suggest the link never landed) plus a
        # named warning for the stranded tmp_old, never an uncaught
        # exception silently miscounted by the caller.
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
    """Ensure a `tmp_old` that survived `_recover_leftover_temp_artifacts` is
    NAMED in the reported outcome on EVERY run (NEW-1) — even a run whose own
    outcome would otherwise report nothing at all (an already-healthy link's
    ``noop``), which is exactly how a partially-destroyed leftover used to go
    permanently invisible the moment `family_dir` itself looked healthy.

    Never overwrites a REAL operation's own kind: ``created``/``replaced``/
    ``skipped``/``error`` all keep reporting what they reported, gaining the
    leftover detail as an ADDITIONAL ``warning`` (`create_family_links`
    prints it as an extra `skipped` line alongside the primary bucket). Only
    ``noop`` — which otherwise records nothing at all — is promoted to
    ``skipped`` so the leftover has somewhere to be named.
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
        if not _has_version_stamp(family_dir):
            return _FamilyOutcome(
                "skipped",
                f"refusing to replace {family_dir}: no .dummyindex_version "
                "stamp (a legacy Codex heading alone is not enough evidence "
                "to replace a real directory with a link)",
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
        symlink_fn(relative_link_value(family), tmp_link, target_is_directory=True)
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

    Per family, the safe replacement dance: create the new link at a sibling
    temp name first (probing symlink capability before anything is
    destroyed), rename any proven real copy aside and re-verify it before
    promoting the temp link into place, then delete the renamed-aside tree
    last. See the module/proposal docs for the full per-state matrix.

    ``symlink_fn`` (default `os.symlink`) is called as a plain parameter —
    never `Path.symlink_to` — specifically so tests can inject a raising
    fake without monkeypatching `os.symlink` itself (`Path.symlink_to` does
    not route through the patched name on Python 3.10).

    ``allowed_symlinks`` is the fail-closed parent-chain allowlist forwarded
    to `classify_family_link` for every family — see its docstring. Defaults
    to the empty frozenset.

    Error isolation: a `FileExistsError` creating one family's temp link
    re-classifies and replaces-or-reports that family, then continues. An
    `OSError` shaped like a capability failure (`EPERM`, or a Windows
    `winerror`) aborts every *remaining* family — already-created/replaced
    links from earlier in this call stay, and every family left uncovered is
    named in ``errors``. Any OTHER unexpected `OSError` for one family
    (e.g. a permission error deleting a renamed-aside tree, or `.claude`
    hierarchy shaped as a file instead of a directory) is reported as an
    error for that family only — it never aborts the run or escapes this
    function, so the other families are always attempted (spec: "Error
    isolation per family").

    ``allowed_symlinks`` invariant (see the module docstring): every entry
    must be ``scope_root / ".claude"`` or ``scope_root / ".claude" / "skills"``
    — never derived from an environment variable.
    """
    families = _family_names()
    claude_skills_root = scope_root / skills_root_rel("claude")

    # NEW-2: the SAME parent-chain precondition every per-family write path
    # already runs, hoisted ABOVE `mkdir` — a `.claude -> victim` layout must
    # never cause even `mkdir` to write inside the victim tree. This check is
    # scope_root/family-independent (every family shares the identical
    # `claude_skills_root` parent), so failing here means every per-family
    # call would have refused identically; reported with the same
    # all-8-families `errors` shape the mkdir-failure branch below already
    # uses, and NOTHING is attempted.
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

        # NEW-1: a surviving leftover `tmp_old` rides along as an EXTRA
        # `skipped` line, whatever bucket `kind` itself landed in — a
        # successful `created`/`replaced` is not itself a failure, but the
        # stranded leftover must never go unreported just because the
        # primary operation succeeded (or needed nothing at all).
        if outcome.warning:
            skipped.append(f"{family}: {outcome.warning}")

    return LinkResult(
        created=tuple(created),
        replaced=tuple(replaced),
        skipped=tuple(skipped),
        errors=tuple(errors),
    )
