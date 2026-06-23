"""`dummyindex context debt` — technical-debt ledger over the repo's Python source.

Answers: "where does this repo carry ``# TODO:`` / ``# FIXME:`` / ``# HACK:`` /
``# DEBT:`` debt, and which entries declare an upgrade *trigger* versus none?"

The harvest is **deterministic — no LLM in the loop** (see
``context.domains.debt``). This module is the thin CLI boundary: it parses
flags, calls the harvester, renders a per-file markdown ledger (or the stable
JSON structure), and prints it.

I/O contract (mirrors ``cli/query.py`` — stdout by default; spec D1):

- **Default:** print the markdown ledger to stdout.
- ``--write``: ALSO persist the markdown ledger to ``.context/debt.md`` (whether
  that file is committed is the host repo's ``.context/`` policy, not ours).
- ``--json``: emit the ``DebtLedger.to_dict()`` stable structure to stdout
  instead of markdown. ``--write`` still persists the *markdown* view — the
  on-disk ledger is always the human-readable one.

Every rendered row is **repo-relative POSIX** (the harvester relativizes the
path) so the output is reproducible across machines and never leaks a home dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .common import parse_path_and_root, resolve_context_root

# Where ``--write`` persists the rendered ledger, relative to the context dir.
_LEDGER_FILENAME = "debt.md"


def run(args: list[str]) -> int:
    """`dummyindex context debt [--write] [--json]` — render the debt ledger."""
    from dummyindex.context.domains.debt import harvest_debt

    scope, explicit_root, rest = parse_path_and_root(args)

    as_json = False
    do_write = False
    leftover: list[str] = []
    for a in rest:
        if a == "--json":
            as_json = True
        elif a == "--write":
            do_write = True
        else:
            leftover.append(a)

    if leftover:
        print(
            f"error: unknown argument(s) for `debt`: {leftover}",
            file=sys.stderr,
        )
        return 2

    project_root = resolve_context_root(scope, explicit_root=explicit_root)
    ledger = harvest_debt(project_root)

    # The persisted file is always the human-readable markdown ledger, even
    # when stdout is JSON — the on-disk ledger is the human view (spec D1).
    markdown = render_markdown(ledger)
    if do_write:
        _persist(project_root / ".context", markdown)

    print(render_json(ledger) if as_json else markdown, end="")
    return 0


def render_markdown(ledger) -> str:
    """Render a :class:`DebtLedger` as the markdown the CLI prints by default.

    Rows are grouped by file (path-sorted, already so from the harvester) with
    a ``## <path>`` heading per group; within a group rows stay in line order.
    Each row reads ``- path:line — <ceiling>. upgrade: <trigger>.`` and a
    no-trigger row gets a trailing ``no-trigger`` tag instead of an
    ``upgrade:`` clause. The body ends with the
    ``N markers, M with no trigger.`` tally; an empty ledger prints the
    no-debt message instead.
    """
    if not ledger.rows:
        return "# debt ledger\n\n_No debt markers found in the repo's Python source._\n"

    lines: list[str] = ["# debt ledger", ""]
    current_path: str | None = None
    for row in ledger.rows:
        if row.rel_path != current_path:
            if current_path is not None:
                lines.append("")  # blank line between file groups
            current_path = row.rel_path
            lines.append(f"## `{current_path}`")
            lines.append("")
        lines.append(_render_row(row))

    lines.append("")
    lines.append(f"{ledger.total} markers, {ledger.no_trigger_count} with no trigger.")
    return "\n".join(lines).rstrip() + "\n"


def _render_row(row) -> str:
    """Render one :class:`DebtRow` as a single markdown list item.

    ``- path:line — <ceiling>. upgrade: <trigger>.`` for a triggered row;
    ``- path:line — <ceiling>. no-trigger.`` for a no-trigger row (an empty
    ceiling renders ``(no detail)`` so the dash never dangles).
    """
    ceiling = row.ceiling or "(no detail)"
    head = f"- {row.rel_path}:{row.line} — {ceiling}."
    if row.no_trigger:
        return f"{head} no-trigger."
    return f"{head} upgrade: {row.trigger}."


def render_json(ledger) -> str:
    """Render the ledger's stable ``to_dict()`` structure as indented JSON."""
    import json

    return json.dumps(ledger.to_dict(), indent=2) + "\n"


def _persist(context_dir: Path, markdown: str) -> None:
    """Write the rendered markdown ledger to ``.context/debt.md`` (``--write``).

    Creates the context dir if absent, mirroring how the other CLI boundaries
    (e.g. ``plan_update``'s badge cache) ensure their target dir exists before
    writing. Unlike the best-effort badge cache, a ``--write`` the user asked
    for surfaces its failure rather than swallowing it.
    """
    from dummyindex.context.domains.atomic_io import write_text_atomic

    context_dir.mkdir(parents=True, exist_ok=True)
    write_text_atomic(context_dir / _LEDGER_FILENAME, markdown)
