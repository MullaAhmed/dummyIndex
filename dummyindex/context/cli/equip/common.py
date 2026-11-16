"""Shared plumbing for the ``equip`` subcommand's split modules.

Private to the equip subcommand pair (``equip.py`` + ``_equip_verbs.py``), the
way ``_migrate.py`` is private to init/rebuild: local flag parsing (never the
shared ``parse_path_and_root`` — its ``_FLAGS_TAKING_VALUE`` table would
mis-handle equip's flags) and root resolution. The fresh-render helpers live in
the domain (``context/domains/equip/generate/fresh.py``); they are re-exported
here so CLI callers keep their import path.
"""

from __future__ import annotations

from pathlib import Path

from dummyindex.context.domains.equip.generate.fresh import (
    _GROUNDING_BASE,
    drop_generated_stems,
    filter_grounding_docs,
    fresh_rendered,
    fresh_renders,
    project_slug,
    specialist_caps_from_manifest,
)

from ..common import resolve_context_root

__all__ = [
    "_GROUNDING_BASE",
    "drop_generated_stems",
    "filter_grounding_docs",
    "fresh_renders",
    "fresh_rendered",
    "project_slug",
    "specialist_caps_from_manifest",
]

_SETTINGS_REL = ".claude/settings.json"


# --- flag parsing (local; never the shared parse_path_and_root)


def pull_flag_value(rest: list[str], name: str) -> tuple[str | None, list[str]]:
    """Strip a single ``--name VALUE`` / ``--name=VALUE`` out of ``rest``.

    Mirrors ``cli.build_loop.pull_flag_value`` — local so we never route equip
    through the shared ``parse_path_and_root`` (whose ``_FLAGS_TAKING_VALUE``
    table would mis-handle equip's own ``--status``-class flags).
    """
    value: str | None = None
    out: list[str] = []
    i = 0
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    while i < len(rest):
        a = rest[i]
        if a == long_flag and i + 1 < len(rest):
            value = rest[i + 1]
            i += 2
        elif a.startswith(eq_prefix):
            value = a.split("=", 1)[1]
            i += 1
        else:
            out.append(a)
            i += 1
    return value, out


def pull_bool_flag(rest: list[str], name: str) -> tuple[bool, list[str]]:
    """Strip every ``--name`` occurrence; return (present?, remaining)."""
    flag = f"--{name}"
    present = flag in rest
    return present, [a for a in rest if a != flag]


def pull_root(rest: list[str]) -> tuple[Path | None, list[str]]:
    value, rest = pull_flag_value(rest, "root")
    return (Path(value) if value else None), rest


def resolve_root(rest: list[str]) -> tuple[Path, list[str]]:
    """Pull ``--root`` and a single optional positional path; resolve the root."""
    explicit_root, rest = pull_root(rest)
    scope = Path(".")
    leftover: list[str] = []
    saw_scope = False
    for a in rest:
        if not a.startswith("--") and not saw_scope:
            scope = Path(a)
            saw_scope = True
        else:
            leftover.append(a)
    return resolve_context_root(scope, explicit_root=explicit_root), leftover


def pull_root_then_positional(
    rest: list[str],
) -> tuple[Path, tuple[str | None, list[str]]]:
    """Pull ``--root DIR`` then take the first positional as a NAME (not a path).

    Shared by ``equip reset NAME`` and ``equip add-specialist CAPABILITY`` — both
    take a single bare positional that is an identifier, not a scope path, so the
    root always resolves from the cwd (override with ``--root``).
    """
    explicit_root, rest = pull_root(rest)
    name: str | None = None
    leftover: list[str] = []
    for a in rest:
        if not a.startswith("--") and name is None:
            name = a
        else:
            leftover.append(a)
    root = resolve_context_root(Path("."), explicit_root=explicit_root)
    return root, (name, leftover)
