"""`dummyindex context build --proposal S <verb>` — grounded execution.

Deterministic STATE management over a proposal's ``checklist.md``. The CLI
is wire-only: it parses args, calls the ``buildloop`` domain, and prints.
The actual agent dispatch (Task tool) + verify-before-tick discipline live
in the ``dummyindex-build`` skill, not here.

Verbs (exactly one per call):

- ``--next [--json]``   print the first unchecked item, the equipment item
                        it maps to (or ``general-purpose`` fallback), and
                        the grounding paths to inject into the agent.
- ``--check "<item>"``  atomically flip that item (text substring or index)
                        to ``- [x]``. Idempotent.
- ``--status [--json]`` print done/total; when complete, print the
                        ``dummyindex context rebuild --changed`` next step.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ._common import _resolve_context_root

# Rendered agent name when no equipment item matches (fallback). The domain
# Choice stores equipment_name=None / fallback=True; this literal is the
# CLI/skill-layer render of that fallback.
_FALLBACK_AGENT = "general-purpose"

_REBUILD_HINT = "dummyindex context rebuild --changed"


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


def _load_manifest(context_dir: Path) -> list[dict]:
    """Read ``.context/equipment.json`` → its ``items`` list.

    Tolerates absence (returns ``[]`` → everything falls back). Accepts
    either a top-level list or an object with an ``items`` array, matching
    Slice B's manifest shape loosely so a schema tweak doesn't break us.
    """
    path = context_dir / "equipment.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or []
    else:
        items = []
    return [it for it in items if isinstance(it, dict)]


def _grounding_paths(proposal_dir: Path, context_dir: Path) -> tuple[str, ...]:
    """Fixed grounding set for a proposal: its spec + plan, plus the repo's
    conventions dir when present. No relevance ranking — just the anchors
    the agent must read before acting."""
    paths: list[str] = []
    for name in ("spec.md", "plan.md"):
        p = proposal_dir / name
        if p.is_file():
            paths.append(str(p))
    conventions = context_dir / "conventions"
    if conventions.is_dir():
        paths.append(str(conventions))
    return tuple(paths)


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

    verbs = sum((want_next, check_value is not None, want_status))
    if verbs == 0:
        print(
            "error: build requires one verb: --next, --check <item>, or --status",
            file=sys.stderr,
        )
        return 2
    if verbs > 1:
        print(
            "error: build takes exactly one verb (--next | --check | --status)",
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
    return _do_next(
        items,
        proposal,
        proposal_dir,
        context_dir,
        as_json=as_json,
    )


def _do_check(checklist_path: Path, key: str) -> int:
    from dummyindex.context.domains.buildloop import BuildLoopError, flip_item

    try:
        item = flip_item(checklist_path, key)
    except BuildLoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"build check: [x] #{item.index} {item.text}")
    return 0


def _do_status(items, proposal: str, *, as_json: bool) -> int:
    from dummyindex.context.domains.buildloop import counts

    done, total = counts(items)
    complete = total > 0 and done == total
    if as_json:
        payload = {
            "proposal": proposal,
            "done": done,
            "total": total,
            "complete": complete,
            "next_step": _REBUILD_HINT if complete else None,
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(f"build status [{proposal}]: {done}/{total} done")
    if complete:
        print(f"all items checked — close the loop with:\n  {_REBUILD_HINT}")
    return 0


def _do_next(
    items,
    proposal: str,
    proposal_dir: Path,
    context_dir: Path,
    *,
    as_json: bool,
) -> int:
    from dummyindex.context.domains.buildloop import map_task_to_equipment

    pending = next((it for it in items if not it.done), None)
    if pending is None:
        if as_json:
            print(json.dumps({"proposal": proposal, "item": None, "complete": True,
                              "next_step": _REBUILD_HINT}, indent=2))
            return 0
        print(f"build next [{proposal}]: all items checked.")
        print(f"close the loop with:\n  {_REBUILD_HINT}")
        return 0

    manifest = _load_manifest(context_dir)
    grounding = _grounding_paths(proposal_dir, context_dir)
    choice = map_task_to_equipment(pending.text, manifest, grounding=grounding)
    agent = choice.equipment_name if not choice.fallback else _FALLBACK_AGENT

    if as_json:
        payload = {
            "proposal": proposal,
            "item": {"index": pending.index, "text": pending.text},
            "agent": agent,
            "fallback": choice.fallback,
            "grounding": list(choice.grounding),
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"build next [{proposal}]: #{pending.index} {pending.text}")
    tag = " (fallback)" if choice.fallback else ""
    print(f"  agent: {agent}{tag}")
    if choice.grounding:
        print("  grounding:")
        for g in choice.grounding:
            print(f"    - {g}")
    else:
        print("  grounding: (none found — read spec.md/plan.md if present)")
    return 0
