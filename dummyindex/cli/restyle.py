"""`dummyindex context restyle plan|begin|next|done|stamp|status`: the ASD-STE100 rewrite loop.

Wire-only: parse argv, lazy-import the restyle domain, print, return the exit code.
Domain errors are printed and exit 1; usage errors exit 2.
"""

from __future__ import annotations

import json
import sys

from .common import usage_error
from .maintain import _context_dir, _missing_context, _parse_flags

_RESTYLE_USAGE = (
    "usage: dummyindex context restyle plan|begin|next|done|stamp|status ..."
)
_VERBS = ("plan", "begin", "next", "done", "stamp", "status")


def run(args: list[str]) -> int:
    """`dummyindex context restyle <verb> ...`; ``-h`` is handled by the dispatcher."""
    if not args:
        print(f"error: {_RESTYLE_USAGE}", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    if verb not in _VERBS:
        print(
            f"error: unknown restyle verb {verb!r} (expected {'|'.join(_VERBS)})",
            file=sys.stderr,
        )
        return 2
    return _HANDLERS[verb](rest)


def _load(args: list[str], value_keys: set[str], bool_keys: set[str], verb: str):
    """Shared flag parse + context resolve; returns ``(values, flags, context_dir, rc)``."""
    values, flags, err = _parse_flags(
        args, value_keys=value_keys | {"root"}, bool_keys=bool_keys | {"json"}
    )
    if err is not None:
        return None, None, None, usage_error("restyle", f"{err} (for `restyle {verb}`)")
    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return None, None, None, _missing_context(context_dir)
    return values, flags, context_dir, None


def _restyle_error(exc: Exception) -> int:
    print(f"error: {exc}", file=sys.stderr)
    return 1


def _plan(args: list[str]) -> int:
    """`restyle plan [--json] [--root DIR]` — read-only."""
    from dummyindex.context.domains.restyle.errors import RestyleError
    from dummyindex.context.domains.restyle.run import plan

    values, flags, context_dir, rc = _load(args, set(), set(), "plan")
    if rc is not None:
        return rc
    try:
        result = plan(context_dir)
    except RestyleError as exc:
        return _restyle_error(exc)
    if "json" in flags:
        payload = {
            "status": result.status,
            "ruleset": result.ruleset,
            "doc_count": result.doc_count,
            "strict": result.strict,
            "advice": result.advice,
            "units": [
                {
                    "unit_id": u.unit_id,
                    "docs": list(u.docs),
                    "strict": u.strict,
                    "advice": u.advice,
                }
                for u in result.units
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0
    if result.status == "already_restyled":
        print(f"already restyled (ruleset {result.ruleset})")
        return 0
    if result.status == "nothing_to_restyle":
        print("nothing to restyle")
        return 0
    print(
        f"restyle plan: {len(result.units)} unit(s), {result.doc_count} doc(s), "
        f"strict {result.strict}, advice {result.advice}"
    )
    for unit in result.units:
        print(
            f"  {unit.unit_id}: {len(unit.docs)} doc(s), strict {unit.strict}, "
            f"advice {unit.advice}"
        )
    return 0


def _pull_max_units(values: dict[str, str]) -> tuple[int | None, str | None]:
    raw = values.get("max-units")
    if raw is None:
        return None, None
    try:
        n = int(raw)
    except ValueError:
        return None, "--max-units must be an integer"
    if n < 1:
        return None, "--max-units must be >= 1"
    return n, None


def _begin(args: list[str]) -> int:
    """`restyle begin --all | --max-units N [--force] [--json] [--root DIR]`."""
    from dummyindex.context.domains.restyle.errors import RestyleError
    from dummyindex.context.domains.restyle.run import begin

    values, flags, context_dir, rc = _load(
        args, {"max-units"}, {"all", "force"}, "begin"
    )
    if rc is not None:
        return rc
    max_units, err = _pull_max_units(values)
    if err is not None:
        return usage_error("restyle", f"{err} (for `restyle begin`)")
    try:
        result = begin(
            context_dir,
            all_units="all" in flags,
            max_units=max_units,
            force="force" in flags,
        )
    except RestyleError as exc:
        return _restyle_error(exc)
    if "json" in flags:
        print(
            json.dumps(
                {
                    "run": result.run_dir.name,
                    "units": list(result.units),
                    "doc_count": result.doc_count,
                },
                indent=2,
            )
        )
        return 0
    print(f"restyle begin: {result.run_dir.name}")
    print(f"  {len(result.units)} unit(s), {result.doc_count} doc(s)")
    for unit_id in result.units:
        print(f"    {unit_id}")
    print("  drive it with `restyle next`; resume any time from state.json.")
    return 0


def _next(args: list[str]) -> int:
    """`restyle next [--run NAME] [--json] [--root DIR]` — the next unit to rewrite."""
    from dummyindex.context.domains.restyle.errors import RestyleError
    from dummyindex.context.domains.restyle.run import next_unit

    values, flags, context_dir, rc = _load(args, {"run"}, set(), "next")
    if rc is not None:
        return rc
    try:
        unit = next_unit(context_dir, values.get("run"))
    except RestyleError as exc:
        return _restyle_error(exc)
    if "json" in flags:
        payload = None
        if unit is not None:
            payload = {
                "unit_id": unit.unit_id,
                "docs": [str(doc) for doc in unit.docs],
                "brief": unit.brief,
            }
        print(json.dumps({"unit": payload}, indent=2))
        return 0
    if unit is None:
        print(
            "restyle next: complete — all units done. "
            "Run `dummyindex context restyle stamp`."
        )
        return 0
    print(f"restyle next: {unit.unit_id}")
    for doc in unit.docs:
        print(f"  doc: {doc}")
    print("brief:")
    print(unit.brief)
    return 0


def _done(args: list[str]) -> int:
    """`restyle done <unit> [--run NAME] [--json] [--root DIR]`."""
    from dummyindex.context.domains.restyle.errors import (
        DocTokenLossError,
        RestyleError,
    )
    from dummyindex.context.domains.restyle.run import done

    if not args or args[0].startswith("--"):
        return usage_error("restyle", "unit id is required (for `restyle done`)")
    unit, rest = args[0], args[1:]
    values, flags, context_dir, rc = _load(rest, {"run"}, set(), "done")
    if rc is not None:
        return rc
    try:
        result = done(context_dir, unit, values.get("run"))
    except DocTokenLossError as exc:
        if "json" in flags:
            print(
                json.dumps(
                    {
                        "error": str(exc),
                        "losses": [
                            {"doc": doc, "token": token} for doc, token in exc.losses
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
            for doc, token in exc.losses:
                print(f"  {doc}: lost {token}", file=sys.stderr)
        return 1
    except RestyleError as exc:
        return _restyle_error(exc)
    if "json" in flags:
        print(
            json.dumps(
                {
                    "unit_id": result.unit_id,
                    "strict": [
                        {
                            "doc": doc,
                            "line": v.line,
                            "rule": v.rule,
                            "excerpt": v.excerpt,
                        }
                        for doc, v in result.strict
                    ],
                    "advice": [
                        {
                            "doc": doc,
                            "line": v.line,
                            "rule": v.rule,
                            "excerpt": v.excerpt,
                        }
                        for doc, v in result.advice
                    ],
                    "added": [{"doc": doc, "token": t} for doc, t in result.added],
                },
                indent=2,
            )
        )
        return 0
    print(f"restyle done: {result.unit_id}")
    for doc, v in result.strict:
        print(f"  strict {doc}:{v.line}: {v.rule} {v.excerpt}")
    print(f"  strict remaining: {len(result.strict)}")
    for doc, v in result.advice:
        print(f"advice: {doc}:{v.line}: {v.rule} {v.excerpt}")
    for doc, token in result.added:
        print(f"warning: {doc} gained protected token {token}")
    return 0


def _stamp(args: list[str]) -> int:
    """`restyle stamp [--run NAME] [--json] [--root DIR]` — record the ruleset."""
    from dummyindex.context.domains.restyle.errors import RestyleError
    from dummyindex.context.domains.restyle.run import stamp

    values, flags, context_dir, rc = _load(args, {"run"}, set(), "stamp")
    if rc is not None:
        return rc
    try:
        result = stamp(context_dir, values.get("run"))
    except RestyleError as exc:
        return _restyle_error(exc)
    if "json" in flags:
        print(
            json.dumps({"ruleset": result.ruleset, "docs": list(result.docs)}, indent=2)
        )
        return 0
    print(
        f"restyle stamp: ruleset {result.ruleset}, {len(result.docs)} doc(s) restyled"
    )
    return 0


def _status(args: list[str]) -> int:
    """`restyle status [--run NAME] [--json] [--root DIR]`."""
    from dummyindex.context.domains.restyle.errors import RestyleError
    from dummyindex.context.domains.restyle.run import status

    values, flags, context_dir, rc = _load(args, {"run"}, set(), "status")
    if rc is not None:
        return rc
    try:
        counts = status(context_dir, values.get("run"))
    except RestyleError as exc:
        return _restyle_error(exc)
    if "json" in flags:
        print(json.dumps(counts, indent=2))
        return 0
    print(
        f"restyle status: {counts['done']}/{counts['total']} done, "
        f"{counts['pending']} pending, {counts['skipped']} skipped"
    )
    return 0


_HANDLERS = {
    "plan": _plan,
    "begin": _begin,
    "next": _next,
    "done": _done,
    "stamp": _stamp,
    "status": _status,
}
