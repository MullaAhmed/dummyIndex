"""`dummyindex context build --proposal S <verb>` — grounded execution.

Deterministic STATE management over a proposal's ``checklist.md``. The CLI
is wire-only: it parses args, calls the ``buildloop`` domain, and prints.
The actual agent dispatch (Task tool) + verify-before-tick discipline live
in the ``dummyindex-build`` skill, not here. The ``--next``/``--next-wave``
handlers live in the ``_build_next`` sibling (file-size discipline); this
module keeps arg parsing + ``--check``/``--status``.

Verbs (exactly one per call):

- ``--next [--json]``      print the first unchecked item, the equipment item
                           it maps to (or ``general-purpose`` fallback), and
                           the grounding paths to inject into the agent.
- ``--next-wave [--json]`` print EVERY unchecked item in the earliest
                           incomplete wave (``## Wave N`` group in
                           ``checklist.md``), each with its own equipment
                           mapping — the parallel-dispatch frontier. On a
                           flat (ungrouped) checklist this is exactly the
                           single ``--next`` item.
- ``--check "<item>"``     atomically flip that item (text substring or
                           index) to ``- [x]``. Idempotent.
- ``--status [--json]``    print done/total; when complete, print the
                           reconcile next step.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dummyindex.context.domains.buildloop import ChecklistItem

from ._next import _RECONCILE_HINT, _do_next, _do_next_wave
from .._common import _resolve_context_root


def _pull_flag_value(rest: list[str], name: str) -> tuple[str | None, list[str]]:
    """Strip a single ``--name VALUE`` / ``--name=VALUE`` out of ``rest``.

    Returns ``(value_or_None, remaining)``. Local to this subcommand so we
    never mutate the shared ``_FLAGS_TAKING_VALUE`` table in ``_common``.
    """
    value: str | None = None
    out: list[str] = []
    i = 0
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    while i < len(rest):
        a = rest[i]
        if a == long_flag and i + 1 < len(rest):
            value = rest[i + 1]
            i += 2
        elif a.startswith(eq_prefix):
            value = a.split("=", 1)[1]
            i += 1
        else:
            out.append(a)
            i += 1
    return value, out


def _cmd_build(args: list[str]) -> int:
    from dummyindex.context.domains.buildloop import BuildLoopError, parse_checklist

    # Parse flags locally. We do NOT use `_parse_path_and_root` here because
    # `--status` is one of this subcommand's boolean verbs but is also in the
    # shared `_FLAGS_TAKING_VALUE` table (council-log's `--status STATE`), so the
    # shared parser would swallow the token after `--status` (e.g. `--root`).
    rest = list(args)
    root_value, rest = _pull_flag_value(rest, "root")
    proposal, rest = _pull_flag_value(rest, "proposal")
    check_value, rest = _pull_flag_value(rest, "check")

    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    # List membership is exact-token, so `--next-wave` never aliases `--next`.
    want_wave = "--next-wave" in rest
    rest = [a for a in rest if a != "--next-wave"]
    want_next = "--next" in rest
    rest = [a for a in rest if a != "--next"]
    want_status = "--status" in rest
    rest = [a for a in rest if a != "--status"]

    if rest:
        print(f"error: unknown argument(s) for `build`: {rest}", file=sys.stderr)
        return 2

    if not proposal:
        print("error: build requires --proposal <slug>", file=sys.stderr)
        return 2

    verbs = sum((want_next, want_wave, check_value is not None, want_status))
    if verbs == 0:
        print(
            "error: build requires one verb: --next, --next-wave, "
            "--check <item>, or --status",
            file=sys.stderr,
        )
        return 2
    if verbs > 1:
        print(
            "error: build takes exactly one verb "
            "(--next | --next-wave | --check | --status)",
            file=sys.stderr,
        )
        return 2

    explicit_root = Path(root_value) if root_value else None
    out_root = _resolve_context_root(Path("."), explicit_root=explicit_root)
    context_dir = out_root / ".context"
    proposal_dir = context_dir / "proposals" / proposal
    checklist_path = proposal_dir / "checklist.md"

    try:
        items = parse_checklist(checklist_path)
    except BuildLoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if check_value is not None:
        return _do_check(checklist_path, check_value)
    if want_status:
        return _do_status(items, proposal, as_json=as_json)
    handler = _do_next_wave if want_wave else _do_next
    return handler(items, proposal, proposal_dir, context_dir, as_json=as_json)


def _do_check(checklist_path: Path, key: str) -> int:
    from dummyindex.context.domains.buildloop import BuildLoopError, flip_item

    try:
        item = flip_item(checklist_path, key)
    except BuildLoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"build check: [x] #{item.index} {item.text}")
    return 0


def _do_status(items: tuple[ChecklistItem, ...], proposal: str, *, as_json: bool) -> int:
    from dummyindex.context.domains.buildloop import counts

    done, total = counts(items)
    complete = total > 0 and done == total
    if as_json:
        payload = {
            "proposal": proposal,
            "done": done,
            "total": total,
            "complete": complete,
            "next_step": _RECONCILE_HINT if complete else None,
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(f"build status [{proposal}]: {done}/{total} done")
    if complete:
        print(
            "all items checked — close the loop by reconciling the new code "
            f"into .context/ (council/65-reconcile.md):\n  {_RECONCILE_HINT}"
        )
    return 0
