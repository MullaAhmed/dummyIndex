"""`dummyindex context gc <verb>` — the context-hygiene GC CLI (wire-only).

Sub-dispatches the first positional verb (``status|delete|stamp|signal``) the
same way ``cli/audit.py`` dispatches ``start|show``: parse this command's own
flag alphabet, lazy-import the ``context.domains.gc`` domain *inside* ``run``
(the layering rule — ``cli`` imports the domain, never the reverse), call a
domain function, print, and return an exit code. No business logic lives here;
the sweep / anchor / delete logic all sits in ``context/domains/gc/``.

The four verbs:

- ``status [--json] [--root DIR]`` — read-only sweep report (``gc.scan``).
- ``delete --kind proposal|audit (--slug S|--path P) [--yes] [--allow-untracked]
  [--force-partial] [--root DIR]`` — without ``--yes`` a dry-run that deletes
  nothing; with ``--yes`` the bounded ``gc.delete_workspace``.
- ``stamp [--to SHA] [--root DIR]`` — advance the committed GC anchor.
- ``signal [--json] [--root DIR]`` — the SessionStart throttle probe (consumes
  the per-session fire-once memo via ``gc.should_signal``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import resolve_context_root, usage_error

_GC_USAGE = "usage: dummyindex context gc status|delete|stamp|signal ..."


def run(args: list[str]) -> int:
    """`dummyindex context gc status|delete|stamp|signal ...`.

    ``-h``/``--help`` is intercepted at the dispatcher (``cli/__init__``), so it
    never reaches here.
    """
    if not args:
        print(f"error: {_GC_USAGE}", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    if verb == "status":
        return _gc_status(rest)
    if verb == "delete":
        return _gc_delete(rest)
    if verb == "stamp":
        return _gc_stamp(rest)
    if verb == "signal":
        return _gc_signal(rest)
    print(
        f"error: unknown gc verb {verb!r} (expected status|delete|stamp|signal)",
        file=sys.stderr,
    )
    return 2


def _gc_status(args: list[str]) -> int:
    """`gc status [--json] [--root DIR]` — read-only sweep report (exit 0)."""
    from dummyindex.context.domains.gc import scan

    values, flags, err = _parse_flags(args, value_keys={"root"}, bool_keys={"json"})
    if err is not None:
        return usage_error("gc", f"{err} (for `gc status`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    root = context_dir.parent
    report = scan(context_dir, root)

    if "json" in flags:
        print(json.dumps(_status_payload(report), indent=2))
    else:
        _print_status(report)
    return 0


def _gc_delete(args: list[str]) -> int:
    """`gc delete --kind K (--slug S|--path P) [--yes] [...]`.

    Without ``--yes``: prints the dry-run target and deletes nothing (exit 0).
    With ``--yes``: runs the bounded ``delete_workspace`` and prints the result.
    A recoverability *refusal* still exits 0 (a guard outcome, not a usage
    error); a slug / sentinel / path / liveness violation maps to exit 2.
    """
    from dummyindex.context.domains.audit import AuditSlugError
    from dummyindex.context.domains.gc import (
        CandidateKind,
        GcPathError,
        GcTargetError,
        delete_workspace,
    )
    from dummyindex.context.domains.proposals import ProposalSlugError

    values, flags, err = _parse_flags(
        args,
        value_keys={"kind", "slug", "path", "root"},
        bool_keys={"yes", "allow-untracked", "force-partial"},
    )
    if err is not None:
        return usage_error("gc", f"{err} (for `gc delete`)")

    kind_raw = values.get("kind")
    if not kind_raw:
        return usage_error("gc", "--kind proposal|audit is required (for `gc delete`)")
    kind = _resolve_kind(kind_raw, CandidateKind)
    if kind is None:
        return usage_error(
            "gc", f"--kind must be proposal|audit, got {kind_raw!r} (for `gc delete`)"
        )

    slug = values.get("slug")
    path = values.get("path")
    if not slug and not path:
        return usage_error(
            "gc", "one of --slug S / --path P is required (for `gc delete`)"
        )
    if slug and path:
        return usage_error("gc", "pass only one of --slug / --path (for `gc delete`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    target_label = f"--slug {slug}" if slug else f"--path {path}"
    if "yes" not in flags:
        print(f"context gc delete (dry-run): would delete {kind.value} {target_label}")
        print("  pass --yes to delete (nothing removed)")
        return 0

    try:
        result = delete_workspace(
            context_dir,
            kind=kind,
            slug=slug,
            path=path,
            allow_untracked="allow-untracked" in flags,
            force_partial="force-partial" in flags,
        )
    except (ProposalSlugError, AuditSlugError, GcTargetError, GcPathError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.deleted:
        print(f"context gc delete: removed {kind.value} {target_label}")
    elif result.refused:
        print(f"context gc delete: refused — {result.reason}")
    else:
        print(f"context gc delete: {result.reason or 'nothing to delete'}")
    return 0


def _gc_stamp(args: list[str]) -> int:
    """`gc stamp [--to SHA] [--root DIR]` — advance the GC anchor (exit 0)."""
    from dummyindex.context.domains.gc import stamp_gc

    values, _flags, err = _parse_flags(args, value_keys={"to", "root"}, bool_keys=set())
    if err is not None:
        return usage_error("gc", f"{err} (for `gc stamp`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    stamped = stamp_gc(context_dir, context_dir.parent, to=values.get("to"))
    if stamped is None:
        print("context gc stamp: off-git (no HEAD to anchor) — no-op")
    else:
        print(f"context gc stamp: anchored at {stamped}")
    return 0


def _gc_signal(args: list[str]) -> int:
    """`gc signal [--json] [--root DIR]` — SessionStart throttle probe (exit 0).

    Prints the one-line nudge iff over threshold and not already signalled this
    session; silent otherwise. Always exit 0 (it is a hook probe, never a usage
    failure surface).
    """
    from dummyindex.context.domains.gc import should_signal
    from dummyindex.context.domains.memory.transcript import resolve_session_id

    values, flags, err = _parse_flags(args, value_keys={"root"}, bool_keys={"json"})
    if err is not None:
        return usage_error("gc", f"{err} (for `gc signal`)")

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        # A missing .context/ is just "nothing to nudge" for a hook probe.
        if "json" in flags:
            print(json.dumps({"should_signal": False}))
        return 0

    session_id = resolve_session_id() or ""
    fire = should_signal(context_dir, context_dir.parent, session_id)

    if "json" in flags:
        print(json.dumps({"should_signal": fire}))
        return 0
    if fire:
        from dummyindex.context.domains.gc import gc_commits_since

        count = gc_commits_since(context_dir, context_dir.parent)
        print(f"{count} commits since last hygiene sweep — run /dummyindex-gc")
    return 0


# ----- status rendering -----------------------------------------------------


def _status_payload(report: object) -> dict:
    """The `gc status --json` payload (proposal-free, stable key set)."""
    return {
        "candidates": [
            {
                "kind": c.kind.value,
                "slug": c.slug,
                "rel_path": c.rel_path,
                "status": c.status,
                "signals": list(c.signals),
                "tracked": c.tracked,
                "age_days": c.age_days,
            }
            for c in report.candidates  # type: ignore[attr-defined]
        ],
        "anchor": report.anchor,  # type: ignore[attr-defined]
        "commits_since": report.commits_since,  # type: ignore[attr-defined]
        "threshold": report.threshold,  # type: ignore[attr-defined]
        "should_signal": report.should_signal,  # type: ignore[attr-defined]
        "anchor_orphaned": report.anchor_orphaned,  # type: ignore[attr-defined]
    }


def _print_status(report: object) -> None:
    """Human-readable `gc status` table."""
    candidates = report.candidates  # type: ignore[attr-defined]
    print(f"context gc status: {len(candidates)} candidate(s)")
    for c in candidates:
        signals = ", ".join(c.signals) or "(none)"
        print(f"  {c.kind.value:9} {c.slug}")
        print(f"    {c.rel_path}  [{signals}]")
    anchor = report.anchor or "(unset)"  # type: ignore[attr-defined]
    commits = report.commits_since  # type: ignore[attr-defined]
    commits_str = "n/a (off-git / no anchor)" if commits is None else str(commits)
    print(
        f"  anchor={anchor} commits_since={commits_str} "
        f"threshold={report.threshold} "  # type: ignore[attr-defined]
        f"should_signal={report.should_signal}"  # type: ignore[attr-defined]
    )
    if report.anchor_orphaned:  # type: ignore[attr-defined]
        print(
            "  warning: recorded anchor is unknown to the repo "
            "(history rewrite) — re-baseline with `gc stamp --to HEAD`"
        )


# ----- helpers --------------------------------------------------------------


def _resolve_kind(kind_raw: str, candidate_kind: type) -> object | None:
    """Map a ``--kind`` value (``proposal``/``audit``) to a ``CandidateKind``.

    Only the two user-facing kinds are accepted; the enum's internal members
    (``orphan_scaffold`` / ``archived``) are never selectable on the CLI.
    """
    try:
        kind = candidate_kind(kind_raw)
    except ValueError:
        return None
    if kind not in (candidate_kind.PROPOSAL, candidate_kind.AUDIT):
        return None
    return kind


def _context_dir(root: str | None) -> tuple[Path, bool]:
    """Resolve the ``.context/`` dir + whether it is missing.

    Mirrors ``propose``'s root resolution + existence check: an explicit
    ``--root`` wins, else the enclosing repo is found from cwd. Returns
    ``(context_dir, missing)`` so each verb decides how a missing index reads
    (usage error for the read/write verbs; a quiet no-op for ``signal``).
    """
    explicit_root = Path(root) if root else None
    out_root = resolve_context_root(Path("."), explicit_root=explicit_root)
    context_dir = out_root / ".context"
    return context_dir, not context_dir.is_dir()


def _missing_context(context_dir: Path) -> int:
    """Print the standard missing-`.context/` error and return exit 2."""
    print(
        f"error: {context_dir} not found. Run `dummyindex ingest` first.",
        file=sys.stderr,
    )
    return 2


def _parse_flags(
    args: list[str],
    *,
    value_keys: set[str],
    bool_keys: set[str],
) -> tuple[dict[str, str], set[str], str | None]:
    """Parse ``--key value`` / ``--key=value`` / ``--flag`` arguments.

    A trimmed cousin of ``cli/audit.py:_parse_flags`` (no repeatable flags —
    gc has none). Returns ``(values, flags, error)``; ``error`` is a message on
    a malformed / unknown argument, else None. Boolean flag names keep their
    dashes (``allow-untracked``) so the caller membership-tests on the raw key.
    """
    values: dict[str, str] = {}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return values, flags, f"unexpected argument: {token!r}"
        if "=" in token:
            name, inline_value = token[2:].split("=", 1)
            has_inline = True
        else:
            name, inline_value = token[2:], None
            has_inline = False

        if name in bool_keys:
            if has_inline:
                return values, flags, f"--{name} takes no value"
            flags.add(name)
            i += 1
            continue

        if name in value_keys:
            if has_inline:
                values[name] = inline_value or ""
                i += 1
            else:
                if i + 1 >= len(args):
                    return values, flags, f"--{name} requires a value"
                values[name] = args[i + 1]
                i += 2
            continue

        return values, flags, f"unknown argument: --{name}"
    return values, flags, None
