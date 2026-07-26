"""`dummyindex context graph <verb>` — bounded queries over the symbol graph.

Wire-only, per the CLI contract: parse flags, delegate to
``context.domains.graph_query``, print, return an exit code.

- ``0`` — the query was answered (a valid empty answer counts: zero
  callers is exactly what ``dead-code`` hunts for)
- ``1`` — nothing to answer: unknown or ambiguous symbol, no path
  between the endpoints, empty community
- ``2`` — usage error, or no ``features/symbol-graph.json`` to query
"""

from __future__ import annotations

import sys

from .common import parse_path_and_root, resolve_context_root, usage_error

_VERBS = "callers-of|callees-of|impact|path|neighbors|dead-code|community"
_INT_FLAGS = {"--limit": "limit", "--depth": "depth", "--hops": "hops"}


def run(args: list[str]) -> int:
    """`dummyindex context graph <verb> [SYMBOL...]` — query the symbol graph."""
    from dummyindex.context.domains.graph_query import (
        DEFAULT_DEAD_CODE_LIMIT,
        DEFAULT_IMPACT_DEPTH,
        DEFAULT_LIMIT,
        DEFAULT_NEIGHBOR_HOPS,
        AmbiguousSymbolError,
        GraphArtifactInvalidError,
        GraphArtifactMissingError,
        GraphVerb,
        UnknownSymbolError,
        callees_of,
        callers_of,
        community,
        dead_code,
        impact,
        load_symbol_graph,
        neighbors,
        path_between,
        render_json,
        render_markdown,
        resolve_symbol,
    )

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)

    as_json = False
    ints: dict[str, int] = {}
    positionals: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--json":
            as_json = True
            i += 1
            continue
        flag = a.split("=", 1)[0]
        if flag in _INT_FLAGS:
            if "=" in a:
                raw, consumed = a.split("=", 1)[1], 1
            elif i + 1 < len(rest):
                raw, consumed = rest[i + 1], 2
            else:
                return usage_error("graph", f"{flag} requires an integer value")
            try:
                value = int(raw)
            except ValueError:
                return usage_error("graph", f"{flag} must be an integer, got {raw!r}")
            if value < 1:
                return usage_error("graph", f"{flag} must be >= 1, got {value}")
            ints[_INT_FLAGS[flag]] = value
            i += consumed
            continue
        if a.startswith("--"):
            return usage_error("graph", f"unknown flag: {a}")
        positionals.append(a)
        i += 1

    if not positionals:
        return usage_error(
            "graph",
            f"usage: dummyindex context graph <{_VERBS}> "
            "[SYMBOL] [SYMBOL2] [--limit N] [--depth N] [--hops N] [--json]",
        )
    try:
        verb = GraphVerb(positionals[0])
    except ValueError:
        return usage_error(
            "graph",
            f"unknown graph verb {positionals[0]!r} (expected {_VERBS})",
        )
    operands = positionals[1:]

    arity = {
        GraphVerb.CALLERS_OF: 1,
        GraphVerb.CALLEES_OF: 1,
        GraphVerb.IMPACT: 1,
        GraphVerb.PATH: 2,
        GraphVerb.NEIGHBORS: 1,
        GraphVerb.DEAD_CODE: 0,
        GraphVerb.COMMUNITY: 1,
    }[verb]
    if len(operands) != arity:
        return usage_error(
            "graph",
            f"`graph {verb.value}` takes {arity} positional argument(s), "
            f"got {len(operands)}",
        )
    if "depth" in ints and verb is not GraphVerb.IMPACT:
        return usage_error("graph", "--depth only applies to `impact`")
    if "hops" in ints and verb is not GraphVerb.NEIGHBORS:
        return usage_error("graph", "--hops only applies to `neighbors`")

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    try:
        graph = load_symbol_graph(out_root / ".context")
    except GraphArtifactMissingError as exc:
        print(
            f"error: {exc} — run `dummyindex ingest` "
            "(or `dummyindex context rebuild --changed`) first.",
            file=sys.stderr,
        )
        return 2
    except GraphArtifactInvalidError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    limit = ints.get("limit")
    try:
        if verb is GraphVerb.CALLERS_OF:
            result = callers_of(
                graph,
                resolve_symbol(graph, operands[0]),
                limit=limit or DEFAULT_LIMIT,
            )
        elif verb is GraphVerb.CALLEES_OF:
            result = callees_of(
                graph,
                resolve_symbol(graph, operands[0]),
                limit=limit or DEFAULT_LIMIT,
            )
        elif verb is GraphVerb.IMPACT:
            result = impact(
                graph,
                resolve_symbol(graph, operands[0]),
                depth=ints.get("depth", DEFAULT_IMPACT_DEPTH),
                limit=limit or DEFAULT_LIMIT,
            )
        elif verb is GraphVerb.PATH:
            result = path_between(
                graph,
                resolve_symbol(graph, operands[0]),
                resolve_symbol(graph, operands[1]),
                limit=limit or DEFAULT_LIMIT,
            )
        elif verb is GraphVerb.NEIGHBORS:
            result = neighbors(
                graph,
                resolve_symbol(graph, operands[0]),
                hops=ints.get("hops", DEFAULT_NEIGHBOR_HOPS),
                limit=limit or DEFAULT_LIMIT,
            )
        elif verb is GraphVerb.DEAD_CODE:
            result = dead_code(graph, limit=limit or DEFAULT_DEAD_CODE_LIMIT)
        else:
            result = community(graph, operands[0], limit=limit or DEFAULT_LIMIT)
    except AmbiguousSymbolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        for candidate in exc.candidates:
            print(f"  {candidate}", file=sys.stderr)
        if exc.total > len(exc.candidates):
            print(f"  … and {exc.total - len(exc.candidates)} more", file=sys.stderr)
        return 1
    except UnknownSymbolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(render_json(result) if as_json else render_markdown(result), end="")
    if verb in (GraphVerb.PATH, GraphVerb.COMMUNITY) and not result.rows:
        return 1
    return 0
