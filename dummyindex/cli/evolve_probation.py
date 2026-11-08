"""`dummyindex context evolve attribute|probation` — probation lifecycle CLI (wire-only)."""

from __future__ import annotations

import json
import sys

from .common import usage_error

DISABLED = "evolution disabled (DUMMYINDEX_EVOLUTION)"
PROTOCOL = "probation-protocol.md"
_VERDICTS = ("attributed", "unrelated", "unknown")
_SUBVERBS = ("report", "promote", "demote")


def run_attribute(args: list[str]) -> int:
    """`evolve attribute --next [--json]` or `evolve attribute --event ID --verdict V ...`."""
    from .evolve import _context_dir, _missing_context, _parse_flags

    values, flags, err = _parse_flags(
        args,
        value_keys={"root", "event", "verdict", "item"},
        bool_keys={"next", "json", "durable", "retracts"},
    )
    if err is not None:
        return usage_error("evolve attribute", err)

    from dummyindex.context.domains.evolve_gate import EvolveError
    from dummyindex.context.domains.observe import (
        evolution_enabled,
        record_attribution,
        resolution_packet,
    )
    from dummyindex.context.domains.probation import sync

    if not evolution_enabled():
        print(DISABLED)
        return 0
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()

    try:
        if "next" in flags or not values.get("event"):
            packet = resolution_packet(context_dir)
            if packet is None:
                print("nothing to attribute")
                return 0
            print(
                json.dumps({**packet, "protocol": PROTOCOL}, sort_keys=True, indent=2)
            )
            return 0

        verdict = values.get("verdict")
        if verdict not in _VERDICTS:
            return usage_error(
                "evolve attribute",
                "--verdict must be attributed|unrelated|unknown",
            )
        if "retracts" in flags and (verdict != "attributed" or not values.get("item")):
            return usage_error(
                "evolve attribute",
                "--retracts needs --verdict attributed and --item ITEM (bare --retracts)",
            )
        row = record_attribution(
            context_dir,
            values["event"],
            verdict=verdict,
            item=values.get("item"),
            durable="durable" in flags,
            retracts="retracts" in flags,
        )
        sync(context_dir, probes=True)
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(row, sort_keys=True, indent=2))
    return 0


def run_probation(args: list[str]) -> int:
    """`evolve probation report [--json]|promote [--item ID]...|demote --item ID`."""
    from .evolve import _context_dir, _missing_context, _parse_flags

    if not args or args[0] not in _SUBVERBS:
        return usage_error("evolve probation", "expected report|promote|demote")
    verb, rest = args[0], args[1:]

    ids: list[str] = []
    passthrough: list[str] = []
    i = 0
    while i < len(rest):
        token = rest[i]
        if token == "--item":
            if i + 1 >= len(rest):
                return usage_error("evolve probation", "--item requires a value")
            ids.append(rest[i + 1])
            i += 2
            continue
        if token.startswith("--item="):
            ids.append(token.split("=", 1)[1])
            i += 1
            continue
        passthrough.append(token)
        i += 1
    if any(not item for item in ids):
        return usage_error("evolve probation", "--item requires a non-empty ID")

    values, flags, err = _parse_flags(
        passthrough, value_keys={"root"}, bool_keys={"json"}
    )
    if err is not None:
        return usage_error("evolve probation", err)
    if verb == "demote" and len(ids) != 1:
        return usage_error("evolve probation", "demote needs exactly one --item ID")

    from dummyindex.context.domains.evolve_gate import EvolveError
    from dummyindex.context.domains.observe import evolution_enabled
    from dummyindex.context.domains.probation import (
        demote,
        format_promote,
        format_report,
        promote,
        report,
        sync,
    )

    if not evolution_enabled():
        print(DISABLED)
        return 0
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()

    try:
        sync(context_dir, probes=True)
        if verb == "report":
            data = report(context_dir)
            if "json" in flags:
                print(json.dumps(data, sort_keys=True, indent=2))
            else:
                print(format_report(data))
            return 0
        if verb == "promote":
            results = promote(context_dir, ids or None)
            print(format_promote(results))
            return 0
        result = demote(context_dir, ids[0])
        print(json.dumps(result, sort_keys=True, indent=2))
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
