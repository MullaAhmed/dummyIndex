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

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .claude_plugins import enable_plugin
from .claude_settings import MalformedSettingsError, load_settings

# Set truthy to suppress the best-effort ``claude plugin install`` shell-out and
# leave defaults for Claude Code to materialise on next session. The test suite
# sets it so the production path never touches the real CLI/network; CI or users
# who don't want install-time network can set it too.
SKIP_INSTALL_ENV = "DUMMYINDEX_SKIP_PLUGIN_INSTALL"


@dataclass(frozen=True)
class DefaultPlugin:
    """One plugin dummyindex enables by default, identified by marketplace.

    ``repo`` is the ``owner/name`` GitHub slug of the marketplace, needed only
    for *non-official* marketplaces that must be registered (``claude plugin
    marketplace add``) before install. It is ``None`` for marketplaces Claude
    Code natively knows (e.g. the Anthropic-official one). ``ref`` optionally
    pins the marketplace to a tag/branch/sha.
    """

    plugin: str
    marketplace: str
    repo: str | None = None
    ref: str | None = None

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


def _already_decided(project_root: Path, target: str) -> bool:
    """True if the repo already has a decision for ``target``.

    The ``enabledPlugins`` key is *present* (``true`` OR explicitly ``false``)
    in the project ``settings.json`` or ``settings.local.json``. User
    ``~/.claude/settings.json`` is intentionally NOT consulted: the committed
    project settings file is the team-wide artefact and must not depend on the
    current developer's personal global config. A malformed/unreadable file
    counts as "no decision".
    """
    for rel in ("settings.json", "settings.local.json"):
        path = project_root / ".claude" / rel
        try:
            enabled = load_settings(path).get("enabledPlugins")
        except (MalformedSettingsError, OSError):
            continue
        if isinstance(enabled, dict) and target in enabled:
            return True
    return False


