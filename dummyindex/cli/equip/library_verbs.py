"""Specialist-library wiring for the equip CLI: ``equip reuse`` + lesson storing.

Wire-only: parsing, printing and exit codes live here; every decision (hashing,
validation, overwrite refusal, reverify) is in
``dummyindex/context/domains/equip/lifecycle/library.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.equip import EquipError, read_manifest
from dummyindex.context.domains.equip.lifecycle import library

from .common import pull_bool_flag, pull_root_then_positional


def read_lesson_file(path: str) -> tuple[dict | None, str | None]:
    """Parse and validate a ``--lesson-file``; return ``(lesson, error)``."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"lesson file unreadable: {exc}"
    if not isinstance(data, dict):
        return None, "lesson file must be a JSON object"
    try:
        library.validate_lesson(data)
    except EquipError as exc:
        return None, str(exc)
    return data, None


def store_items(project_root: Path, lesson: dict | None, names: set[str]) -> int:
    """Store the named agent bodies into the library when a lesson is supplied.

    No lesson or no names -> nothing stored, exit 0. Notices go to stderr so
    ``--json`` stdout stays machine-parseable.
    """
    if lesson is None or not names:
        return 0
    try:
        manifest = read_manifest(project_root / ".context")
        for item in library.agent_items(manifest.items, names):
            body_path = project_root / item.path
            if not body_path.is_file():
                continue
            body = body_path.read_text(encoding="utf-8")
            cid = library.store(project_root, item, body, lesson)
            print(f"equip: stored {cid} in specialist library", file=sys.stderr)
    except (EquipError, OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def run_reuse(rest: list[str]) -> int:
    """``equip reuse CAPABILITY_ID [--force] [--root DIR]``."""
    force, rest = pull_bool_flag(rest, "force")
    root, (cid, leftover) = pull_root_then_positional(rest)
    if cid is None or leftover:
        print(
            "error: `equip reuse` requires CAPABILITY_ID [--force] [--root DIR]",
            file=sys.stderr,
        )
        return 2
    try:
        dest = library.reuse_capability(root, cid, force=force)
        status = library.reverify(root, cid)
    except (EquipError, OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    reason = ""
    if status == library.NEEDS_REVERIFY:
        reason = " (grounding or body changed since stored)"
    shown = dest.relative_to(root.resolve()).as_posix()
    print(f"equip reuse: {cid} -> {shown} status={status}{reason}")
    return 0
