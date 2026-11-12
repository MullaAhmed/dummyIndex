"""Name validation and path containment for toolkit reads and writes.

Every write goes through :func:`safe_target`. It refuses ``..``, separators and
drive prefixes in path parts, and it refuses any existing ancestor that is a
symlink resolving outside its base. The check runs before anything is written.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .constants import ALLOWED_SOURCE_SCHEMES
from .errors import ToolkitError

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_TERMINAL_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_BAD_PART_CHARS = ("/", "\\", ":")


def validate_name(name: str) -> str:
    """A kind-level item name: one safe path segment with no traversal."""
    if not isinstance(name, str) or not _NAME_RE.match(name) or ".." in name:
        raise ToolkitError(
            "invalid_name",
            f"name {name!r} must be 1-64 letters, digits, '.', '_' or '-' "
            "and must start with a letter or digit",
        )
    return name


def validate_plugin_key(key: str) -> str:
    """``<plugin>@<marketplace>`` with both halves valid names."""
    plugin, sep, market = key.partition("@")
    if not sep:
        raise ToolkitError("invalid_name", f"plugin key {key!r} needs @<marketplace>")
    validate_name(plugin)
    validate_name(market)
    return key


def validate_terminal_id(terminal_id: str) -> str:
    if not isinstance(terminal_id, str) or not _TERMINAL_RE.match(terminal_id):
        raise ToolkitError(
            "invalid_terminal_id",
            "terminal id must be 1-64 letters, digits, '_' or '-'",
        )
    return terminal_id


def validate_source_scheme(ref: str) -> str:
    """Return the scheme when it is allowlisted; refuse everything else."""
    scheme, sep, _ = ref.partition(":")
    if not sep or scheme not in ALLOWED_SOURCE_SCHEMES:
        allowed = ", ".join(f"{s}:" for s in ALLOWED_SOURCE_SCHEMES)
        raise ToolkitError(
            "unsupported_source",
            f"source {ref!r} is not allowed; allowed schemes: {allowed}",
        )
    return scheme


def _within(child: Path, base: Path) -> bool:
    try:
        child.relative_to(base)
    except ValueError:
        return False
    return True


def is_link(path: Path) -> bool:
    """A symlink, or a Windows directory junction (not a symlink to Python)."""
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction and isjunction(path))


def refuse_links(folder: Path) -> None:
    """Raise ``path_escape`` if ``folder`` holds any symlink or junction.

    Used before a recursive delete or copy, so a link inside a managed folder can
    never redirect the operation to content outside it.
    """
    if not folder.is_dir() or is_link(folder):
        return
    pending = [folder]
    while pending:
        current = pending.pop()
        for child in current.iterdir():
            if is_link(child):
                raise ToolkitError(
                    "path_escape", f"{child} is a link; refusing to follow it"
                )
            if child.is_dir():
                pending.append(child)


def safe_target(base: Path, *parts: str) -> Path:
    """``base / parts`` after refusing traversal and symlink escapes."""
    for part in parts:
        if not part or part in (".", "..") or any(c in part for c in _BAD_PART_CHARS):
            raise ToolkitError("path_escape", f"path part {part!r} is not allowed")
    base_real = base.resolve(strict=False)
    current = base
    for part in parts:
        current = current / part
        # Any existing component (symlink, junction, or dangling link) whose
        # real location leaves the base is refused. resolve() follows both
        # symlinks and Windows junctions.
        if (current.exists() or current.is_symlink()) and not _within(
            current.resolve(strict=False), base_real
        ):
            raise ToolkitError(
                "path_escape",
                f"{current} leads outside {base}; refusing to write",
            )
    target = base.joinpath(*parts)
    if not _within(target.resolve(strict=False), base_real):
        raise ToolkitError("path_escape", f"{target} resolves outside {base}")
    return target


def read_target(base: Path, *parts: str) -> Path:
    """``base / parts`` for reads: traversal is refused, symlinks are followed."""
    for part in parts:
        if not part or part in (".", "..") or any(c in part for c in _BAD_PART_CHARS):
            raise ToolkitError("path_escape", f"path part {part!r} is not allowed")
    return base.joinpath(*parts)


def check_out_dir(out_dir: Path, root: Path) -> Path:
    """The terminal bundle folder must be absolute and must not sit in ``.context/``."""
    if not out_dir.is_absolute():
        raise ToolkitError("invalid_argument", "--out-dir must be an absolute path")
    resolved = out_dir.resolve(strict=False)
    context_dir = (root / ".context").resolve(strict=False)
    if _within(resolved, context_dir):
        raise ToolkitError(
            "invalid_argument",
            "--out-dir must not be inside .context/ (terminal bundles are app data)",
        )
    return out_dir
