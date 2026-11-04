"""Recoverable multi-file evolve promotion and guarded rollback."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

from .evolve_gate import (
    EvolveError,
    _atomic_bytes,
    _digest,
    _managed_overlay,
    _working_inputs,
    safe_file,
    staged_files,
)


@contextmanager
def project_lock(project_root: Path):
    """One writer per project; OS advisory locks are released after a crash."""
    path = safe_file(project_root, ".context/cache/evolve.lock", exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise EvolveError(
                "another evolve writer is active for this project; retry after it finishes"
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _journal(path: Path, data: dict) -> None:
    _atomic_bytes(path, (json.dumps(data, indent=2, sort_keys=True) + "\n").encode())


def promote_files(
    targets: tuple[str, ...],
    run_dir: Path,
    index: int,
    project_root: Path,
    receipt: dict,
) -> tuple[str, ...]:
    """Back up all originals before writes; restore all targets after any failure."""
    edits = {
        t: p.read_bytes()
        for t, p in zip(targets, staged_files(run_dir, index, targets), strict=True)
    }
    edits = _managed_overlay(_working_inputs(project_root), edits)
    targets = tuple(edits)
    destinations = {t: safe_file(project_root, t) for t in targets}
    originals = {t: p.read_bytes() for t, p in destinations.items()}
    if {t: _digest(b) for t, b in edits.items()} != receipt["staged_sha256"] or {
        t: _digest(b) for t, b in originals.items()
    } != receipt["baseline_targets"]:
        raise EvolveError(
            "candidate or baseline changed during promotion; rerun evolve apply"
        )
    journal_path = safe_file(run_dir, f"backup/{index}/transaction.json", exists=False)
    if journal_path.exists():
        raise EvolveError(
            "candidate already has a promotion journal; roll back or use a new run"
        )
    backups = {
        t: safe_file(run_dir, f"backup/{index}/files/{t}", exists=False)
        for t in targets
    }
    for target, backup in backups.items():
        _atomic_bytes(backup, originals[target])
    journal = {
        "schema_version": 1,
        "state": "prepared",
        "targets": list(targets),
        "before": {t: _digest(b) for t, b in originals.items()},
        "after": {t: _digest(b) for t, b in edits.items()},
    }
    _journal(journal_path, journal)
    try:
        for target, path in destinations.items():
            safe_file(project_root, target)
            if path.read_bytes() != originals[target]:
                raise EvolveError(f"target changed during promotion: {target}")
            _atomic_bytes(path, edits[target])
        journal["state"] = "committed"
        _journal(journal_path, journal)
    except (OSError, EvolveError) as exc:
        errors: list[str] = []
        for target, path in destinations.items():
            try:
                safe_file(project_root, target)
                current = path.read_bytes()
                if current == originals[target]:
                    continue
                if current != edits[target]:
                    raise EvolveError(
                        "target changed during recovery; refusing to overwrite it"
                    )
                _atomic_bytes(path, originals[target])
            except (OSError, EvolveError) as restore_error:
                errors.append(f"{target}: {restore_error}")
        journal.update(
            state="recovery_required" if errors else "rolled_back", errors=errors
        )
        _journal(journal_path, journal)
        raise EvolveError(
            f"promotion failed; {journal['state']}; recovery journal: {journal_path}: {exc}"
        ) from exc
    return targets


def rollback_files(run_dir: Path, index: int, project_root: Path) -> tuple[str, ...]:
    journal_path = safe_file(run_dir, f"backup/{index}/transaction.json")
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        targets = tuple(journal["targets"])
        if not targets or not all(isinstance(t, str) for t in targets):
            raise ValueError("invalid targets")
        originals = {
            t: safe_file(run_dir, f"backup/{index}/files/{t}").read_bytes()
            for t in targets
        }
        destinations = {t: safe_file(project_root, t) for t in targets}
        for target, path in destinations.items():
            if _digest(originals[target]) != journal["before"][target]:
                raise EvolveError(f"backup changed: {target}")
            allowed = {journal["after"][target]}
            if journal["state"] in {"prepared", "recovery_required", "rolled_back"}:
                allowed.add(journal["before"][target])
            if _digest(path.read_bytes()) not in allowed:
                raise EvolveError(
                    f"target changed since promotion; refusing rollback: {target}"
                )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EvolveError(f"invalid promotion journal: {exc}") from exc
    # Persist before the first restoration: interruption can leave a mix of
    # original and promoted bytes, both of which a recovery retry must accept.
    journal["state"] = "recovery_required"
    _journal(journal_path, journal)
    try:
        for target, path in destinations.items():
            safe_file(project_root, target)
            _atomic_bytes(path, originals[target])
        journal["state"] = "rolled_back"
        _journal(journal_path, journal)
    except (OSError, EvolveError) as exc:
        journal["state"] = "recovery_required"
        _journal(journal_path, journal)
        raise EvolveError(
            f"rollback incomplete; recovery journal: {journal_path}: {exc}"
        ) from exc
    return targets
