"""`dummyindex context drift-ack` — record drift rows as acknowledged.

Wire-only, following the ``cli/gc.py`` shape: parse this command's own flag
alphabet, lazy-import the domain (``context.domains.drift_acks``) *inside*
``run`` (the layering rule — ``cli`` imports the domain, never the reverse),
delegate, print, return an exit code. No suppression policy lives here —
matching/expiry is owned by the consumer (``context/drift.py``); this verb
only records and reports judgements.

Modes:

- **record** (default) — ``--feature ID [--path REL] [--reason TEXT]``:
  append one ack per file. With ``--path``, exactly that file; without it,
  every currently-drifting file of the feature (today's rows). The recorded
  sha is the git blob sha on-git, content sha256 off-git.
- ``--list [--feature ID]`` — print recorded acks (oldest first).
- ``--clear`` — drop every ack.

The modes are mutually exclusive; mixing their flags is a usage error
(exit 2), never a silent reinterpretation.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from .common import (
    parse_kv_flags,
    parse_path_and_root,
    resolve_context_root,
    usage_error,
)

_USAGE = (
    "usage: dummyindex context drift-ack [path] [--root DIR] "
    "(--feature ID [--path REL] [--reason TEXT] | --list | --clear) ..."
)


def run(args: list[str]) -> int:
    """`dummyindex context drift-ack ...`.

    ``-h``/``--help`` is intercepted at the dispatcher (``cli/__init__``), so
    it never reaches here.
    """
    scope, explicit_root, rest = parse_path_and_root(args)
    parsed, leftover = parse_kv_flags(
        rest, allowed={"--feature", "--path", "--reason"}
    )
    want_list = "--list" in leftover
    want_clear = "--clear" in leftover
    leftover = [a for a in leftover if a not in ("--list", "--clear")]
    if leftover:
        return usage_error(
            "drift-ack", f"unknown argument(s): {leftover} (for `drift-ack`)"
        )

    context_dir = _resolve_context_dir(scope, explicit_root)
    if context_dir is None:
        return 2

    if want_clear:
        if parsed or want_list:
            return _mode_conflict()
        from dummyindex.context.domains.drift_acks import clear_acks

        print(f"cleared {clear_acks(context_dir)} ack(s).")
        return 0

    if want_list:
        if "path" in parsed or "reason" in parsed:
            return _mode_conflict()
        from dummyindex.context.domains.drift_acks import read_acks

        acks = read_acks(context_dir)
        feature_id = parsed.get("feature")
        if feature_id:
            acks = [a for a in acks if a.get("feature_id") == feature_id]
        if not acks:
            target = f" for feature '{feature_id}'" if feature_id else ""
            print(f"no acks recorded{target}.")
            return 0
        for ack in acks:
            reason = f" — {ack['reason']}" if ack.get("reason") else ""
            print(
                f"- {ack.get('feature_id')}:{ack.get('path') or '*'}"
                f" @ {str(ack.get('acked_sha') or '')[:12]}{reason}"
            )
        return 0

    return _record(context_dir, parsed)


def _record(context_dir: Path, parsed: dict[str, str]) -> int:
    """Record mode: ack one file (--path) or every currently-drifting file."""
    from dummyindex.context.build.reconcile import blob_sha
    from dummyindex.context.domains.drift_acks import append_ack
    from dummyindex.context.drift import compute_drift
    from dummyindex.context.git import is_git_repo

    feature_id = parsed.get("feature")
    if not feature_id:
        return usage_error("drift-ack", "--feature ID is required (for `drift-ack`)")
    project_root = context_dir.parent

    if not (context_dir / "features" / feature_id).is_dir():
        return usage_error(
            "drift-ack", f"unknown feature {feature_id!r} (for `drift-ack`)"
        )

    rel_path = parsed.get("path")
    if rel_path:
        rels = [rel_path]
    else:
        report = compute_drift(project_root)
        rels = sorted(
            {r.rel_path for r in report.rows if r.feature_id == feature_id}
        )
        if not rels:
            print(f"nothing to ack: no drifting rows for feature '{feature_id}'.")
            return 0

    on_git = is_git_repo(project_root)
    flavor = "git blob sha" if on_git else "content sha256"
    reason = parsed.get("reason")
    recorded: list[tuple[str, str]] = []
    for rel in rels:
        try:
            data = (project_root / rel).read_bytes()
        except OSError:
            print(f"error: cannot read '{rel}' under {project_root}", file=sys.stderr)
            return 2
        sha = blob_sha(data) if on_git else hashlib.sha256(data).hexdigest()
        append_ack(
            context_dir,
            feature_id=feature_id,
            acked_sha=sha,
            path=rel,
            reason=reason,
        )
        recorded.append((rel, sha))
    for rel, sha in recorded:
        print(f"acked {feature_id}:{rel} @ {sha[:12]} ({flavor})")
    print(
        f"{len(recorded)} ack(s) recorded — suppressed while the bytes stay "
        "unchanged; any edit re-reports the row."
    )
    return 0


def _resolve_context_dir(scope: Path, explicit_root: Path | None) -> Path | None:
    """Resolve the project root's ``.context/``; hint + ``None`` when absent."""
    project_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = project_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return None
    return context_dir


def _mode_conflict() -> int:
    return usage_error(
        "drift-ack",
        "--list/--clear are exclusive modes; drop record/list flags to use them",
    )
