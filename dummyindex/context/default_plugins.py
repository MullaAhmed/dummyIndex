"""Wire dummyindex's default Claude Code plugins into a repo at init time.

When dummyindex first initialises a project (``install`` auto-init, or
``ingest`` / ``context init``), it enables a small, opinionated set of default
plugins in the project's ``.claude/settings.json`` so a fresh dummyindex repo
is "batteries included". Today that set is just ``superpowers`` from the
Anthropic-official marketplace — trusted and natively known to Claude Code, so
we enable it WITHOUT declaring ``extraKnownMarketplaces``.

Base-layer module: it reuses :func:`context.claude_plugins.enable_plugin` and
:func:`context.claude_settings.load_settings` and imports nothing from ``cli/``,
``installer/``, or ``context/domains/`` — callers depend on it, never the
reverse. Like :class:`context.hooks.HookResult`, :func:`wire_default_plugins`
reports problems in its result and never raises, so a malformed or unwritable
``settings.json`` cannot fail an otherwise-successful init.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .claude_plugins import enable_plugin
from .claude_settings import MalformedSettingsError, load_settings


@dataclass(frozen=True)
class DefaultPlugin:
    """One plugin dummyindex enables by default, identified by marketplace."""

    plugin: str
    marketplace: str

    @property
    def target(self) -> str:
        """The ``<plugin>@<marketplace>`` key Claude Code resolves it by."""
        return f"{self.plugin}@{self.marketplace}"


# The default set. A tuple so adding another default is a one-line edit.
# superpowers lives in the Anthropic-official marketplace (trusted + natively
# known to Claude Code) — enable-only, no extraKnownMarketplaces entry needed.
DEFAULT_PLUGINS: tuple[DefaultPlugin, ...] = (
    DefaultPlugin(plugin="superpowers", marketplace="claude-plugins-official"),
)


@dataclass(frozen=True)
class PluginWireResult:
    """Outcome of :func:`wire_default_plugins`. Carries errors, never raises.

    - ``enabled`` — targets newly written ``true`` into the project settings.
    - ``already`` — targets the repo already decided (present in a project
      settings file, enabled or explicitly disabled) and left untouched.
    - ``skipped`` — targets not attempted because wiring was disabled.
    - ``errors`` — ``(target, message)`` for a settings file we couldn't write.
    """

    enabled: tuple[str, ...] = ()
    already: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    errors: tuple[tuple[str, str], ...] = ()


def resolve_enabled(*, cli_opt_out: bool, config_value: bool | None) -> bool:
    """Resolve whether to wire defaults. Precedence: CLI flag > config > on.

    ``cli_opt_out`` True (``--no-superpowers``) always wins → disabled. Else the
    persisted ``config_value`` (``None`` when there is no config or no key) is
    honoured, defaulting to enabled.
    """
    if cli_opt_out:
        return False
    return True if config_value is None else config_value


def describe_wire_result(
    result: PluginWireResult,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Render ``result`` into ``(stdout_lines, stderr_lines)``.

    Pure — the caller prints. Keeps the per-init reporting identical across the
    ``install`` and ``ingest`` entry points without duplicating the wording.
    """
    info: list[str] = []
    warn: list[str] = []
    for target in result.enabled:
        info.append(f"plugins          ->  enabled {target}")
    for target in result.already:
        info.append(f"plugins          ->  {target} already enabled (left as-is)")
    for target in result.skipped:
        info.append(f"plugins          ->  skipped {target} (opted out)")
    for target, msg in result.errors:
        warn.append(f"plugins warning ({target}): {msg}")
    return tuple(info), tuple(warn)
