"""Single-seam CLAUDE.md reconciliation.

Folds a root ``<root>/CLAUDE.md`` (legacy managed block, hand-written content, or
both) and any existing ``<root>/.claude/CLAUDE.md`` into ONE canonical
``.claude/CLAUDE.md`` with exactly one fresh managed block, then deletes the root
file. Returns a frozen :class:`ClaudeMdReconcileResult` and never prints.
Idempotent: a second run on unchanged input is a ``noop``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.output.bootstrap import (
    BEGIN_MARKER,
    END_MARKER,
    UnbalancedMarkersError,
    _managed_block_spans,
    ensure_guidance_target_in_scope,
    generate_managed_block,
)


class ClaudeMdAction(str, Enum):
    """What :func:`reconcile_claude_md` did to the CLAUDE.md layout.

    ``CREATED`` wrote a fresh canonical file; ``CONSOLIDATED`` folded a root
    ``CLAUDE.md`` in and deleted it (a failed delete is a warning); ``UPDATED``
    refreshed the canonical block (no root to fold, or an inode-shared single
    file); ``NOOP`` changed nothing (unchanged input, or a degraded outcome).
    """

    CREATED = "created"
    CONSOLIDATED = "consolidated"
    UPDATED = "updated"
    NOOP = "noop"

    # Python 3.11 f-strings follow __str__; pin it so every interpreter prints
    # "consolidated", never "ClaudeMdAction.CONSOLIDATED".
    __str__ = str.__str__


@dataclass(frozen=True)
class ClaudeMdReconcileResult:
    """Outcome of :func:`reconcile_claude_md`.

    ``root_path`` / ``canonical_path`` are ``<root>/CLAUDE.md`` and
    ``<root>/.claude/CLAUDE.md``; ``message`` is CLI-printable; ``warnings`` lists
    non-fatal degradations (unreadable root, failed write or delete, unbalanced
    markers) and is empty on the clean paths.
    """

    action: ClaudeMdAction
    root_path: Path
    canonical_path: Path
    message: str
    warnings: tuple[str, ...] = ()


def _user_residue(text: str, *, path: Path) -> str:
    """Validate marker order, then strip every complete managed block.

    Sequential duplicates (a repairable legacy state) are all removed; reversed,
    nested, interleaved or dangling markers raise before anything is written. Only
    standalone marker lines count, so markers quoted in prose stay inert.
    """
    spans = _managed_block_spans(
        text,
        path=path,
        begin_marker=BEGIN_MARKER,
        end_marker=END_MARKER,
    )
    residue = text
    for span in reversed(spans):
        residue = residue[: span.start] + residue[span.remove_end :]
    return residue.strip()


def reconcile_claude_md(out_root: Path) -> ClaudeMdReconcileResult:
    """Fold root + canonical CLAUDE.md into one canonical managed file.

    Both files' user content goes above a single fresh managed block; the
    canonical is written atomically and the root deleted only after that write
    succeeds. Never raises for expected filesystem or marker conditions: each
    degrades to a non-fatal result with a warning, leaving the root file
    untouched unless the canonical write already succeeded.
    """
    root_path = out_root / "CLAUDE.md"
    canonical_path = out_root / ".claude" / "CLAUDE.md"

    try:
        ensure_guidance_target_in_scope(out_root, root_path)
        ensure_guidance_target_in_scope(out_root, canonical_path)
    except ValueError as exc:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message=f"left files in place: {exc}",
            warnings=(str(exc),),
        )

    managed = f"{BEGIN_MARKER}\n{generate_managed_block().rstrip()}\n{END_MARKER}"

    root_exists = root_path.exists()
    canonical_exists = canonical_path.exists()

    # R1 — inode-safety: if root and canonical are the same file (symlink or
    # hardlink), there is nothing to consolidate and deleting would destroy the
    # only copy. Refresh the managed block in place; never delete.
    if root_exists and canonical_exists and _same_file(root_path, canonical_path):
        return _refresh_single_file(canonical_path, managed, root_path)

    # Read the root residue (R3 — quoted markers preserved; whole-block strip).
    root_residue = ""
    if root_exists:
        try:
            root_text = root_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            # Unreadable root → degrade; do NOT delete, do NOT lose anything.
            return ClaudeMdReconcileResult(
                action=ClaudeMdAction.NOOP,
                root_path=root_path,
                canonical_path=canonical_path,
                message=f"left {root_path} in place: could not read it ({exc})",
                warnings=(f"cannot read {root_path}: {exc}",),
            )
        try:
            root_residue = _user_residue(root_text, path=root_path)
        except UnbalancedMarkersError as exc:
            return ClaudeMdReconcileResult(
                action=ClaudeMdAction.NOOP,
                root_path=root_path,
                canonical_path=canonical_path,
                message=(
                    f"left {root_path} in place: malformed dummyindex markers "
                    "— resolve manually before re-running"
                ),
                warnings=(str(exc),),
            )

    # Read the canonical's existing user content (block stripped).
    canonical_residue = ""
    if canonical_exists:
        try:
            canonical_text = canonical_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return ClaudeMdReconcileResult(
                action=ClaudeMdAction.NOOP,
                root_path=root_path,
                canonical_path=canonical_path,
                message=f"left files in place: could not read {canonical_path} ({exc})",
                warnings=(f"cannot read {canonical_path}: {exc}",),
            )
        try:
            canonical_residue = _user_residue(canonical_text, path=canonical_path)
        except UnbalancedMarkersError as exc:
            return ClaudeMdReconcileResult(
                action=ClaudeMdAction.NOOP,
                root_path=root_path,
                canonical_path=canonical_path,
                message=(
                    f"left files in place: malformed dummyindex markers in "
                    f"{canonical_path} — resolve manually before re-running"
                ),
                warnings=(str(exc),),
            )

    # R4 — idempotent merge: skip folding only if the root residue was ALREADY
    # folded (a failed-delete rerun would double it). Match the exact folded form
    # (equal, or the trailing appended segment), NOT a substring, so a root "kind"
    # inside canonical "kindness" is never dropped (user-content-never-lost invariant).
    already_folded = root_residue == canonical_residue or canonical_residue.endswith(
        f"\n\n{root_residue}"
    )
    merged_residue = canonical_residue
    if root_residue and not already_folded:
        merged_residue = (
            f"{canonical_residue}\n\n{root_residue}"
            if canonical_residue
            else root_residue
        )

    new_content = (
        f"{merged_residue}\n\n{managed}\n" if merged_residue else f"{managed}\n"
    )

    # Idempotency check: if the canonical already holds exactly this content
    # and there is nothing to fold/delete from root, it's a true no-op.
    if canonical_exists and canonical_text == new_content and not root_exists:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message=f"{canonical_path} already current",
        )

    # Write-then-delete: write canonical first. Only on success do we touch root.
    try:
        write_text_atomic(canonical_path, new_content)
    except OSError as exc:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message=f"left {root_path} in place: writing {canonical_path} failed ({exc})",
            warnings=(f"cannot write {canonical_path}: {exc}",),
        )

    if not root_exists:
        action = (
            ClaudeMdAction.CREATED if not canonical_exists else ClaudeMdAction.UPDATED
        )
        return ClaudeMdReconcileResult(
            action=action,
            root_path=root_path,
            canonical_path=canonical_path,
            message=f"wrote {canonical_path}",
        )

    # Canonical write succeeded — now delete the root file (even if its residue
    # was whitespace-only). A failed delete is non-fatal: the next run dedupes.
    delete_warnings: tuple[str, ...] = ()
    try:
        root_path.unlink()
    except OSError as exc:
        delete_warnings = (f"cannot delete {root_path}: {exc}",)

    if delete_warnings:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.CONSOLIDATED,
            root_path=root_path,
            canonical_path=canonical_path,
            message=(
                f"folded {root_path} into {canonical_path} but could not remove "
                "the root file"
            ),
            warnings=delete_warnings,
        )

    return ClaudeMdReconcileResult(
        action=ClaudeMdAction.CONSOLIDATED,
        root_path=root_path,
        canonical_path=canonical_path,
        message=f"consolidated {root_path} into {canonical_path} (root file removed)",
    )


def _same_file(a: Path, b: Path) -> bool:
    """True when ``a`` and ``b`` resolve to the same on-disk inode (R1)."""
    try:
        if a.resolve() == b.resolve():
            return True
        return os.path.samefile(a, b)
    except OSError:
        return False


def _refresh_single_file(
    canonical_path: Path, managed: str, root_path: Path
) -> ClaudeMdReconcileResult:
    """Refresh the managed block of an inode-shared single file; never delete.

    Reached only when root and canonical are the same inode (R1). The file
    survives intact; its user residue is preserved and the block refreshed.
    """
    try:
        text = canonical_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message=f"left shared CLAUDE.md in place: could not read it ({exc})",
            warnings=(f"cannot read {canonical_path}: {exc}",),
        )
    try:
        residue = _user_residue(text, path=canonical_path)
    except UnbalancedMarkersError as exc:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message=(
                "left shared CLAUDE.md in place: malformed dummyindex markers "
                "— resolve manually before re-running"
            ),
            warnings=(str(exc),),
        )
    new_content = f"{residue}\n\n{managed}\n" if residue else f"{managed}\n"
    if text == new_content:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message="shared CLAUDE.md already current (root and canonical are one file)",
        )
    try:
        write_text_atomic(canonical_path, new_content)
    except OSError as exc:
        return ClaudeMdReconcileResult(
            action=ClaudeMdAction.NOOP,
            root_path=root_path,
            canonical_path=canonical_path,
            message=f"left shared CLAUDE.md in place: write failed ({exc})",
            warnings=(f"cannot write {canonical_path}: {exc}",),
        )
    return ClaudeMdReconcileResult(
        action=ClaudeMdAction.UPDATED,
        root_path=root_path,
        canonical_path=canonical_path,
        message="refreshed shared CLAUDE.md in place (root and canonical are one file)",
    )
