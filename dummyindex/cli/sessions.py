"""`dummyindex sessions list [--root DIR] [--projects-root DIR] --json`.

Wiring only: flags are parsed here, the listing lives in
``dummyindex.context.domains.sessions``. Read-only; unparseable session data
is reported inside the document (state ``unknown`` plus a warning), never as
an error exit. Usage errors exit 2.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_USAGE = "usage: dummyindex sessions list [--root DIR] [--projects-root DIR] --json"


def run(argv: list[str]) -> int:
    as_json = "--json" in argv
    if not argv or argv[0] != "list":
        return _usage_error("expected `list`", as_json=as_json)
    root: str | None = None
    projects_root: str | None = None
    rest = argv[1:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--json":
            i += 1
        elif arg in ("--root", "--projects-root") and i + 1 < len(rest):
            if arg == "--root":
                root = rest[i + 1]
            else:
                projects_root = rest[i + 1]
            i += 2
        elif arg.startswith("--root="):
            root = arg.split("=", 1)[1]
            i += 1
        elif arg.startswith("--projects-root="):
            projects_root = arg.split("=", 1)[1]
            i += 1
        else:
            return _usage_error(
                f"unknown argument {arg!r}", as_json=as_json, code="unknown_argument"
            )
    if not as_json:
        return _usage_error("--json is required", as_json=False, code="usage")

    from dummyindex.context.domains.sessions import list_sessions
    from dummyindex.usage.transcripts import default_projects_root

    base = Path(projects_root) if projects_root else default_projects_root()
    items = list_sessions(
        base,
        now=datetime.now(timezone.utc),
        root=Path(root) if root else None,
    )
    print(json.dumps({"sessions": items}, indent=2))
    return 0


def _usage_error(message: str, *, as_json: bool, code: str = "usage") -> int:
    if as_json:
        print(json.dumps({"error": {"code": code, "message": message}}, indent=2))
    print(f"error: {message}", file=sys.stderr)
    print(_USAGE, file=sys.stderr)
    return 2
