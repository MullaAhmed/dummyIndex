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
from enum import Enum
from pathlib import Path
from typing import Any

from .claude_plugins import enable_plugin
from .claude_settings import MalformedSettingsError, load_settings


class WiredKind(str, Enum):
    """What a :class:`WiredEntry` declares — a plugin or a (bundled) skill."""

    PLUGIN = "plugin"
    SKILL = "skill"


class WiredClass(str, Enum):
    """How a declared :class:`WiredEntry` classifies against actual presence.

    The single vocabulary shared by every surface that classifies ``wired``
    (the headless reconciler's reporting, read-only ``status``, the interactive
    ``wire`` command) so they can never drift on what "satisfied / acted /
    needs-user" means:

    - ``SATISFIED`` — a ``kind=plugin`` entry already decided in the committed
      ``settings.json`` (enabled or explicitly disabled) → left untouched.
    - ``ACTED`` — a ``kind=plugin`` entry declared but absent → a real run wires
      it (``enable_plugin`` + best-effort install).
    - ``NEEDS_USER`` — an entry no unattended run can resolve: every
      ``kind=skill`` entry (no skill-enable primitive) or a plugin ``target``
      with no ``<plugin>@<marketplace>`` shape.
    """

    SATISFIED = "satisfied"
    ACTED = "acted"
    NEEDS_USER = "needs_user"


@dataclass(frozen=True)
class WiredEntry:
    """One declared plugin/skill the repo wants present, optionally version-pinned.

    The user-facing source of truth for what should be wired (committed in
    ``config.wired``). ``target`` is ``<plugin>@<marketplace>`` for a plugin or a
    bare skill name; ``version`` is a *descriptive* pin (recorded/surfaced, never
    enforced as an install ref) or ``None``. Mirrors
    :class:`context.domains.equip.models.EquipmentItem`'s hand-written
    ``to_dict``/``from_dict`` style; validation lives at the ``from_dict``
    boundary.
    """

    kind: WiredKind
    target: str
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WiredEntry:
        if not isinstance(data, dict):
            raise ValueError(
                f"wired entry must be an object, got {type(data).__name__}"
            )
        raw_kind = data.get("kind")
        try:
            kind = WiredKind(raw_kind)
        except ValueError as exc:
            allowed = ", ".join(m.value for m in WiredKind)
            raise ValueError(
                f"wired.kind={raw_kind!r} is not one of: {allowed}"
            ) from exc
        target = data.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("wired.target must be a non-empty string")
        ver = data.get("version")
        return cls(
            kind=kind,
            target=target,
            version=str(ver) if ver is not None else None,
        )


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


def _plugin_to_wired(plugin: DefaultPlugin) -> WiredEntry:
    """Adapt a :class:`DefaultPlugin` to a :class:`WiredEntry`.

    The single source for the ``<plugin>@<marketplace>`` ``target`` format, so
    ``config.wired`` and ``DEFAULT_PLUGINS`` can never drift on it. Defaults map
    to ``kind=plugin`` with no version pin (descriptive only).
    """
    return WiredEntry(kind=WiredKind.PLUGIN, target=plugin.target, version=None)


def default_wired() -> tuple[WiredEntry, ...]:
    """The seed ``wired`` set — :data:`DEFAULT_PLUGINS` as :class:`WiredEntry`s.

    The default declaration moves from code-as-law to config-as-declaration:
    ``default_config()`` seeds ``config.wired`` from this, and the v1→v2 read
    migration uses it for ``wire_superpowers: true``.
    """
    return tuple(_plugin_to_wired(p) for p in DEFAULT_PLUGINS)


@dataclass(frozen=True)
class PluginWireResult:
    """Outcome of :func:`wire_default_plugins`. Carries errors, never raises.

    The reconciler classifies each declared :class:`WiredEntry` against the
    project ``settings.json`` *presence* into one of three buckets, mirrored by
    the spec's satisfied / acted / needs-user vocabulary:

    - ``already`` — **satisfied**: a ``kind=plugin`` entry the repo already
      decided (present in a project settings file, enabled or explicitly
      disabled) → left untouched.
    - ``enabled`` — **acted**: a ``kind=plugin`` entry declared but absent →
      ``enable_plugin`` wrote ``true`` into the project settings.
    - ``needs_user`` — **needs-user**: ``(target, reason)`` for an entry the
      reconciler can't act on unattended — every ``kind=skill`` entry (no
      skill-enable primitive exists; skills are declared + surfaced, never
      auto-wired here) and any plugin install that the best-effort
      materialisation reported as failed.
    - ``skipped`` — targets not attempted because wiring was disabled
      (empty ``wired`` / ``--no-superpowers``).
    - ``errors`` — ``(target, message)`` for a settings file we couldn't write.

    ``WiredEntry.version`` is recorded/surfaced only; it NEVER drives a
    re-wire — ``settings.json`` has no installed-version field, so the
    reconciler synthesises no "stale" verdict from it.
    """

    enabled: tuple[str, ...] = ()
    already: tuple[str, ...] = ()
    needs_user: tuple[tuple[str, str], ...] = ()
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
    for target, reason in result.needs_user:
        warn.append(f"plugins          ->  needs you: {target} ({reason})")
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


