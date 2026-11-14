"""Bounded, guarded deletion of one generated-doc workspace (GC's only destructive op).

Removes exactly one ``.context/proposals/<slug>/`` or ``.context/audits/<slug>/``
dir; the ``/dummyindex-gc`` skill picks it and gets user confirmation. In order:

1. Slug validation: the kind's ``validate_slug`` rejects traversal before path work.
2. Sentinel reject: ``_archive``, leading ``_``, ``.``/``..``, empty. ``_archive``
   is charset-valid and inside the root, so only this guard stops it.
3. Realpath containment: the target, symlinks resolved, must stay in the kind-root.
4. Liveness (proposal kinds): in-flight work is refused unless ``force_partial``.
5. Recoverability: an untracked target is refused (returned, not raised) unless
   ``allow_untracked``, because its removal would be permanent.
6. Knowledge lifecycle: needs a current closeout receipt, intact units/fixtures and
   no inbound durable dependencies; neither flag bypasses it.

1. **Slug validation** — the kind's own ``validate_slug`` rejects an
   out-of-charset slug (``../../etc``) by raising ``ProposalSlugError`` /
   ``AuditSlugError`` *before any path work*. The caller maps these to exit 2.
2. **Sentinel reject** — a slug that is ``_archive``, leads with ``_``, is
   ``.``/``..``, or is empty raises ``GcTargetError``. ``_archive`` is
   charset-valid and resolves *inside* the root, so guard 3 cannot catch it —
   this guard is the only thing that does.
3. **Realpath containment** — the target dir is resolved (following symlinks)
   and must be inside the resolved kind-root, else ``GcPathError``. Reachable
   via a symlinked workspace or an explicit ``path=`` — never via a clean slug.
4. **Liveness** (proposals/archived only) — an ``in_progress`` proposal, or one
   whose checklist is partial, is refused with ``GcTargetError`` unless
   ``force_partial`` is given. A structural backstop against deleting a plan a
   ``/dummyindex-build`` is mid-flight on.
5. **Recoverability** — a git-untracked target is refused (returning a
   ``DeleteResult``, not raising) unless ``allow_untracked`` is also given,
   because its removal would be permanent.
6. **Knowledge lifecycle** — authored work needs a current closeout receipt,
   intact accepted units/fixtures and no inbound durable dependencies. Neither
   force_partial nor allow_untracked bypasses this guard.

A target that does not exist is an idempotent no-op (``deleted=False``,
``refused=False``), never an error. No ``print`` here — the CLI owns stdout.
This module never touches anything outside the resolved kind-root.
``dry_run=True`` runs the same guards without the lock and returns before ``rmtree``.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..audit.workspace import audits_root
from ..audit.workspace import validate_slug as validate_audit_slug
from ..equip.enums import EquipmentKind, EquipmentScope
from ..equip.errors import EquipError
from ..equip.generate.grounding import contained_path, grounding_path
from ..equip.lifecycle.manifest import read_manifest
from ..equip.lifecycle.remove import remove_item
from ..equip.lifecycle.status import classify_item, is_lifecycle_managed, is_user_owned
from ..equip.models import EquipmentItem, EquipmentManifest
from ..proposals.errors import CloseoutError
from ..proposals.retirement import retirement_block
from ..proposals.store import proposals_root
from ..proposals.store import validate_slug as validate_proposal_slug
from ..requirements.constants import CONFIG_TOML_REL
from ..requirements.enums import SkillOrigin
from ..requirements.errors import RequirementsError
from ..requirements.models import Requirements, SkillRequirement
from ..requirements.toml_io import read_requirements, write_requirements
from .constants import ARCHIVE_SENTINEL, PROPOSAL_KINDS
from .enums import CandidateKind
from .equipment import _refs_finished
from .errors import GcPathError, GcTargetError
from .liveness import _checklist_partial, _liveness_block, _proposal_status  # noqa: F401 — old names stay importable
from .models import DeleteResult


def delete_workspace(
    context_dir: Path,
    *,
    kind: CandidateKind,
    slug: str | None = None,
    path: str | None = None,
    allow_untracked: bool = False,
    force_partial: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> DeleteResult:
    """Hold the shared project writer lock across all guards and deletion.

    An active closeout, receipt or policy writer refuses deletion with a retry
    instruction. ``dry_run`` runs every guard, takes no lock, and deletes nothing.
    ``kind=EQUIPMENT`` routes to :func:`delete_equipment_item` (``force`` applies
    only there); workspace kinds never see ``force``.
    """
    from dummyindex.shared.errors import EvolveError
    from dummyindex.shared.guard import project_lock

    if kind is CandidateKind.EQUIPMENT:
        if slug is None or path is not None:
            raise GcTargetError(path or "", "equipment is deleted by --slug only")
        return delete_equipment_item(
            context_dir.parent, slug, force=force, dry_run=dry_run
        )
    if dry_run:
        return _delete_workspace_locked(
            context_dir,
            kind=kind,
            slug=slug,
            path=path,
            allow_untracked=allow_untracked,
            force_partial=force_partial,
            dry_run=True,
        )
    try:
        with project_lock(context_dir.parent):
            return _delete_workspace_locked(
                context_dir,
                kind=kind,
                slug=slug,
                path=path,
                allow_untracked=allow_untracked,
                force_partial=force_partial,
            )
    except EvolveError as exc:
        raise GcTargetError(slug or path or "", str(exc)) from exc


def _delete_workspace_locked(
    context_dir: Path,
    *,
    kind: CandidateKind,
    slug: str | None = None,
    path: str | None = None,
    allow_untracked: bool = False,
    force_partial: bool = False,
    dry_run: bool = False,
) -> DeleteResult:
    """Delete one generated-doc workspace dir behind the guards.

    Exactly one of ``slug`` / ``path`` identifies the target; ``path`` is the
    escape hatch the realpath guard hardens against. Returns a ``DeleteResult``
    (deleted / refused / no-op). Raises ``ProposalSlugError`` / ``AuditSlugError``
    (guard 1), ``GcPathError`` (guard 3) or ``GcTargetError`` (guards 2, 4, 6);
    the caller maps every one to exit 2.
    """
    root = _kind_root(context_dir, kind)

    # --- guard 1: slug validation (out-of-charset traversal)
    # Always run the validator when a slug is given — it raises the typed slug
    # error for ``../../etc`` before any path work. ``path=`` callers skip this
    # (no slug to validate); the realpath guard contains them instead.
    safe_slug = _validate(kind, slug) if slug is not None else None

    # --- guard 2: sentinel reject
    # ``_archive`` / leading-``_`` / ``.`` / ``..`` / empty are charset-valid
    # (or path-special) yet never deletable. Only meaningful for a slug target.
    if safe_slug is not None:
        _reject_sentinel(safe_slug)

    # Resolve the on-disk target. A ``path=`` target is taken verbatim; a slug
    # target is built from the *validated* slug under the kind-root.
    if path is not None:
        target = Path(path)
    elif safe_slug is not None:
        target = root / safe_slug
    else:
        raise GcTargetError("", "no target: pass slug or path")

    # --- guard 3: realpath containment
    # Resolve symlinks on both sides and assert the target stays inside the
    # resolved kind-root. A symlinked workspace / ``--path`` is the only way to
    # escape; a clean slug is charset-bounded and cannot.
    resolved_target = target.resolve()
    resolved_root = root.resolve()
    if not _is_relative_to(resolved_target, resolved_root):
        raise GcPathError(str(target), str(root))

    # --- missing dir: idempotent no-op (NOT an error)
    if not target.exists():
        return DeleteResult(
            deleted=False, refused=False, reason="nothing to delete", untracked=False
        )

    # --- guard 4: liveness (proposals/archived only) ------------------------
    if kind in PROPOSAL_KINDS and not force_partial:
        reason = _liveness_block(target)
        if reason is not None:
            raise GcTargetError(
                safe_slug or str(target),
                f"{reason}; pass force_partial",
            )

    # --- guard 5: recoverability (git-tracked vs untracked)
    tracked = _is_tracked(context_dir.parent, resolved_target)
    untracked = not tracked
    if untracked and not allow_untracked:
        return DeleteResult(
            deleted=False,
            refused=True,
            reason="unrecoverable: not tracked by git; pass allow_untracked",
            untracked=True,
        )

    try:
        reason = retirement_block(
            context_dir,
            resolved_target,
            kind="proposal" if kind in PROPOSAL_KINDS else "audit",
        )
    except (CloseoutError, OSError, ValueError) as exc:
        raise GcTargetError(safe_slug or str(target), str(exc)) from exc
    if reason:
        raise GcTargetError(safe_slug or str(target), reason)

    if dry_run:
        return DeleteResult(would_delete=True, untracked=untracked)

    # --- delete --------------------------------------------------------------
    shutil.rmtree(target)
    return DeleteResult(deleted=True, refused=False, reason=None, untracked=untracked)


# --- guard helpers


def _kind_root(context_dir: Path, kind: CandidateKind) -> Path:
    """``.context/proposals`` or ``.context/audits`` for the candidate kind."""
    if kind is CandidateKind.EQUIPMENT:
        # Equipment never has a workspace dir; an equipment slug must not reach audits/.
        raise GcTargetError("", "equipment has no workspace root")
    if kind in PROPOSAL_KINDS:
        return proposals_root(context_dir)
    return audits_root(context_dir)


def _validate(kind: CandidateKind, slug: str) -> str:
    """Run the kind's own slug validator (raises the typed slug error)."""
    if kind is CandidateKind.EQUIPMENT:
        raise GcTargetError(slug, "equipment has no workspace slug validator")
    if kind in PROPOSAL_KINDS:
        return validate_proposal_slug(slug)
    return validate_audit_slug(slug)


