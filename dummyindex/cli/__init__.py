"""`dummyindex context <subcommand>` dispatcher.

Wired in from ``dummyindex/__main__.py``. Each subcommand is a sibling
module (or subpackage) exporting ``run(argv: list[str]) -> int`` — multi-
handler modules export ``run_<verb>`` siblings (``enrich.run_plan``,
``audit.run_log``, …).

Public surface (kept stable for `__main__` and tests):

- ``dispatch(argv)`` — top-level entry point.
- ``resolve_context_root`` — scope/root resolution helper (used in tests).
"""
from __future__ import annotations

import sys
from typing import Callable

from dummyindex.context.enums import ContextSubcommand

from . import (
    audit,
    bootstrap,
    build_loop,
    check,
    config,
    conventions,
    council,
    council_batch,
    debt,
    dev_pick,
    doc_reorg,
    enrich,
    equip,
    features,
    hooks,
    init,
    memory,
    onboard,
    plan_update,
    preflight,
    propose,
    query,
    reality_check,
    rebuild,
    reconcile,
    reconcile_gate,
    refresh,
    status,
    statusline,
)
from .common import _FLAGS_TAKING_VALUE, resolve_context_root
from .help import USAGE, usage_for

__all__ = ["dispatch", "resolve_context_root"]


def _wants_help(rest: list[str]) -> bool:
    """True when ``-h``/``--help`` appears as a *flag* (not a flag's value).

    Mirrors argparse's "help wins everywhere" behaviour. A token immediately
    after a ``_FLAGS_TAKING_VALUE`` member is normally its value and is skipped
    — but **help wins even there**: if that value is itself ``-h``/``--help`` we
    treat it as a help request. ``_FLAGS_TAKING_VALUE`` is a single global set,
    so it can't know that ``--status`` is council-log's value flag yet build's
    boolean verb; biasing to help means ``build --status --help`` still shows
    help instead of silently swallowing it. The only cost is the pathological
    "pass the literal string ``--help`` as a flag value" case — a non-use-case.
    """
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in ("-h", "--help"):
            return True
        if tok in _FLAGS_TAKING_VALUE:
            if i + 1 < len(rest) and rest[i + 1] in ("-h", "--help"):
                return True  # help wins over being read as this flag's value
            i += 2  # skip this flag's value
            continue
        i += 1
    return False


_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]] = {
    ContextSubcommand.INIT: init.run,
    ContextSubcommand.REBUILD: rebuild.run,
    ContextSubcommand.BOOTSTRAP: bootstrap.run,
    ContextSubcommand.CHECK: check.run,
    ContextSubcommand.HOOKS: hooks.run,
    ContextSubcommand.ENRICH_PLAN: enrich.run_plan,
    ContextSubcommand.ENRICH_APPLY: enrich.run_apply,
    ContextSubcommand.FEATURES_RENAME: features.run_rename,
    ContextSubcommand.FEATURES_MERGE: features.run_merge,
    ContextSubcommand.FLOW_REMOVE: features.run_flow_remove,
    ContextSubcommand.SECTION_WRITE: features.run_section_write,
    ContextSubcommand.SCAFFOLD_FEATURE: features.run_scaffold,
    ContextSubcommand.ASSIGN_FILES: features.run_assign_files,
    ContextSubcommand.UNASSIGN_FILES: features.run_unassign_files,
    ContextSubcommand.FEATURES_REMOVE: features.run_remove,
    ContextSubcommand.MARK_ENRICHED: features.run_mark_enriched,
    ContextSubcommand.RECONCILE: reconcile.run,
    ContextSubcommand.RECONCILE_STAMP: reconcile.run_stamp,
    ContextSubcommand.COUNCIL_LOG: council.run,
    ContextSubcommand.COUNCIL_BATCH: council_batch.run,
    ContextSubcommand.CONVENTIONS_WRITE: conventions.run,
    ContextSubcommand.REFRESH_INDEXES: refresh.run,
    ContextSubcommand.QUERY: query.run,
    ContextSubcommand.REALITY_CHECK: reality_check.run,
    ContextSubcommand.PLAN_UPDATE: plan_update.run,
    ContextSubcommand.RECONCILE_GATE: reconcile_gate.run,
    ContextSubcommand.DEV_PICK: dev_pick.run,
    ContextSubcommand.ONBOARD: onboard.run,
    ContextSubcommand.CONFIG: config.run,
    ContextSubcommand.PREFLIGHT: preflight.run,
    ContextSubcommand.DOC_REORG: doc_reorg.run,
    ContextSubcommand.MEMORY: memory.run,
    ContextSubcommand.PROPOSE: propose.run,
    ContextSubcommand.EQUIP: equip.run,
    ContextSubcommand.BUILD: build_loop.run,
    ContextSubcommand.AUDIT: audit.run,
    ContextSubcommand.AUDIT_LOG: audit.run_log,
    ContextSubcommand.STATUS: status.run,
    ContextSubcommand.DEBT: debt.run,
    ContextSubcommand.STATUSLINE: statusline.run,
}


def dispatch(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    subcmd, rest = argv[0], argv[1:]
    try:
        sub = ContextSubcommand(subcmd)
    except ValueError:
        print(f"error: unknown context subcommand '{subcmd}'", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    # Help wins everywhere: a `-h`/`--help` anywhere in the subcommand's args
    # prints that subcommand's usage and returns 0 BEFORE the handler's
    # mandatory-flag parsing or any side effect runs (the bare-equip-mutates
    # hazard lived exactly here). Read-only, never touches the filesystem.
    if _wants_help(rest):
        print(usage_for(sub))
        return 0
    return _HANDLERS[sub](rest)
