"""Single-seam CLAUDE.md reconciliation.

Folds a pre-existing root ``<root>/CLAUDE.md`` (a legacy managed block, plain
hand-written user content, or both) and any existing canonical
``<root>/.claude/CLAUDE.md`` into ONE canonical ``.claude/CLAUDE.md`` carrying
exactly one fresh managed block, then deletes the root file. The unified
"fold → single canonical file" behavior the audit found missing from every
real build path.

Domain helper, not a CLI: it returns a frozen :class:`ClaudeMdReconcileResult`
and never prints. The CLI prints from the result. Idempotent and safe to run
repeatedly — a second run on unchanged input is a ``noop``.
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

    - ``CREATED``: no canonical file existed; one was written fresh.
    - ``CONSOLIDATED``: a root ``CLAUDE.md`` was folded into the canonical file
      and removed.
    - ``UPDATED``: the canonical file's managed block was refreshed (no root
      file to fold, or an inode-shared single file left intact).
    - ``NOOP``: nothing changed — a second run on unchanged input, or a
      non-fatal degraded outcome that left the tree untouched.
    """

    CREATED = "created"
    CONSOLIDATED = "consolidated"
    UPDATED = "updated"
    NOOP = "noop"

    # Render as the value ("noop"), never the enum repr. Python 3.11 follows
    # __str__ in f-strings; pin to the str value on every interpreter so the
    # CLI prints "consolidated", not "ClaudeMdAction.CONSOLIDATED".
    __str__ = str.__str__


@dataclass(frozen=True)
class ClaudeMdReconcileResult:
    """Outcome of :func:`reconcile_claude_md`.

    - ``action``: the closed-alphabet outcome (see :class:`ClaudeMdAction`).
    - ``root_path``: the root ``<root>/CLAUDE.md`` that was considered.
    - ``canonical_path``: the canonical ``<root>/.claude/CLAUDE.md``.
    - ``message``: a human-readable, CLI-printable summary.
    - ``warnings``: non-fatal degradations (unreadable root, failed write,
      failed delete, unbalanced markers) — empty on the clean paths.
    """

    action: ClaudeMdAction
    root_path: Path
    canonical_path: Path
    message: str
    warnings: tuple[str, ...] = ()


def _user_residue(text: str, *, path: Path) -> str:
    """Validate marker order, then strip every complete managed block.

    Sequential duplicate blocks are a repairable legacy state and are all
    removed before one fresh block is emitted. Reversed, nested, interleaved,
    or dangling marker lines raise before reconciliation writes anything.
    Quoted markers in prose remain inert because the shared parser recognizes
    standalone marker lines only.
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

    Reads ``<out_root>/CLAUDE.md`` (root) and ``<out_root>/.claude/CLAUDE.md``
    (canonical), folds the root's user residue and the canonical's user content
    above a single fresh managed block, writes the canonical atomically, then
    deletes the root file — only after the write succeeds.

    Never raises for expected filesystem or marker conditions: an unreadable
    root, a failed canonical write, a failed delete, or malformed markers each
    degrade to a non-fatal result with a warning, leaving the root file
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

    # R4 — idempotent merge: skip folding only when the root residue was ALREADY
    # folded (a failed-delete + rerun would otherwise double it). Match the exact
    # folded form — the residue is equal to, or the trailing appended segment of,
    # the canonical residue — NOT a loose substring, so a root note that merely
    # coincides with a fragment of canonical (e.g. "kind" inside "kindness") is
    # never silently dropped on delete (the "user content never lost" invariant).
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