# --- equipment (contract 19): retire one generated agent/skill


_EQUIPMENT_KINDS = frozenset({EquipmentKind.AGENT, EquipmentKind.SKILL})


@dataclass(frozen=True)
class _EquipmentPlan:
    """Every fact the equipment delete needs, gathered before the first write."""

    name: str
    manifest: EquipmentManifest
    item: EquipmentItem
    body: Path
    sidecar: Path
    user_modified: bool
    # config.toml with the same-named project skill row dropped; None leaves the file alone.
    requirements: Requirements | None
    # One line for the operator when config.toml was skipped; None otherwise.
    warning: str | None = None


def delete_equipment_item(
    root: Path, name: str, *, force: bool = False, dry_run: bool = False
) -> DeleteResult:
    """Retire one generated equipment item: body, adapter, sidecar, manifest row.

    The library entry is kept so ``equip reuse`` can restore it. Every refusal
    raises ``GcTargetError`` before anything is written; a user-edited body needs
    ``force``. ``dry_run`` runs the same checks and reports what would go.
    """
    from dummyindex.shared.errors import EvolveError
    from dummyindex.shared.guard import project_lock

    if dry_run:
        plan = _equipment_plan(root, name, force=force)
        if plan is None:
            return DeleteResult(
                deleted=False, refused=False, reason="nothing to delete"
            )
        return DeleteResult(would_delete=True, reason=_describe(plan))
    try:
        with project_lock(root):
            plan = _equipment_plan(root, name, force=force)
            if plan is None:
                return DeleteResult(
                    deleted=False, refused=False, reason="nothing to delete"
                )
            apply_warning = _equipment_apply(root, plan)
    except EvolveError as exc:
        raise GcTargetError(name, str(exc)) from exc
    notes = [w for w in (plan.warning, apply_warning) if w]
    return DeleteResult(deleted=True, refused=False, reason="; ".join(notes) or None)


