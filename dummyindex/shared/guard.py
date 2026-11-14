"""Path guard and project writer lock shared by evolve and context writers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath

from dummyindex.shared.errors import EvolveError


def safe_file(root: Path, relative: str, *, exists: bool = True) -> Path:
    """Resolve a regular file without following any symlink or escaping root."""
    pure = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or pure.is_absolute()
        or PureWindowsPath(relative).drive
        or ".." in pure.parts
        or str(pure) == "."
    ):
        raise EvolveError(f"unsafe relative file path: {relative!r}")
    root = root.absolute()
    path = root
    for part in pure.parts:
        path = path / part
        if path.is_symlink():
            raise EvolveError(f"symlink is not an evolve input or destination: {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise EvolveError(f"path escapes its workspace: {path}")
    if exists and not path.is_file():
        raise EvolveError(f"required file missing: {path}")
    if path.exists() and not path.is_file():
        raise EvolveError(f"expected a regular file: {path}")
    return path


@contextmanager
def project_lock(project_root: Path, *, lock_name: str = "evolve.lock"):
    """One writer per project; OS advisory locks are released after a crash."""
    if lock_name not in {"evolve.lock", "replay.lock", "observe.lock"}:
        raise EvolveError("unknown project writer lock")
    path = safe_file(project_root, f".context/cache/{lock_name}", exists=False)
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
