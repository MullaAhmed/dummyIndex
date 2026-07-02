"""`dummyindex context migrate-docs` — relocate stray planning docs (wire-only).

Capability 1 of the managed-doc-home feature, on the CLI side. Detects
planning-doc markdown that leaked outside `.context/` (under `docs/`) and
relocates each stray into its managed home — `.context/proposals/<slug>/`
(spec/plan) or `.context/audits/<slug>/` (report) — preserving git history and
minting a valid `proposal.json`.

This module is *wire-only*, mirroring `cli/gc.py`: it lazy-imports the
`context.domains.docguard.migrate` domain **inside** `run` (the layering rule —
`cli` imports the domain, never the reverse), drives the three domain steps
(`enumerate_strays` → `plan_moves` → `apply_moves`), prints, and returns an exit
code. No move mechanics live here — containment, clobber-protection, and the
git/non-git branch all sit in `context/domains/docguard/migrate.py`.

Behaviour:

- **Dry-run by default** (no `--yes`): list the planned relocations grouped by
  slug + target home in deterministic sorted order, plus any skips, and move
  **nothing** (exit 0).
- `--yes`: relocate the strays and print what moved + what was skipped (exit 0).
- `--force`: fill only *missing* files in an existing managed home — the domain
  enforces it; the CLI just threads the flag through.
- `--json`: emit a stable, exact-keyset payload (a fixed top-level key set plus a
  fixed per-group / per-move / per-skip key set, mirroring `gc status --json`).

One bad stray is skipped + reported by the domain (a `MoveSkip`), never raised;
a whole-plan guard refusal (a containment escape or unsafe slug) aborts before
anything moves and surfaces as exit 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .common import resolve_context_root, usage_error

if TYPE_CHECKING:  # annotations only — no runtime domain import (layering)
    from dummyindex.context.domains.docguard.models import MovePlan, MoveResult

_MIGRATE_USAGE = (
    "usage: dummyindex context migrate-docs [--root DIR] [--yes] [--force] [--json]"
)


def run(args: list[str]) -> int:
    """`dummyindex context migrate-docs [--root DIR] [--yes] [--force] [--json]`.

    `-h`/`--help` is intercepted at the dispatcher (`cli/__init__`), so it never
    reaches here. Dry-run unless `--yes`; a missing `.context/` is a clean usage
    error (migration relocates *into* `.context/`, so it must already exist).
    """
    from dummyindex.context.domains.audit import AuditSlugError
    from dummyindex.context.domains.docguard.errors import MigrationError
    from dummyindex.context.domains.docguard.migrate import (
        apply_moves,
        enumerate_strays,
        plan_moves,
    )
    from dummyindex.context.domains.proposals import ProposalSlugError

    values, flags, err = _parse_flags(
        args, value_keys={"root"}, bool_keys={"yes", "force", "json"}
    )
    if err is not None:
        return usage_error("migrate-docs", err)

    context_dir, missing = _context_dir(values.get("root"))
    if missing:
        return _missing_context(context_dir)

    repo_root = context_dir.parent
    force = "force" in flags
    yes = "yes" in flags

    try:
        groups = enumerate_strays(repo_root, context_dir)
        plan = plan_moves(repo_root, context_dir, groups, force=force)
        result = apply_moves(plan, yes=yes, force=force)
    except (MigrationError, ProposalSlugError, AuditSlugError) as exc:
        # A whole-plan guard refusal (containment escape / unsafe slug) aborts
        # the transactional plan *before* anything moved — surface it, exit 2,
        # never crash the process.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if "json" in flags:
        print(json.dumps(_migrate_payload(plan, result), indent=2))
    else:
        _print_migrate(plan, result)
    return 0


# ----- rendering ------------------------------------------------------------


def _migrate_payload(plan: MovePlan, result: MoveResult) -> dict:
    """The `migrate-docs --json` payload — a stable, exact key set.

    The grouped shape is driven by the *plan* (the intended relocations, already
    in deterministic sorted order) with each move's `method` overlaid from the
    *result* when it actually executed (empty on a dry-run, `git-mv` / `replace`
    / `replace+add` once applied). `skipped` carries every reported non-move.
    """
    methods = _method_index(result)
    return {
        "dry_run": result.dry_run,
        "groups": [
            {
                "slug": group.slug,
                "kind": group.kind.value,
                "home": group.home_rel,
                "title": group.title,
                "moves": [
                    {
                        "source": move.source_rel,
                        "target": move.target_rel,
                        "method": methods.get(
                            (move.source_rel, move.target_rel), move.method
                        ),
                    }
                    for move in group.moves
                ],
            }
            for group in plan.groups
        ],
        "skipped": [
            {
                "slug": skip.slug,
                "kind": skip.kind.value,
                "target": skip.target_rel,
                "reason": skip.reason,
            }
            for skip in result.skipped
        ],
    }


def _print_migrate(plan: MovePlan, result: MoveResult) -> None:
    """Human-readable plan/result, groups sorted by slug + target home."""
    groups = plan.groups
    skipped = result.skipped

    if not groups and not skipped:
        suffix = " (dry-run)" if result.dry_run else ""
        print(f"context migrate-docs{suffix}: nothing to migrate")
        return

    methods = _method_index(result)
    if result.dry_run:
        moves = sum(len(g.moves) for g in groups)
        print(
            f"context migrate-docs (dry-run): {len(groups)} group(s), "
            f"{moves} move(s), {len(skipped)} skip(s)"
        )
    else:
        print(
            f"context migrate-docs: moved {len(result.moved)} file(s), "
            f"{len(skipped)} skip(s)"
        )

    for group in groups:
        print(f"  {group.kind.value:8} {group.slug} → {group.home_rel}")
        for move in group.moves:
            method = methods.get((move.source_rel, move.target_rel))
            tag = f"  [{method}]" if method else ""
            print(f"    {move.source_rel} → {move.target_rel}{tag}")

    if skipped:
        print("  skipped:")
        for skip in skipped:
            print(
                f"    {skip.kind.value:8} {skip.slug} ({skip.target_rel}): {skip.reason}"
            )

    if result.dry_run:
        print("  pass --yes to relocate (nothing moved)")


def _method_index(result: MoveResult) -> dict[tuple[str, str], str]:
    """`(source_rel, target_rel) -> method` for every executed move."""
    return {(m.source_rel, m.target_rel): m.method for m in result.moved}


# ----- root / flag helpers (mirrors cli/gc.py) ------------------------------


def _context_dir(root: str | None) -> tuple[Path, bool]:
    """Resolve the `.context/` dir + whether it is missing.

    Mirrors `gc.py:_context_dir`: an explicit `--root` wins, else the enclosing
    repo is found from cwd. Returns `(context_dir, missing)`.
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
    """Parse `--key value` / `--key=value` / `--flag` arguments.

    A sibling of `cli/gc.py:_parse_flags` (same shape, no repeatable flags).
    Returns `(values, flags, error)`; `error` is a message on a malformed /
    unknown argument, else None.
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
