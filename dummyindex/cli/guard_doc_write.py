"""`dummyindex context guard-doc-write` — PreToolUse Write-guard.

Wire-only: read the PreToolUse hook JSON from stdin, decide whether the target
``Write`` would create a stray internal planning doc under ``docs/``, and either
print a single-line JSON ``deny`` payload or stay silent. It ALWAYS returns 0 —
a PreToolUse hook that exits 2 *blocks* the tool, so this guard never does that:
it speaks only through the JSON ``permissionDecision`` and otherwise allows.

Fail-open is the whole contract. Malformed/empty stdin, a non-``Write`` tool
(``Edit``/``MultiEdit`` can only maintain an existing file, never create a new
leak), a missing ``file_path``, a path the classifier cannot make repo-relative,
a disabled guard, an allow-listed path, or any internal exception all resolve to
"allow": exit 0 with empty stdout. No git, no network, no subprocess on this
path — the guard is a pure read -> classify -> decide.

It deliberately does NOT inherit ``reconcile_gate.run``'s ``return 2`` arg-error
branch: an arg-parse problem falls through to the process cwd and allows.
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path

from .common import parse_path_and_root, resolve_context_root
from .memory import read_hook_stdin

WRITE_TOOL = "Write"


def run(args: list[str]) -> int:
    """Decide the guard. Never returns anything but 0 (fail-open, never blocks).

    The catch-all keeps the guard from ever wedging a session: any unexpected
    error — a malformed payload that slips the type checks, a classifier raise,
    anything — allows the write. NEVER ``exit 2``, never raise.
    """
    try:
        return _decide(args)
    except Exception:
        return 0


def _decide(args: list[str]) -> int:
    repo_root = _resolve_repo_root(args)

    hook = read_hook_stdin()
    if hook.get("tool_name") != WRITE_TOOL:
        # Matcher is Write-only; Edit/MultiEdit require a pre-existing file and
        # so can only maintain an existing doc, never create a new leak.
        return 0

    tool_input = hook.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return 0

    from dummyindex.context.domains.config import read_doc_guard_settings

    enabled, allow_globs = read_doc_guard_settings(repo_root / ".context")
    if not enabled:
        return 0  # config-gated off → allow everything

    from dummyindex.context.domains.docguard.classify import classify_doc_path
    from dummyindex.context.domains.docguard.decision import decide

    # classify_doc_path raises DocPathError for a path outside repo_root; the
    # outer catch-all turns that into a fail-open allow.
    classification = classify_doc_path(repo_root, file_path)

    rel_path = classification.rel_path or ""
    if any(fnmatch(rel_path, glob) for glob in allow_globs):
        # An allow-listed path is exempt — not a stray for guard purposes.
        return 0

    payload = decide(classification)
    if payload:
        print(json.dumps(payload, separators=(",", ":")))
    return 0


def _resolve_repo_root(args: list[str]) -> Path:
    """Resolve the repo root from ``--root`` with a tolerant cwd fallback.

    Any arg-parse problem falls through to the process cwd — never an error
    exit. ``reconcile_gate.run`` returns 2 on a leftover arg; the guard must
    NOT, so leftovers are ignored rather than rejected.
    """
    try:
        scope, explicit_root, _leftover = parse_path_and_root(args)
        return resolve_context_root(scope, explicit_root=explicit_root)
    except Exception:
        return Path.cwd()
