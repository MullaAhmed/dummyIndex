"""`dummyindex context query` — PageIndex-style retrieval over .context/features/."""

from __future__ import annotations

import sys

from .common import parse_path_and_root, resolve_context_root, usage_error


def run(args: list[str]) -> int:
    """`dummyindex context query "..."` — PageIndex-style retrieval."""
    from dummyindex.context.domains.query import (
        _DEFAULT_BUDGET_TOKENS,
        _DEFAULT_TOP_K,
        query,
        render_json,
        render_markdown,
    )

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)

    # Pull --top-k / --budget / --json out before treating the rest as the
    # query string. The query string is everything left over, joined on
    # spaces — supports both `query "..."` and `query find auth` shapes.
    top_k = _DEFAULT_TOP_K
    budget = _DEFAULT_BUDGET_TOKENS
    as_json = False
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--json":
            as_json = True
            i += 1
        elif a == "--top-k" and i + 1 < len(rest):
            try:
                top_k = int(rest[i + 1])
            except ValueError:
                return usage_error(
                    "query", f"--top-k must be an integer, got {rest[i + 1]!r}"
                )
            i += 2
        elif a.startswith("--top-k="):
            try:
                top_k = int(a.split("=", 1)[1])
            except ValueError:
                return usage_error("query", f"--top-k must be an integer, got {a!r}")
            i += 1
        elif a == "--budget" and i + 1 < len(rest):
            try:
                budget = int(rest[i + 1])
            except ValueError:
                return usage_error(
                    "query", f"--budget must be an integer, got {rest[i + 1]!r}"
                )
            i += 2
        elif a.startswith("--budget="):
            try:
                budget = int(a.split("=", 1)[1])
            except ValueError:
                return usage_error("query", f"--budget must be an integer, got {a!r}")
            i += 1
        elif a in ("--top-k", "--budget"):
            # A value-taking flag with no value following it (trailing). Without
            # this branch it would fall through to the unknown-flag check below
            # and error there — error here instead with a value-specific message,
            # matching the integer-validation failures above. (The empty `=` form,
            # e.g. `--top-k=`, is already handled by the `startswith` arms above,
            # which raise on `int("")`.)
            return usage_error("query", f"{a} requires an integer value")
        elif a.startswith("--"):
            # An unknown flag — reject it with a usage pointer rather than
            # silently folding it into the search string (where `--bogus 5`
            # would become part of the query text and quietly return no hits).
            return usage_error("query", f"unknown flag: {a}")
        else:
            leftover.append(a)
            i += 1

    if not leftover:
        return usage_error(
            "query",
            'usage: dummyindex context query "search text" '
            "[--top-k N] [--budget N] [--json]",
        )

    query_text = " ".join(leftover).strip()
    if not query_text:
        return usage_error("query", "empty query")

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"

    try:
        result = query(context_dir, query_text, top_k=top_k, budget_tokens=budget)
    except FileNotFoundError as exc:
        print(
            f"error: {exc} not found — run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    print(render_json(result) if as_json else render_markdown(result), end="")
    # Exit non-zero when no matches so shell scripts can detect "no hit".
    return 0 if result.matches else 1
