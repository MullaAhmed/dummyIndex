"""`dummyindex toolkit list|show|add|remove|enable|disable|install` — the GUI JSON facade.

Wire-only: parse arguments, call :mod:`dummyindex.context.domains.toolkit`, print
one JSON document (indent 2) on stdout. Failures print the error envelope
``{"error": {"code", "message"}}`` on stdout and exit non-zero: 2 for a malformed
request, 1 for an operational failure. The domain logic lives in
``context/domains/toolkit/``.

Usage (``argv`` excludes the ``toolkit`` token)::

    list [--kind K] [--scope S] [--terminal ID --out-dir DIR] [--root DIR] [--json]
    show NAME [--kind K] [--scope S] [--terminal ID --out-dir DIR] [--root DIR]
    add NAME --kind K [--scope S] [--config FILE | --file FILE | --dir DIR]
        [--mechanism M] [--terminal ID --out-dir DIR] [--root DIR]
    remove|enable|disable NAME [--kind K] [--scope S] [--terminal ID --out-dir DIR]
        [--allow-project-fallback] [--root DIR]
    install --kind K --source REF [--scope project|user] --preview | --yes --plan-hash H
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_USAGE_EXIT = 2
_FAIL_EXIT = 1


class _UsageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Parser(argparse.ArgumentParser):
    """Raises instead of printing argparse text, so every failure is an envelope."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="dummyindex toolkit", add_help=True)
    sub = parser.add_subparsers(dest="verb", parser_class=_Parser)
    sub.required = True

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--kind", choices=("mcp", "skill", "plugin"))
        p.add_argument("--scope", choices=("terminal", "project", "user"))
        p.add_argument("--terminal", dest="terminal_id")
        p.add_argument("--out-dir", type=Path)
        p.add_argument("--root", type=Path)
        p.add_argument(
            "--json", action="store_true", help="accepted; output is always JSON"
        )

    list_p = sub.add_parser("list")
    common(list_p)

    show_p = sub.add_parser("show")
    show_p.add_argument("name")
    common(show_p)

    add_p = sub.add_parser("add")
    add_p.add_argument("name")
    common(add_p)
    add_p.add_argument("--config", type=Path)
    add_p.add_argument("--file", dest="source_file", type=Path)
    add_p.add_argument("--dir", dest="source_dir", type=Path)
    add_p.add_argument(
        "--mechanism",
        choices=("mcp_additive", "mcp_exclusive", "plugin_dir", "settings", "add_dir"),
    )

    for verb in ("remove", "enable", "disable"):
        p = sub.add_parser(verb)
        p.add_argument("name")
        common(p)
        p.add_argument("--allow-project-fallback", action="store_true")

    install_p = sub.add_parser("install")
    install_p.add_argument("--kind", choices=("mcp", "skill", "plugin"), required=True)
    install_p.add_argument("--source", required=True)
    install_p.add_argument("--scope", choices=("project", "user"))
    install_p.add_argument("--root", type=Path)
    install_p.add_argument("--preview", action="store_true")
    install_p.add_argument("--yes", action="store_true")
    install_p.add_argument("--plan-hash")
    install_p.add_argument(
        "--json", action="store_true", help="accepted; output is always JSON"
    )
    return parser


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _envelope(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _dispatch(ns: argparse.Namespace) -> dict[str, Any]:
    # Imported here so `--help` and usage errors never load the domain.
    from dummyindex.context.domains.toolkit import (
        resolve_root,
        toolkit_install,
        toolkit_list,
        toolkit_mutate,
        toolkit_show,
    )

    root = resolve_root(Path.cwd(), getattr(ns, "root", None))
    home = Path.home()
    if ns.verb == "install":
        return toolkit_install(
            ns.kind,
            ns.source,
            root=root,
            home=home,
            scope=ns.scope,
            preview=ns.preview,
            yes=ns.yes,
            plan_hash=ns.plan_hash,
        )
    if ns.verb == "list":
        return toolkit_list(
            root=root,
            home=home,
            kind=ns.kind,
            scope=ns.scope,
            terminal_id=ns.terminal_id,
            out_dir=ns.out_dir,
        )
    if ns.verb == "show":
        return toolkit_show(
            ns.name,
            root=root,
            home=home,
            kind=ns.kind,
            scope=ns.scope,
            terminal_id=ns.terminal_id,
            out_dir=ns.out_dir,
        )
    return toolkit_mutate(
        ns.verb,
        ns.name,
        root=root,
        home=home,
        kind=ns.kind,
        scope=ns.scope,
        terminal_id=ns.terminal_id,
        out_dir=ns.out_dir,
        config_file=getattr(ns, "config", None),
        source_file=getattr(ns, "source_file", None),
        source_dir=getattr(ns, "source_dir", None),
        mechanism=getattr(ns, "mechanism", None),
        allow_project_fallback=getattr(ns, "allow_project_fallback", False),
    )


def run(argv: list[str]) -> int:
    """`dummyindex toolkit <verb> ...`. Returns the process exit code."""
    from dummyindex.context.domains.toolkit import ToolkitError
    from dummyindex.context.domains.toolkit.constants import USAGE_CODES

    try:
        ns = _build_parser().parse_args(argv)
    except _UsageError as exc:
        _emit(_envelope("usage", exc.message))
        return _USAGE_EXIT
    except SystemExit as exc:  # -h / --help: argparse already printed help
        return int(exc.code or 0)

    try:
        payload = _dispatch(ns)
    except ToolkitError as exc:
        _emit(_envelope(exc.code, exc.message))
        return _USAGE_EXIT if exc.code in USAGE_CODES else _FAIL_EXIT
    except OSError as exc:
        _emit(_envelope("io_error", str(exc)))
        return _FAIL_EXIT
    _emit(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual use only
    sys.exit(run(sys.argv[1:]))