def _split_target(target: str) -> tuple[str, str] | None:
    """Split a plugin ``target`` into ``(plugin, marketplace)``.

    A plugin ``target`` is ``<plugin>@<marketplace>`` (see
    :meth:`DefaultPlugin.target`). Split on the *last* ``@`` so a plugin name
    that contains one is tolerated. Returns ``None`` if the shape is invalid
    (no ``@``, or an empty half) so the caller can classify it needs-user
    rather than mis-wire it.
    """
    plugin, sep, marketplace = target.rpartition("@")
    if not sep or not plugin or not marketplace:
        return None
    return plugin, marketplace


def classify_wired_entry(
    entry: WiredEntry, *, is_present: Callable[[str], bool]
) -> WiredClass:
    """Classify one declared ``entry`` against presence only — pure, no I/O.

    ``is_present(target)`` reports whether the project ``settings.json`` already
    has a decision for that plugin target (the caller passes
    :func:`_already_decided` bound to a root, or a fake in tests). This is the
    ONE place the satisfied / acted / needs-user rule lives, so the reconciler,
    read-only ``status`` and the interactive ``wire`` command can never drift:

    - ``kind=skill`` → :attr:`WiredClass.NEEDS_USER` (no skill-enable primitive).
    - a plugin ``target`` with no ``<plugin>@<marketplace>`` shape →
      :attr:`WiredClass.NEEDS_USER` (can't be mis-wired).
    - a ``kind=plugin`` already decided → :attr:`WiredClass.SATISFIED`.
    - a ``kind=plugin`` declared but absent → :attr:`WiredClass.ACTED`.
    """
    if entry.kind is WiredKind.SKILL or _split_target(entry.target) is None:
        return WiredClass.NEEDS_USER
    if is_present(entry.target):
        return WiredClass.SATISFIED
    return WiredClass.ACTED


def wire_default_plugins(
    wired: tuple[WiredEntry, ...],
    project_root: Path,
    *,
    enabled: bool = True,
    runner: Runner | None = None,
) -> PluginWireResult:
    """Reconcile the declared ``wired`` list against the project ``settings.json``.

    Non-interactive and never-blocking — it runs inside best-effort, never-raise,
    headless ``install``/``ingest`` init, so it **only classifies and reports**;
    it never calls ``input()``. Each :class:`WiredEntry` is classified against
    the actual settings *presence* (:func:`_already_decided`) into the
    :class:`PluginWireResult` buckets:

    - ``kind=skill`` → always **needs-user** (no skill-enable primitive exists;
      skills are declared + surfaced, never auto-wired here).
    - ``kind=plugin`` already decided → **satisfied** (``already``).
    - ``kind=plugin`` declared but absent → **acted** (``enabled``):
      ``enable_plugin`` writes ``true`` into the project settings, then
      :func:`install_default_plugins` best-effort materialises the bits. An
      install the CLI rejected lands in **needs-user** (the declaration is
      written, but the user must finish it — e.g. an untrusted source needing
      ``--yes``).

    ``enabled=False`` (empty ``wired`` / ``--no-superpowers``) wires nothing —
    every target lands in ``skipped``. ``WiredEntry.version`` is recorded only,
    never used to trigger a re-wire. ``runner`` is the test seam threaded into
    the install step (real subprocess by default). Any settings-write error is
    captured in ``errors`` — never raised.
    """
    if not enabled:
        return PluginWireResult(skipped=tuple(e.target for e in wired))

    settings_path = project_root / ".claude" / "settings.json"
    enabled_now: list[str] = []
    already: list[str] = []
    needs_user: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    for entry in wired:
        if entry.kind is WiredKind.SKILL:
            needs_user.append(
                (entry.target, "skill entries are declared, not auto-wired")
            )
            continue
        parts = _split_target(entry.target)
        if parts is None:
            needs_user.append((entry.target, "not a <plugin>@<marketplace> target"))
            continue
        if _already_decided(project_root, entry.target):
            already.append(entry.target)
            continue
        plugin, marketplace = parts
        try:
            enable_plugin(settings_path, plugin=plugin, marketplace=marketplace)
        except (MalformedSettingsError, OSError) as exc:
            errors.append((entry.target, str(exc)))
            continue
        enabled_now.append(entry.target)
        install = install_default_plugins(project_root, enabled=True, runner=runner)
        for failed_target, msg in install.errors:
            if failed_target == entry.target:
                needs_user.append((entry.target, f"install needs you: {msg}"))
    return PluginWireResult(
        enabled=tuple(enabled_now),
        already=tuple(already),
        needs_user=tuple(needs_user),
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