def _equipment_plan(root: Path, name: str, *, force: bool) -> _EquipmentPlan | None:
    """Run every equipment guard; ``None`` when the manifest has no such item.

    An unreadable or unsupported config.toml never blocks the delete: the project
    skill row step is skipped with a warning and the file is left untouched.
    """
    context_dir = root / ".context"
    try:
        manifest = read_manifest(context_dir)
    except EquipError as exc:
        raise GcTargetError(name, str(exc)) from exc
    requirements: Requirements | None = None
    warning: str | None = None
    try:
        requirements = read_requirements(root / CONFIG_TOML_REL)
    except RequirementsError as exc:
        warning = (
            f"warning: {CONFIG_TOML_REL} unreadable ({exc}); "
            "project skill row not checked, file left unchanged"
        )
    item = next((i for i in manifest.items if i.name == name), None)
    if item is None:
        return None
    if item.kind not in _EQUIPMENT_KINDS or not is_lifecycle_managed(item):
        raise GcTargetError(
            name,
            "only generated agents and skills are GC-deletable; "
            "use `equip remove` for other items",
        )
    body = contained_path(root, item.path)
    sidecar = contained_path(root, grounding_path(name))
    if body is None or sidecar is None:
        raise GcPathError(item.path, str(root))
    if item.scope is EquipmentScope.TASK and not _refs_finished(
        context_dir, item.task_refs
    ):
        raise GcTargetError(name, "task has a live ref (in-flight proposal or audit)")
    state = classify_item(root, item)
    user_modified = is_user_owned(state)
    if user_modified and not force:
        raise GcTargetError(
            name,
            f"{item.path} is {state.value} (edited since generation); "
            "confirm with the user, then pass --force",
        )
    return _EquipmentPlan(
        name=name,
        manifest=manifest,
        item=item,
        body=body,
        sidecar=sidecar,
        user_modified=user_modified,
        requirements=_without_project_skill(requirements, name),
        warning=warning,
    )


def _without_project_skill(
    requirements: Requirements | None, name: str
) -> Requirements | None:
    if requirements is None:
        return None
    if not any(_is_project_row(s, name) for s in requirements.skills):
        return None
    return dataclasses.replace(
        requirements,
        skills=tuple(s for s in requirements.skills if not _is_project_row(s, name)),
    )


