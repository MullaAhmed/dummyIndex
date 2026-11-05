"""Keep the scan scope distinct from its authorized context destination."""

from __future__ import annotations

import json
import stat
from pathlib import Path


class BuildScopeError(ValueError):
    """A build would scan or write outside its declared roots."""


def validate_context_destination(root: Path) -> None:
    for relative in (
        ".context",
        ".context/map",
        ".context/features",
        ".context/cache",
        ".context/source-docs",
        ".context/architecture",
        ".context/conventions",
        ".context/playbooks",
    ):
        path = root / relative
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        linked = path.is_symlink() or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        )
        if linked:
            raise BuildScopeError(f"context destination is linked; preserved: {path}")


def scan_root(root: Path, explicit: Path | None = None) -> Path:
    root = root.resolve()
    validate_context_destination(root)
    if explicit is not None:
        scope = explicit.resolve()
    else:
        relative = "."
        for path, field in (
            (root / ".context/meta.json", "scan_scope"),
            (root / ".context/config.json", "scope_path"),
        ):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                value = (
                    raw.get("config", {}).get(field)
                    if field == "scan_scope"
                    else raw.get(field)
                )
            except (OSError, ValueError, AttributeError):
                continue
            if value:
                relative = value
                break
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise BuildScopeError(
                "stored scan scope must be a repository-relative path"
            )
        scope = (root / relative).resolve()
    if not scope.is_relative_to(root) or not scope.is_dir():
        raise BuildScopeError(
            f"scan scope must be a directory within output root {root}: {scope}"
        )
    return scope
