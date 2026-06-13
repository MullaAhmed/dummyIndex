"""Argument parsing + scope/root resolution shared by every subcommand.

`resolve_context_root` is re-exported from `dummyindex.cli` for tests
that exercise the scope/root rules directly.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def resolve_context_root(scope: Path, *, explicit_root: Optional[Path] = None,
                          cwd: Optional[Path] = None) -> Path:
    """Decide where `.context/` and `CLAUDE.md` live for a given scope.

    Rule:
    - If `explicit_root` is given, use it.
    - If `scope` was passed as an **absolute path**, treat it as both scan
      target and project root (the user typed a full path on purpose).
    - If `scope` was relative and resolves to a strict subdirectory of cwd,
      the user is operating inside a project — return cwd (the enclosing
      repo root).
    - Otherwise return `scope`.

    The check on absolute-vs-relative is done on the original `Path` object
    (`scope.is_absolute()`), not on its resolved form, so callers pass the
    user's raw argument rather than `.resolve()`-ing it first.
    """
    if explicit_root is not None:
        return explicit_root.resolve()
    if scope.is_absolute():
        return scope.resolve()
    cwd = (cwd or Path.cwd()).resolve()
    # Resolve relative scope against the supplied cwd, not the live process
    # cwd — keeps the helper testable and matches what the user "meant"
    # when they typed a relative path.
    scope_resolved = (cwd / scope).resolve()
    if scope_resolved == cwd:
        return cwd
    try:
        scope_resolved.relative_to(cwd)
        return cwd  # scope is under cwd → enclosing repo
    except ValueError:
        return scope_resolved

def usage_error(subcommand: str, message: str) -> int:
    """Print a required-flag / unknown-arg error WITH a usage pointer; return 2.

    Centralises the terse-error → help-pointer pattern so every mandatory-flag
    failure tells the agent where to look (``dummyindex context <sub> --help``)
    instead of leaving it to probe by running the verb bare — the probing loop
    that, for ``equip``, used to mutate the repo. Additive to the message text
    only; the exit code stays 2.
    """
    print(f"error: {message}", file=sys.stderr)
    print(
        f"  hint: run `dummyindex context {subcommand} --help` for usage",
        file=sys.stderr,
    )
    return 2


_FLAGS_TAKING_VALUE = frozenset(
    {
        "--from", "--to", "--name", "--summary", "--from-json",
        "--feature", "--flow", "--section", "--from-file",
        "--stage", "--agent", "--status", "--note",
        "--into", "--as-section",
        "--docs",
        "--id", "--file",
        "--mode", "--cap",
    }
)


def pull_repeatable_flag(args: list[str], name: str) -> tuple[list[str], list[str]]:
    """Strip every ``--{name} VALUE`` occurrence out of ``args``.

    Supports both ``--docs PATH`` and ``--docs=PATH`` forms. Returns
    ``(values, remaining_args)``. The flag is *repeatable* — callers
    receive every value the user passed, in order.
    """
    values: list[str] = []
    rest: list[str] = []
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    i = 0
    while i < len(args):
        a = args[i]
        if a == long_flag and i + 1 < len(args):
            values.append(args[i + 1])
            i += 2
        elif a.startswith(eq_prefix):
            values.append(a.split("=", 1)[1])
            i += 1
        else:
            rest.append(a)
            i += 1
    return values, rest


def parse_path_and_root(
    args: list[str],
    *,
    take_positional: bool = True,
) -> tuple[Path, Optional[Path], list[str]]:
    """Pull the positional scope + optional `--root` out of `args`.

    Returns ``(scope, explicit_root, remaining_args)`` so callers can
    parse their own flags (e.g. `--changed`, `--from-json`) from
    ``remaining_args``.

    ``take_positional=False`` for subcommands that have no leading
    path argument (``features-rename`` only takes flags) — the helper
    then leaves every non-``--root`` token in ``remaining_args``.

    Tokens that look like values for known flags (``--from value``,
    ``--name value``, etc.) are forwarded to ``remaining_args`` as a
    pair so subcommand parsers see them in the right order.
    """
    scope = Path(".")
    explicit_root: Optional[Path] = None
    remaining: list[str] = []
    i = 0
    saw_scope = False
    while i < len(args):
        a = args[i]
        if a == "--root" and i + 1 < len(args):
            explicit_root = Path(args[i + 1])
            i += 2
        elif a.startswith("--root="):
            explicit_root = Path(a.split("=", 1)[1])
            i += 1
        elif a in _FLAGS_TAKING_VALUE and i + 1 < len(args):
            # Forward the flag *and* its value untouched so the
            # subcommand parser sees them together.
            remaining.append(a)
            remaining.append(args[i + 1])
            i += 2
        elif take_positional and not a.startswith("--") and not saw_scope:
            scope = Path(a)
            saw_scope = True
            i += 1
        else:
            remaining.append(a)
            i += 1
    return scope, explicit_root, remaining


# ----- subcommands ----------------------------------------------------------

def resolve_doc_paths(values: list[str], *, base: Path) -> list[Path]:
    """Resolve every ``--docs PATH`` value relative to ``base`` if not absolute.

    Missing paths are dropped silently with a warning to stderr — better
    to ingest with one fewer doc root than to abort the whole rebuild.
    """
    resolved: list[Path] = []
    seen: set[str] = set()
    for raw in values:
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = (base / p).resolve()
        else:
            p = p.resolve()
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.exists():
            print(
                f"warning: --docs path not found, skipping: {p}",
                file=sys.stderr,
            )
            continue
        resolved.append(p)
    return resolved

def parse_kv_flags(rest: list[str]) -> tuple[dict[str, str], list[str]]:
    """Tiny --key value parser for the council subcommands.

    Returns (parsed, leftover). Recognized keys come from
    _FLAGS_TAKING_VALUE. Boolean flags / unknown args go to leftover.
    """
    parsed: dict[str, str] = {}
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in _FLAGS_TAKING_VALUE and i + 1 < len(rest):
            parsed[a.lstrip("-")] = rest[i + 1]
            i += 2
        elif "=" in a and a.startswith("--") and a.split("=", 1)[0] in _FLAGS_TAKING_VALUE:
            k, v = a.split("=", 1)
            parsed[k.lstrip("-")] = v
            i += 1
        else:
            leftover.append(a)
            i += 1
    return parsed, leftover