def _is_project_row(skill: SkillRequirement, name: str) -> bool:
    return skill.name == name and skill.from_ == SkillOrigin.PROJECT.value


def _equipment_apply(root: Path, plan: _EquipmentPlan) -> str | None:
    """Config row first, then files. Returns a warning when only the sidecar stays.

    ``remove_item`` deletes the body, removes the native adapter only when it is
    still the generated pointer, and drops the manifest row. The library entry
    is not touched. If a step before the sidecar raises, config.toml is restored
    to its exact original bytes and the error is raised as ``GcTargetError``;
    config.toml is restored on failure, and a retry finishes the delete. A
    sidecar that cannot be removed after the delete is done is a warning, not a
    rollback.
    """
    config = root / CONFIG_TOML_REL
    original = config.read_bytes() if plan.requirements is not None else None
    try:
        if plan.requirements is not None:
            write_requirements(config, plan.requirements)
        remove_item(root, plan.manifest, plan.name, delete_file=True)
    except Exception as exc:
        if original is not None:
            try:
                _restore_bytes(config, original)
            except OSError as restore_exc:
                raise GcTargetError(
                    plan.name,
                    f"{exc}; restoring {CONFIG_TOML_REL} also failed: {restore_exc}",
                ) from exc
        if isinstance(exc, (EquipError, RequirementsError, OSError)):
            raise GcTargetError(plan.name, str(exc)) from exc
        raise
    try:
        plan.sidecar.unlink(missing_ok=True)
    except OSError as exc:
        return f"warning: sidecar {plan.sidecar} not removed ({exc}); delete it by hand"
    return None


def _restore_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` back to ``path`` atomically (temp file, then replace)."""
    tmp = path.with_name(path.name + ".gc-restore")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _describe(plan: _EquipmentPlan) -> str:
    steps = [
        f"body {plan.item.path}",
        "native adapter",
        grounding_path(plan.name),
        "manifest entry",
    ]
    if plan.requirements is not None:
        steps.append("config.toml project skill row")
    text = "remove " + ", ".join(steps) + "; library entry kept"
    if plan.user_modified:
        text += " (user-edited body, --force given)"
    if plan.warning is not None:
        text += f"; {plan.warning}"
    return text


def _reject_sentinel(slug: str) -> None:
    """Refuse a sentinel / path-special slug — ``GcTargetError`` on a match.

    ``slug`` is already charset-validated, so ``.``/``..`` are theoretical for
    the proposal/audit charset (it has no ``.``) but checked anyway so the guard
    is self-contained and order-independent of the validator's exact charset.
    """
    if not slug or not slug.strip():
        raise GcTargetError(slug, "empty slug is never a delete target")
    if slug == ARCHIVE_SENTINEL:
        raise GcTargetError(slug, f"{ARCHIVE_SENTINEL!r} is a sentinel container")
    if slug.startswith("_"):
        raise GcTargetError(slug, "leading-underscore slugs are sentinel containers")
    if slug in {".", ".."}:
        raise GcTargetError(slug, "'.'/'..' are never delete targets")


def _is_tracked(repo_root: Path, target: Path) -> bool:
    """Whether ``target`` is tracked by git in ``repo_root``.

    ``ls-files --error-unmatch <rel>`` exit 0 means some path under the target is
    tracked. Off-git (no git, no repo) counts as tracked: such a workspace never
    had git's recoverability promise, so refusing it as "unrecoverable" is useless.
    """
    try:
        rel = target.relative_to(repo_root.resolve())
    except ValueError:
        # Outside the repo root entirely — git can't speak to it; treat as
        # tracked so recoverability never blocks (containment already passed).
        return True
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", str(rel)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        # git missing → treat as tracked (graceful off-git degradation).
        return True
    # `--error-unmatch` exits non-zero when no tracked path matches; but a
    # non-repo also exits non-zero. Disambiguate: if `rev-parse --git-dir`
    # fails, there is no repo → treat as tracked.
    if completed.returncode == 0:
        return True
    return not _is_git_repo(repo_root)


def _is_git_repo(repo_root: Path) -> bool:
    """Whether ``repo_root`` is inside a git work tree (``rev-parse`` exit 0)."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        return False
    return completed.returncode == 0


def _is_relative_to(path: Path, root: Path) -> bool:
    """Whether ``path`` is inside ``root``, like ``Path.is_relative_to``.

    That method exists on the 3.10 floor (added in 3.9); this explicit form is
    kept only so the containment check reads plainly.
    """
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
