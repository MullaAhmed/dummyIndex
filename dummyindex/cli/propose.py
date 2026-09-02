"""`dummyindex context propose` — scaffold a consistency-checked proposal.

Wire-only: parse ``--slug`` / ``--title`` / ``--root`` / ``--force`` /
``--route k=v``, resolve the ``.context/`` root, then hand off to the
proposals domain (``ensure_proposal`` → ``scan_consistency`` →
``apply_consistency``) and print the resulting path + related features.

``--route k=v`` (repeatable; keys: implementer|auditor|decisions, values a
ModelChoice alias like sonnet/opus/current) records the optional model-
routing block in the scaffolded ``proposal.json``. Validation is centralised
in the buildloop domain (``parse_route_flags``) so propose and build reject
exactly the same inputs.

``--slug`` and ``--title`` are propose-specific value flags, so this module
parses its own arguments rather than going through the shared
``parse_path_and_root`` / ``parse_kv_flags`` helpers (which only know the
flag alphabet used by the older subcommands).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .common import resolve_context_root

# Value-bearing flags this subcommand understands.
_VALUE_FLAGS = ("--slug", "--title", "--root")


def run(args: list[str]) -> int:
    """`dummyindex context propose --slug S --title "..." [--route K=V]... [--root DIR] [--force]`."""
    from dummyindex.context.domains.buildloop import (
        BuildLoopError,
        parse_route_flags,
    )
    from dummyindex.context.domains.proposals import (
        ProposalExistsError,
        ProposalSlugError,
        apply_consistency,
        ensure_proposal,
        proposal_dir,
        scan_consistency,
        set_routing,
    )

    parsed, routes, force, error = _parse_propose_args(args)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2

    slug = parsed.get("slug")
    title = parsed.get("title")
    if not slug or not title:
        print(
            "error: --slug <slug> and --title <text> are both required",
            file=sys.stderr,
        )
        return 2

    try:
        routing = parse_route_flags(routes)
    except BuildLoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    explicit_root = Path(parsed["root"]) if parsed.get("root") else None
    out_root = resolve_context_root(Path("."), explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        written = ensure_proposal(context_dir, slug, title, force=force)
    except ProposalSlugError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ProposalExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    hits = scan_consistency(context_dir, title)
    apply_consistency(context_dir, slug, hits)

    # Routing is written LAST (a raw-JSON merge): apply_consistency
    # round-trips proposal.json through the Proposal dataclass, which has no
    # routing field and would drop the key on rewrite.
    if routing:
        set_routing(context_dir, slug, routing)

    target = proposal_dir(context_dir, slug)
    print(f"context propose: {target} ({len(written)} files)")
    if routing:
        models = ", ".join(f"{key}={value}" for key, value in routing.items())
        print(f"  routing: {models}")
    if hits.related_features:
        print(f"  related features: {', '.join(hits.related_features)}")
    else:
        print("  related features: (none detected)")
    if hits.conventions:
        print(f"  conventions:      {', '.join(hits.conventions)}")
    return 0


def _parse_propose_args(
    args: list[str],
) -> tuple[dict[str, str], list[str], bool, str | None]:
    """Parse ``--slug``/``--title``/``--root`` (value) + repeatable
    ``--route k=v`` + ``--force`` (bool).

    Returns ``(parsed, routes, force, error)``; ``error`` is a message
    string on a malformed argument, else None. Route tokens are collected
    verbatim here and validated by ``parse_route_flags`` in ``run``.
    """
    parsed: dict[str, str] = {}
    routes: list[str] = []
    force = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--force":
            force = True
            i += 1
            continue
        matched = False
        for flag in _VALUE_FLAGS:
            key = flag.lstrip("-")
            if a == flag:
                if i + 1 >= len(args):
                    return parsed, routes, force, f"{flag} requires a value"
                parsed[key] = args[i + 1]
                i += 2
                matched = True
                break
            if a.startswith(flag + "="):
                parsed[key] = a.split("=", 1)[1]
                i += 1
                matched = True
                break
        if matched:
            continue
        if a == "--route":
            if i + 1 >= len(args):
                return parsed, routes, force, "--route requires a k=v value"
            routes.append(args[i + 1])
            i += 2
            continue
        if a.startswith("--route="):
            routes.append(a.split("=", 1)[1])
            i += 1
            continue
        return parsed, routes, force, f"unknown argument for `propose`: {a!r}"
    return parsed, routes, force, None
