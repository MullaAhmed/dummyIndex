"""Bounded, guarded deletion of a single generated-doc workspace.

The only destructive op in the context-hygiene GC. It removes exactly one
``.context/proposals/<slug>/`` or ``.context/audits/<slug>/`` directory, and
only after a fixed guard ladder has cleared the target. The council (the
``/dummyindex-gc`` skill) decides *what* to delete and surfaces the user
confirmation; this function is the bounded Python that performs the act and
refuses anything outside its narrow contract.

Guards apply **in order** — each is a strictly tighter net than the last:

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

A target that does not exist is an idempotent no-op (``deleted=False``,
``refused=False``), never an error. No ``print`` here — the CLI owns stdout.
This module never touches anything outside the resolved kind-root.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..audit.workspace import audits_root
from ..audit.workspace import validate_slug as validate_audit_slug
from ..buildloop.checklist import counts, parse_checklist
from ..proposals.store import proposals_root
from ..proposals.store import validate_slug as validate_proposal_slug
from .constants import ARCHIVE_SENTINEL
from .enums import CandidateKind
from .errors import GcPathError, GcTargetError
from .models import DeleteResult

# Kinds whose workspace lives under ``.context/proposals/`` (validated + rooted
# by the proposals domain). ``ARCHIVED`` is an ``_archive/<slug>`` child, which
# still resolves under the proposals root, so it shares that validator + root.
_PROPOSAL_KINDS = frozenset(
    {CandidateKind.PROPOSAL, CandidateKind.ARCHIVED, CandidateKind.ORPHAN_SCAFFOLD}
)


def delete_workspace(
    context_dir: Path,
    *,
    kind: CandidateKind,
    slug: str | None = None,
    path: str | None = None,
    allow_untracked: bool = False,
    force_partial: bool = False,
) -> DeleteResult:
    """Delete one generated-doc workspace dir, atomically, behind the guards.

    Exactly one of ``slug`` / ``path`` identifies the target; ``path`` is the
    escape hatch the realpath guard hardens against. Returns a ``DeleteResult``
    describing what happened (deleted / refused / no-op). Raises
    ``ProposalSlugError`` / ``AuditSlugError`` (guard 1), or ``GcTargetError`` /
    ``GcPathError`` (guards 2–4) — the caller maps every one to exit 2.
    """
    root = _kind_root(context_dir, kind)

    # --- guard 1: slug validation (out-of-charset traversal) ----------------
    # Always run the validator when a slug is given — it raises the typed slug
    # error for ``../../etc`` before any path work. ``path=`` callers skip this
    # (no slug to validate); the realpath guard contains them instead.
    safe_slug = _validate(kind, slug) if slug is not None else None

    # --- guard 2: sentinel reject -------------------------------------------
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

    # --- guard 3: realpath containment --------------------------------------
    # Resolve symlinks on both sides and assert the target stays inside the
    # resolved kind-root. A symlinked workspace / ``--path`` is the only way to
    # escape; a clean slug is charset-bounded and cannot.
    resolved_target = target.resolve()
    resolved_root = root.resolve()
    if not _is_relative_to(resolved_target, resolved_root):
        raise GcPathError(str(target), str(root))

    # --- missing dir: idempotent no-op (NOT an error) -----------------------
    if not target.exists():
        return DeleteResult(
            deleted=False, refused=False, reason="nothing to delete", untracked=False
        )

    # --- guard 4: liveness (proposals/archived only) ------------------------
    if kind in _PROPOSAL_KINDS and not force_partial:
        reason = _liveness_block(target)
        if reason is not None:
            raise GcTargetError(
                safe_slug or str(target),
                f"{reason}; pass force_partial",
            )

    # --- guard 5: recoverability (git-tracked vs untracked) -----------------
    tracked = _is_tracked(context_dir.parent, resolved_target)
    untracked = not tracked
    if untracked and not allow_untracked:
        return DeleteResult(
            deleted=False,
            refused=True,
            reason="unrecoverable: not tracked by git; pass allow_untracked",
            untracked=True,
        )

    # --- delete --------------------------------------------------------------
    shutil.rmtree(target)
    return DeleteResult(deleted=True, refused=False, reason=None, untracked=untracked)


# ----- guard helpers --------------------------------------------------------


def _kind_root(context_dir: Path, kind: CandidateKind) -> Path:
    """``.context/proposals`` or ``.context/audits`` for the candidate kind."""
    if kind in _PROPOSAL_KINDS:
        return proposals_root(context_dir)
    return audits_root(context_dir)


def _validate(kind: CandidateKind, slug: str) -> str:
    """Run the kind's own slug validator (raises the typed slug error)."""
    if kind in _PROPOSAL_KINDS:
        return validate_proposal_slug(slug)
    return validate_audit_slug(slug)


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


def _liveness_block(target: Path) -> str | None:
    """Return a refusal reason if the proposal is in-flight, else ``None``.

    In-flight = ``proposal.json`` status ``in_progress`` OR a partial checklist
    (some boxes done but not all, or any box still unchecked). Reading is
    tolerant: an unreadable/absent ``proposal.json`` or ``checklist.md`` simply
    contributes no block (the other guards still apply).
    """
    if _proposal_status(target) == "in_progress":
        return "in-flight (status in_progress)"
    if _checklist_partial(target):
        return "in-flight (checklist partial)"
    return None


def _proposal_status(target: Path) -> str | None:
    """Read ``proposal.json``'s ``status`` field, tolerantly (``None`` on miss)."""
    path = target / "proposal.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return status if isinstance(status, str) else None


def _checklist_partial(target: Path) -> bool:
    """Whether ``checklist.md`` has work started but not finished.

    Partial = at least one box but not every box is closed (``0 < done <
    total``), or any box remains unchecked. An absent / unparseable checklist is
    treated as *not* partial (no block).
    """
    path = target / "checklist.md"
    if not path.is_file():
        return False
    try:
        items = parse_checklist(path)
    except Exception:  # noqa: BLE001 — a malformed checklist must not block GC
        return False
    done, total = counts(items)
    if total == 0:
        return False
    return done < total


def _is_tracked(repo_root: Path, target: Path) -> bool:
    """Whether ``target`` is tracked by git in ``repo_root``.

    Uses ``git -C <repo_root> ls-files --error-unmatch <rel>`` — exit 0 means at
    least one tracked path exists under the target. When git is absent or
    ``repo_root`` is not a repo, the target is **treated as tracked** so an
    off-git workspace is never refused as "unrecoverable" (it was never under
    git's recoverability promise to begin with — refusing it would be useless).
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
    """``Path.is_relative_to`` polyfill (the method lands in 3.9, target is 3.10).

    Written explicitly rather than relying on the method so the containment
    check reads unambiguously and stays correct on the oldest supported
    interpreter.
    """
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
