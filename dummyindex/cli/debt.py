"""`dummyindex context debt`: technical-debt ledger over the repo's Python source.

Lists ``# TODO:`` / ``# FIXME:`` / ``# HACK:`` / ``# DEBT:`` markers and whether each
declares an upgrade *trigger*; the harvest (``context.domains.debt``) is deterministic,
no LLM. Prints the markdown ledger, or ``DebtLedger.to_dict()`` with ``--json``;
``--write`` also persists the markdown to ``.context/debt.md``. Paths are repo-relative
POSIX, so output is reproducible and never leaks a home dir.
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

    One ``## <path>`` group per file (path-sorted), rows in line order (format in
    :func:`_render_row`), then the ``N markers, M with no trigger.`` tally; an
    empty ledger prints the no-debt message instead.
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
