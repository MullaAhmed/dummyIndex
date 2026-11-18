"""Seed a first ``config.toml`` from the wired set. Pure: no file or Config access."""

from __future__ import annotations

import re
from collections.abc import Sequence

from dummyindex.context.versioning import parse_version

from ....skills import SIBLING_SKILLS
from ...default_plugins import DEFAULT_PLUGINS, WiredEntry, WiredKind
from .constants import SCHEMA_VERSION
from .models import PluginRequirement, Requirements, SkillRequirement
from .toml_io import is_valid_constraint

_RELEASE = re.compile(r"^\d+(?:\.\d+)*$")
_DEFAULT_TARGETS = frozenset(plugin.target for plugin in DEFAULT_PLUGINS)


def _family_names() -> tuple[str, ...]:
    return ("dummyindex", *(label for _sub, label in SIBLING_SKILLS))


def _constraint(pin: str | None) -> str | None:
    """Turn a descriptive wired pin into a ``>=`` constraint, or drop it."""
    if pin is None:
        return None
    if is_valid_constraint(pin):
        return pin
    if parse_version(pin) is not None:
        return f">={pin}"
    return None


def _min_version(cli_version: str) -> str | None:
    return cli_version if _RELEASE.fullmatch(cli_version) else None


def seed_requirements(
    wired: Sequence[WiredEntry],
    *,
    default_plugins_enabled: bool,
    cli_version: str,
    claude_wired: bool,
) -> Requirements:
    plugins: list[PluginRequirement] = []
    seen: set[str] = set()
    for entry in wired:
        if entry.kind is not WiredKind.PLUGIN or entry.target in seen:
            continue
        if not default_plugins_enabled and entry.target in _DEFAULT_TARGETS:
            continue
        seen.add(entry.target)
        plugins.append(
            PluginRequirement(id=entry.target, version=_constraint(entry.version))
        )
    skills = tuple(SkillRequirement(name=name) for name in _family_names())
    return Requirements(
        schema_version=SCHEMA_VERSION,
        min_version=_min_version(cli_version),
        plugins=tuple(plugins),
        skills=skills,
        require_native_adapters=claude_wired,
    )
