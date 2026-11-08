"""`dummyindex context guard-doc-write` — PreToolUse doc guard and language hint.

Agent/Task/SendMessage get a warn-only ``additionalContext`` language hint;
it never denies.

Two checks. (1) Citation guard (all three tools): deny new text that adds a
``.context/(proposals|audits)/<slug>/`` citation, absent from the existing file,
to authored durable markdown. (2) Stray-doc guard (``Write`` only). Wire-only: read the PreToolUse hook JSON from stdin, decide whether the target
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
CITATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
LANGUAGE_TOOLS = frozenset({"Agent", "Task", "SendMessage"})
MAX_SCAN_CHARS = 1_000_000  # 1 MB cap; larger input is allowed unscanned


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
    tool_name = hook.get("tool_name")
    if tool_name in LANGUAGE_TOOLS:
        return _language_hint(hook)
    if tool_name not in CITATION_TOOLS:
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
    try:
        citation_deny = _citation_deny(repo_root, file_path, tool_input)
    except Exception:
        citation_deny = {}  # fail open for the citation check only
    if citation_deny:
        print(json.dumps(citation_deny, separators=(",", ":")))
        return 0

    if tool_name != WRITE_TOOL:
        # Edit/MultiEdit can only maintain an existing file, never create a
        # stray planning doc; only the citation check above applies to them.
        return 0

    classification = classify_doc_path(repo_root, file_path)

    rel_path = classification.rel_path or ""
    if any(fnmatch(rel_path, glob) for glob in allow_globs):
        # An allow-listed path is exempt — not a stray for guard purposes.
        return 0

    payload = decide(classification)
    if payload:
        print(json.dumps(payload, separators=(",", ":")))
    return 0


def _language_hint(hook: dict) -> int:
    """Warn via ``additionalContext`` when an agent prompt is mostly English.

    Checks ``message`` for SendMessage and ``prompt`` for Agent/Task. Never
    denies, never blocks, and always returns 0.
    """
    from dummyindex.context.domains.docguard.language import cjk_share, needs_warning

    tool_input = hook.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    field = "message" if hook.get("tool_name") == "SendMessage" else "prompt"
    text = tool_input.get(field)
    if not isinstance(text, str) or len(text) > MAX_SCAN_CHARS:
        return 0
    if not needs_warning(cjk_share(text)):
        return 0
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                "Language policy: write subagent prompts and SendMessage bodies in "
                "concise Chinese with caveman rules. Keep code, paths, commands, and "
                "identifiers verbatim. Code, commits, docs, and final reports stay English."
            ),
        }
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0


def _new_texts(tool_input: dict) -> list[str]:
    """Collect new-text strings from content / new_string / edits[].new_string."""
    texts: list[str] = []
    for key in ("content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            texts.append(value)
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            value = edit.get("new_string") if isinstance(edit, dict) else None
            if isinstance(value, str):
                texts.append(value)
    return texts


def _repo_rel(repo_root: Path, file_path: str) -> str | None:
    """Repo-relative posix path, tolerant of backslash separators; None if outside."""
    p = file_path.replace("\\", "/")
    root = repo_root.resolve().as_posix().rstrip("/")
    if p.lower().startswith(root.lower() + "/"):
        rel = p[len(root) + 1 :]
    elif p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        return None
    else:
        rel = p
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _post_edit_text(existing: str, tool_input: dict, texts: list[str]) -> str:
    """Best-effort post-edit text so citations split across old/new are caught."""
    old = tool_input.get("old_string")
    new = tool_input.get("new_string")
    if existing and isinstance(old, str) and old and isinstance(new, str):
        return existing.replace(old, new, 1)
    return "\n".join(texts)


def _citation_deny(repo_root: Path, file_path: str, tool_input: dict) -> dict:
    """Deny payload when new text adds a disposable citation to an authored doc."""
    from dummyindex.context.domains.docguard.citations import (
        added_citations,
        is_durable_doc,
    )

    rel = _repo_rel(repo_root, file_path)
    if rel is None or not is_durable_doc(rel):
        return {}
    texts = _new_texts(tool_input)
    if sum(len(t) for t in texts) > MAX_SCAN_CHARS:
        return {}
    try:
        existing = (repo_root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        existing = ""
    added = added_citations(existing, _post_edit_text(existing, tool_input, texts))
    if not added:
        return {}
    cited = ", ".join(f".context/{c}" for c in added)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{rel} is durable authored documentation but the new text cites "
                f"disposable workspace {cited}. Proposals and audits are deleted "
                "after closeout; state the fact itself instead of linking to them."
            ),
        }
    }


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
