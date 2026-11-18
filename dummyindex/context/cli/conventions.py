"""`dummyindex context conventions-write` — atomic markdown write to conventions/<section>.md."""

from __future__ import annotations

import sys
from pathlib import Path

from .common import (
    parse_kv_flags,
    parse_path_and_root,
    resolve_context_root,
    usage_error,
)


def run(args: list[str]) -> int:
    """Atomic placement of an agent-authored markdown into conventions/."""
    from dummyindex.context.build.conventions import (
        ConventionSectionError,
        write_convention_section,
    )

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest, allowed={"--section", "--from-file"})
    if leftover:
        return usage_error(
            "conventions-write",
            f"unknown argument(s) for `conventions-write`: {leftover}",
        )
    section = parsed.get("section")
    from_file = parsed.get("from-file")
    if not section or not from_file:
        return usage_error(
            "conventions-write",
            "--section <name> and --from-file <path> are both required",
        )

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        target = write_convention_section(
            context_dir, section=section, source_file=Path(from_file)
        )
    except ConventionSectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"context conventions-write: {target}")
    return 0
