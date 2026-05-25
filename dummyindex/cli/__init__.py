"""`dummyindex context <subcommand>` dispatcher.

Wired in from ``dummyindex/__main__.py``. Each subcommand is a sibling
module exporting a single ``run(argv: list[str]) -> int`` function (here
referenced by historical name ``_cmd_<name>`` for diff continuity).

Public surface (kept stable for `__main__` and tests):

- ``dispatch(argv)`` — top-level entry point.
- ``_resolve_context_root`` — scope/root resolution helper (used in tests).
"""
from __future__ import annotations

import sys
from typing import Callable

from dummyindex.context.enums import ContextSubcommand

from ._common import _resolve_context_root
from ._usage import _USAGE

from .bootstrap import _cmd_bootstrap
from .check import _cmd_check
from .conventions import _cmd_conventions_write
from .council import _cmd_council_log
from .enrich import _cmd_enrich_apply, _cmd_enrich_plan
from .features import (
    _cmd_features_merge,
    _cmd_features_rename,
    _cmd_flow_remove,
    _cmd_section_write,
)
from .hooks import _cmd_hooks
from .init import _cmd_init
from .query import _cmd_query
from .reality_check import _cmd_reality_check
from .rebuild import _cmd_rebuild
from .refresh import _cmd_refresh_indexes

__all__ = ["_resolve_context_root", "dispatch"]


_HANDLERS: dict[ContextSubcommand, Callable[[list[str]], int]] = {
    ContextSubcommand.INIT: _cmd_init,
    ContextSubcommand.REBUILD: _cmd_rebuild,
    ContextSubcommand.BOOTSTRAP: _cmd_bootstrap,
    ContextSubcommand.CHECK: _cmd_check,
    ContextSubcommand.HOOKS: _cmd_hooks,
    ContextSubcommand.ENRICH_PLAN: _cmd_enrich_plan,
    ContextSubcommand.ENRICH_APPLY: _cmd_enrich_apply,
    ContextSubcommand.FEATURES_RENAME: _cmd_features_rename,
    ContextSubcommand.FEATURES_MERGE: _cmd_features_merge,
    ContextSubcommand.FLOW_REMOVE: _cmd_flow_remove,
    ContextSubcommand.SECTION_WRITE: _cmd_section_write,
    ContextSubcommand.COUNCIL_LOG: _cmd_council_log,
    ContextSubcommand.CONVENTIONS_WRITE: _cmd_conventions_write,
    ContextSubcommand.REFRESH_INDEXES: _cmd_refresh_indexes,
    ContextSubcommand.QUERY: _cmd_query,
    ContextSubcommand.REALITY_CHECK: _cmd_reality_check,
}


def dispatch(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    subcmd, rest = argv[0], argv[1:]
    try:
        sub = ContextSubcommand(subcmd)
    except ValueError:
        print(f"error: unknown context subcommand '{subcmd}'", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    return _HANDLERS[sub](rest)