def wire_default_plugins(
    project_root: Path, *, enabled: bool = True
) -> PluginWireResult:
    """Enable each :data:`DEFAULT_PLUGINS` entry in the project ``settings.json``.

    ``enabled=False`` wires nothing (every target lands in ``skipped``). For a
    default the repo has already decided (see :func:`_already_decided`), the
    target is recorded in ``already`` and left untouched. Otherwise
    ``enable_plugin`` writes ``true`` into ``<project_root>/.claude/settings.json``.
    Any settings error is captured in ``errors`` — never raised.
    """
    if not enabled:
        return PluginWireResult(skipped=tuple(p.target for p in DEFAULT_PLUGINS))

    settings_path = project_root / ".claude" / "settings.json"
    enabled_now: list[str] = []
    already: list[str] = []
    errors: list[tuple[str, str]] = []
    for plugin in DEFAULT_PLUGINS:
        if _already_decided(project_root, plugin.target):
            already.append(plugin.target)
            continue
        try:
            enable_plugin(
                settings_path,
                plugin=plugin.plugin,
                marketplace=plugin.marketplace,
            )
        except (MalformedSettingsError, OSError) as exc:
            errors.append((plugin.target, str(exc)))
            continue
        enabled_now.append(plugin.target)
    return PluginWireResult(
        enabled=tuple(enabled_now),
        already=tuple(already),
        errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# Materialisation — actually install the bits, not just declare them.
#
# `wire_default_plugins` writes the shared *declaration* (``enabledPlugins`` in
# the committed settings.json). That declaration travels via git, but the
# plugin's *bits* do not: the marketplace clone and the install registration
# live under ``~/.claude/plugins/`` — per-machine, never shared. So a teammate
# who clones the repo has the intent but not the plugin until Claude Code
# installs it. `install_default_plugins` closes that gap at ``dummyindex
# install`` time by shelling out to the ``claude`` CLI. Best-effort, mirroring
# the subprocess-behind-a-Runner-seam precedent in
# ``context/domains/equip/plugins/sources.py``: fixed argv, no shell, never
# raises; a missing ``claude`` degrades to "deferred" (Claude Code installs it
# on next session) rather than an error.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


# (argv, cwd) -> RunResult. cwd scopes ``--scope project`` writes to the repo.
Runner = Callable[[list[str], Path], RunResult]

# Bounds a single ``claude`` invocation. Best-effort means fail-fast-and-defer
# beats hanging the terminal: a slow clone trips this and degrades to deferred.
_RUN_TIMEOUT_SECONDS = 60


def default_runner(argv: list[str], cwd: Path) -> RunResult:
    """Run ``argv`` in ``cwd`` with no shell, capturing output. Never raises;
    a missing executable surfaces as returncode 127."""
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_RUN_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RunResult(returncode=127, stdout="", stderr=str(exc))
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class PluginInstallResult:
    """Outcome of :func:`install_default_plugins`. Carries errors, never raises.

    - ``installed`` — targets materialised via ``claude plugin install``.
    - ``deferred`` — targets left to Claude Code (``claude`` CLI unavailable);
      the wired declaration still makes Claude Code install them on next session.
    - ``skipped`` — targets not attempted because wiring was disabled.
    - ``errors`` — ``(target, message)`` for a marketplace-add/install that the
      CLI rejected.
    """

    installed: tuple[str, ...] = ()
    deferred: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    errors: tuple[tuple[str, str], ...] = ()


def _claude_available(runner: Runner, cwd: Path) -> bool:
    """True iff the ``claude`` CLI answers ``--version`` with exit 0."""
    return runner(["claude", "--version"], cwd).returncode == 0


def _tail(text: str, limit: int = 200) -> str:
    """Last line of ``text``, trimmed — enough to explain a CLI failure."""
    line = text.strip().splitlines()[-1] if text.strip() else ""
    return line[:limit]


def _install_one(
    plugin: DefaultPlugin, project_root: Path, runner: Runner
) -> tuple[bool, str | None]:
    """Install one default via the ``claude`` CLI. ``(ok, error_message)``.

    A non-official marketplace (``plugin.repo`` set) is registered first. Both
    steps are scoped to the project so the enable lands in the committed
    ``settings.json``, the same place :func:`wire_default_plugins` writes it.
    """
    if plugin.repo:
        source = plugin.repo if plugin.ref is None else f"{plugin.repo}@{plugin.ref}"
        added = runner(
            ["claude", "plugin", "marketplace", "add", source, "--scope", "project"],
            project_root,
        )
        if added.returncode != 0:
            return False, (
                f"marketplace add failed (exit {added.returncode}): "
                f"{_tail(added.stderr or added.stdout)}"
            )
    installed = runner(
        ["claude", "plugin", "install", plugin.target, "--scope", "project"],
        project_root,
    )
    if installed.returncode != 0:
        return False, (
            f"install failed (exit {installed.returncode}): "
            f"{_tail(installed.stderr or installed.stdout)}"
        )
    return True, None


def install_default_plugins(
    project_root: Path, *, enabled: bool = True, runner: Runner | None = None
) -> PluginInstallResult:
    """Materialise each :data:`DEFAULT_PLUGINS` entry via the ``claude`` CLI.

    ``enabled=False`` installs nothing (every target lands in ``skipped``). When
    the ``claude`` CLI is unavailable — or :data:`SKIP_INSTALL_ENV` is set on the
    production path — every target lands in ``deferred`` (the wired declaration
    still lets Claude Code install on next session). Each install is idempotent
    (a no-op if already present) and best-effort: a CLI rejection is recorded in
    ``errors``, never raised.

    ``runner`` defaults to :func:`default_runner` (real subprocess). Injecting a
    runner is the test seam and also bypasses :data:`SKIP_INSTALL_ENV`, so unit
    tests exercise the install logic regardless of the ambient env guard.
    """
    injected = runner is not None
    if runner is None:
        runner = default_runner

    if not enabled:
        return PluginInstallResult(skipped=tuple(p.target for p in DEFAULT_PLUGINS))
    if not injected and os.environ.get(SKIP_INSTALL_ENV):
        return PluginInstallResult(deferred=tuple(p.target for p in DEFAULT_PLUGINS))
    if not _claude_available(runner, project_root):
        return PluginInstallResult(deferred=tuple(p.target for p in DEFAULT_PLUGINS))

    installed: list[str] = []
    deferred: list[str] = []
    errors: list[tuple[str, str]] = []
    for plugin in DEFAULT_PLUGINS:
        ok, err = _install_one(plugin, project_root, runner)
        if ok:
            installed.append(plugin.target)
        elif err is not None:
            errors.append((plugin.target, err))
        else:  # pragma: no cover - defensive; _install_one returns ok or error
            deferred.append(plugin.target)
    return PluginInstallResult(
        installed=tuple(installed),
        deferred=tuple(deferred),
        errors=tuple(errors),
    )


def describe_install_result(
    result: PluginInstallResult,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Render an install ``result`` into ``(stdout_lines, stderr_lines)``.

    ``result.skipped`` is intentionally NOT rendered: the opt-out is already
    announced by :func:`describe_wire_result`, which shares the same ``enabled``
    gate — rendering it here too would double-print every opted-out target.
    """
    info: list[str] = []
    warn: list[str] = []
    for target in result.installed:
        info.append(f"plugins          ->  installed {target}")
    for target in result.deferred:
        info.append(
            f"plugins          ->  deferred {target} "
            f"(Claude Code will install it on next session)"
        )
    for target, msg in result.errors:
        warn.append(f"plugins warning ({target}): {msg}")
    return tuple(info), tuple(warn)
