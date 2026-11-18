"""`dummyindex context requirements check|sync|gate|bypass`: the required-setup CLI.

Each verb reads the Claude config dir, the skill-family stamp and the CLI version,
then calls the ``context.domains.requirements`` domain. Domain imports stay inside
the functions: ``gate`` runs on every prompt and must start fast.

Root resolution: ``--root`` > ``$CLAUDE_PROJECT_DIR`` > cwd.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from dummyindex.context.enums import RequirementsVerb

from .common import parse_path_and_root

if TYPE_CHECKING:
    from dummyindex.context.default_plugins import WiredClass, WiredEntry
    from dummyindex.context.domains.requirements import RequirementRow

_USAGE = "usage: dummyindex context requirements check|sync|gate|bypass ..."
_BYPASS_HOURS_RANGE = (1, 24)


def run(args: list[str]) -> int:
    if not args:
        print(f"error: {_USAGE}", file=sys.stderr)
        return 2
    try:
        verb = RequirementsVerb(args[0])
    except ValueError:
        print(
            f"error: unknown requirements verb {args[0]!r} "
            "(expected check|sync|gate|bypass)",
            file=sys.stderr,
        )
        return 2
    handlers = {
        RequirementsVerb.CHECK: _check,
        RequirementsVerb.SYNC: _sync,
        RequirementsVerb.GATE: _gate,
        RequirementsVerb.BYPASS: _bypass,
    }
    return handlers[verb](args[1:])


def project_root(explicit_root: Path | None) -> Path:
    """``--root`` > ``$CLAUDE_PROJECT_DIR`` > cwd."""
    if explicit_root is not None:
        return explicit_root.resolve()
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def skill_present(root: Path, name: str) -> bool:
    """A project skill counts as wired when its ``SKILL.md`` exists in either host dir."""
    return any(
        (root / base / name / "SKILL.md").is_file()
        for base in (".claude/skills", ".agents/skills")
    )


def classify_wired(entry: WiredEntry, *, root: Path) -> WiredClass:
    """``classify_wired_entry`` with skill targets checked against disk.

    Settings only record plugins, so a skill target is satisfied by its
    ``SKILL.md`` on disk and needs the user otherwise.
    """
    from dummyindex.context.default_plugins import (
        WiredClass,
        WiredKind,
        _already_decided,
    )
    from dummyindex.context.default_plugins import (
        classify_wired_entry as classify_entry,
    )

    if entry.kind is WiredKind.SKILL:
        if skill_present(root, entry.target):
            return WiredClass.SATISFIED
        return WiredClass.NEEDS_USER
    return classify_entry(
        entry, is_present=lambda target: _already_decided(root, target)
    )


def _config_path(root: Path) -> Path:
    from dummyindex.context.domains.requirements import CONFIG_TOML_REL

    return root / CONFIG_TOML_REL


def _claude_config_dir() -> Path:
    from dummyindex.context.domains.memory.miner.resolve import (
        resolve_claude_config_dir,
    )

    return resolve_claude_config_dir()


def _family_stamp(root: Path) -> str | None:
    """The first non-empty Claude skill-family stamp (user scope is read first)."""
    from dummyindex.context.cli.check import _read_skill_stamps

    for label, stamp in _read_skill_stamps(root):
        if "Claude" in label and stamp:
            return stamp
    return None


def _cli_version() -> str:
    from dummyindex.context.domains.config import current_dummyindex_version

    return current_dummyindex_version()


def _check(args: list[str]) -> int:
    _, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if rest:
        print(
            f"error: unknown argument(s) for `requirements check`: {rest}",
            file=sys.stderr,
        )
        return 2

    from dummyindex.context.domains.requirements import (
        RequirementKind,
        RequirementRow,
        RequirementsError,
        RequirementStatus,
        check_requirements,
        exit_code,
        read_requirements,
    )

    root = project_root(explicit_root)
    try:
        requirements = read_requirements(_config_path(root))
    except RequirementsError as exc:
        # An invalid config is a reported state, not a crash: one row, exit 0.
        invalid = RequirementRow(
            kind=RequirementKind.DUMMYINDEX,
            name="config.toml",
            status=RequirementStatus.INVALID,
            reason=str(exc),
            fix="fix .context/config.toml",
        )
        _print_rows((invalid,), as_json=as_json)
        return 0
    if requirements is None:
        if as_json:
            print("[]")
        else:
            print(
                "no .context/config.toml — no requirements declared, nothing to check."
            )
        return 0

    rows = check_requirements(
        root,
        requirements,
        claude_config_dir=_claude_config_dir(),
        family_stamp=_family_stamp(root),
        cli_version=_cli_version(),
    )
    _print_rows(rows, as_json=as_json)
    return exit_code(rows)


def _print_rows(rows: tuple[RequirementRow, ...], *, as_json: bool) -> None:
    if as_json:
        payload = [
            {
                "kind": row.kind.value,
                "name": row.name,
                "status": row.status.value,
                "reason": row.reason,
                "fix": row.fix,
            }
            for row in rows
        ]
        print(json.dumps(payload, indent=2))
        return
    for row in rows:
        line = f"{row.status.value:<18} {row.kind.value}: {row.name}"
        if row.reason:
            line += f" — {row.reason}"
        if row.fix and row.status.value != "satisfied":
            line += f" (fix: {row.fix})"
        print(line)


def _sync(args: list[str]) -> int:
    _, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    approve = "--yes" in rest
    local_only = "--local-only" in rest
    rest = [a for a in rest if a not in ("--yes", "--local-only")]
    if rest:
        print(
            f"error: unknown argument(s) for `requirements sync`: {rest}",
            file=sys.stderr,
        )
        return 2

    from dummyindex.context.default_plugins import default_runner
    from dummyindex.context.domains.requirements import (
        RequirementsError,
        read_requirements,
        sync_requirements,
    )

    root = project_root(explicit_root)
    try:
        requirements = read_requirements(_config_path(root))
    except RequirementsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if requirements is None:
        print("no .context/config.toml — no requirements declared, nothing to sync.")
        return 0

    family_stamp = _family_stamp(root)
    report = sync_requirements(
        root,
        requirements,
        approve=approve,
        local_only=local_only,
        runner=default_runner,
        confirm=_confirm if sys.stdin.isatty() else None,
        claude_config_dir=_claude_config_dir(),
        family_stamp=family_stamp,
    )
    for name in report.installed:
        print(f"installed: {name}")
    for name, reason in report.skipped:
        print(f"skipped: {name} — {reason}")
    for name, message in report.errors:
        print(f"error: {name} — {message}", file=sys.stderr)
    for path in report.adapters_kept:
        print(f"kept: {path}")
    if report.adapters_written:
        print("restart Claude Code to load new agents")
    return 1 if report.errors else 0


def _confirm(question: str) -> bool:
    """Ask an untrusted-plugin question. ``question`` already ends in ``[y/N]``.

    EOF or Ctrl-C reads as No, so an interrupted sync never installs anything.
    """
    try:
        answer = input(question)
    except (EOFError, KeyboardInterrupt, OSError):
        return False
    return answer.strip().lower() in ("y", "yes")


def _gate(args: list[str]) -> int:
    """UserPromptSubmit hook. Fail-open: any error exits 0, silently."""
    try:
        _, explicit_root, _ = parse_path_and_root(args, take_positional=False)
        root = project_root(explicit_root)
        if not _config_path(root).exists():
            return 0
        from dummyindex.context.domains.requirements import run_gate

        stdin_text = sys.stdin.read()
        output = run_gate(
            root,
            stdin_text,
            claude_config_dir=_claude_config_dir(),
            family_stamp=_family_stamp(root),
            cli_version=_cli_version(),
            env=os.environ,
        )
    except Exception as exc:  # noqa: BLE001 - the hook must never block a prompt
        print(f"requirements gate skipped: {exc}", file=sys.stderr)
        return 0
    if output:
        print(output)
    return 0


def _bypass(args: list[str]) -> int:
    _, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    hours = _parse_hours(rest)
    if hours is None:
        return 2

    from dummyindex.context.domains.requirements import write_bypass

    root = project_root(explicit_root)
    path = write_bypass(root, hours, now=datetime.now(timezone.utc))
    print(f"requirements bypass set for {hours}h: {path}")
    return 0


def _parse_hours(rest: list[str]) -> int | None:
    low, high = _BYPASS_HOURS_RANGE
    if "--hours" not in rest or rest.index("--hours") + 1 >= len(rest):
        print("error: `requirements bypass` needs --hours N", file=sys.stderr)
        return None
    raw = rest[rest.index("--hours") + 1]
    try:
        hours = int(raw)
    except ValueError:
        print(f"error: --hours must be an integer, got {raw!r}", file=sys.stderr)
        return None
    if not low <= hours <= high:
        print(f"error: --hours must be {low}-{high}, got {hours}", file=sys.stderr)
        return None
    return hours
