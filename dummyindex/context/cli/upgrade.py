"""`dummyindex context upgrade [--if-stale] [--root DIR]`: bring `.context/` to the installed CLI.

The SessionStart hook runs `--if-stale` every session. The stale check reads only
`meta.json` and returns before the upgrade pipeline is imported, so a current
index costs no heavy import and writes nothing.

Root resolution: `--root` > `$CLAUDE_PROJECT_DIR` > cwd.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .common import parse_path_and_root, usage_error
from .requirements import project_root

if TYPE_CHECKING:
    from dummyindex.context.build.context_upgrade import UpgradeReport

_LOCK_WARNING = "upgrade in progress"
_RESTART_HINT = "restart Claude Code to load new agents"


def run(args: list[str]) -> int:
    _, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    unknown = [a for a in rest if a != "--if-stale"]
    if unknown:
        return usage_error("upgrade", f"unknown argument(s) for `upgrade`: {unknown}")

    from dummyindex.context.build.context_upgrade import is_stale, upgrade_project
    from dummyindex.context.domains.config import current_dummyindex_version
    from dummyindex.context.git import run_git

    root = project_root(explicit_root)
    version = current_dummyindex_version()
    if "--if-stale" in rest and not is_stale(root / ".context", version):
        return 0
    report = upgrade_project(root, package_version=version, runner=run_git)
    return _print_report(report, version)


def _print_report(report: UpgradeReport, version: str) -> int:
    if _LOCK_WARNING in report.warnings:
        print(_LOCK_WARNING)
        return 0
    # Only a clean run advances the stamp, so only a clean run is "upgraded".
    if report.changed and not report.errors:
        print(f"dummyindex: upgraded .context/ to {version}")
    if report.adapters_written:
        print(_RESTART_HINT)
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if report.errors else 0
