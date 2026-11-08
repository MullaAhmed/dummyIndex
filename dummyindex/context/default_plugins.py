"""Wire dummyindex's default Claude Code plugins into a repo at init time.

Init enables a small, reviewed plugin set in the project's ``.claude/settings.json``.
Third-party defaults track their upstream's default branch (no commit pin; see
:func:`_is_legacy_sha_pin`). Base layer: imports nothing from ``cli/``,
``installer/`` or ``context/domains/``. :func:`wire_default_plugins` reports problems
in its result and never raises, so a bad ``settings.json`` cannot fail init.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .claude_plugins import add_marketplace, enable_plugin
from .claude_settings import MalformedSettingsError, load_settings


class WiredKind(str, Enum):
    """What a :class:`WiredEntry` declares — a plugin or a (bundled) skill."""

    PLUGIN = "plugin"
    SKILL = "skill"


class WiredClass(str, Enum):
    """How a declared :class:`WiredEntry` classifies against actual presence.

    The satisfied / acted / needs-user vocabulary; the rule lives in
    :func:`classify_wired_entry`.
    """

    SATISFIED = "satisfied"
    ACTED = "acted"
    NEEDS_USER = "needs_user"


@dataclass(frozen=True)
class WiredEntry:
    """One declared plugin/skill the repo wants present, optionally version-pinned.

    Committed in ``config.wired``. ``target`` is ``<plugin>@<marketplace>`` or a bare
    skill name; ``version`` is a descriptive pin (surfaced, never enforced as an
    install ref) or ``None``. Validation lives in :meth:`from_dict`.
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

    ``repo`` (``owner/name``) is needed only for non-official marketplaces; there is
    deliberately no pin field. ``surfaces`` / ``runs_code`` disclose the reviewed
    blast radius; they never substitute for equip's approval gate for arbitrary
    third-party sources.
    """

    plugin: str
    marketplace: str
    repo: str | None = None
    surfaces: tuple[str, ...] = ()
    runs_code: bool = False

    def __post_init__(self) -> None:
        if not self.plugin or not self.marketplace:
            raise ValueError("default plugin and marketplace must be non-empty")

    @property
    def target(self) -> str:
        """The ``<plugin>@<marketplace>`` key Claude Code resolves it by."""
        return f"{self.plugin}@{self.marketplace}"


def _validate_default_plugins(
    plugins: tuple[DefaultPlugin, ...],
) -> tuple[DefaultPlugin, ...]:
    """Return ``plugins`` after validating deterministic unique targets."""
    seen: set[str] = set()
    for plugin in plugins:
        if plugin.target in seen:
            raise ValueError(f"duplicate default plugin target: {plugin.target}")
        seen.add(plugin.target)
        if not plugin.surfaces:
            raise ValueError(f"default plugin {plugin.target} has no reviewed surfaces")
    return plugins


# Ordered, reviewed built-ins. The official marketplace needs no declaration.
DEFAULT_PLUGINS: tuple[DefaultPlugin, ...] = _validate_default_plugins(
    (
        DefaultPlugin(
            plugin="superpowers",
            marketplace="claude-plugins-official",
            surfaces=("skills",),
            runs_code=False,
        ),
        DefaultPlugin(
            plugin="caveman",
            marketplace="caveman",
            repo="JuliusBrussee/caveman",
            surfaces=(
                "skills",
                "commands",
                "SessionStart Node command hook",
                "UserPromptSubmit Node command hook",
            ),
            runs_code=True,
        ),
        DefaultPlugin(
            plugin="i-have-adhd",
            marketplace="i-have-adhd",
            repo="ayghri/i-have-adhd",
            surfaces=("skill", "opt-in SessionStart shell command hook"),
            runs_code=True,
        ),
    )
)


def describe_default_plugin_trust() -> tuple[str, ...]:
    """Render reviewed third-party provenance and blast radius.

    Callers print these pure-rendered lines before config reconciliation,
    settings writes, or runner probes so the reviewed exception is visible
    before it can mutate project or per-machine state.
    """
    lines: list[str] = []
    for plugin in DEFAULT_PLUGINS:
        if plugin.repo is None:
            continue
        lines.append(
            f"default plugin trust -> {plugin.target} from "
            f"{plugin.repo} (tracks latest); reviewed surfaces: "
            f"{', '.join(plugin.surfaces)}; runs code: "
            f"{'yes' if plugin.runs_code else 'no'}; opt out this run with "
            "--no-default-plugins"
        )
    return tuple(lines)


def _plugin_to_wired(plugin: DefaultPlugin) -> WiredEntry:
    """Adapt a :class:`DefaultPlugin` to a :class:`WiredEntry`.

    The single source for the ``<plugin>@<marketplace>`` ``target`` format, so
    ``config.wired`` and ``DEFAULT_PLUGINS`` can never drift on it. Defaults map
    to ``kind=plugin`` with no version pin (descriptive only).
    """
    return WiredEntry(kind=WiredKind.PLUGIN, target=plugin.target, version=None)


def default_wired() -> tuple[WiredEntry, ...]:
    """The seed ``wired`` set — :data:`DEFAULT_PLUGINS` as :class:`WiredEntry`s.

    Claude/both-host ``default_config()`` seeds ``config.wired`` from this (Codex-only
    has no Claude plugins); the v1→v2 read migration uses it for
    ``wire_superpowers: true``.
    """
    return tuple(_plugin_to_wired(p) for p in DEFAULT_PLUGINS)


@dataclass(frozen=True)
class PluginWireResult:
    """Outcome of :func:`wire_default_plugins`. Carries errors, never raises.

    - ``already`` (satisfied): plugin already ``true`` or ``false`` in project settings.
    - ``enabled`` (acted): declared but absent; ``true`` was written.
    - ``needs_user``: ``(target, reason)``: skills, bad targets, marketplace conflicts.
    - ``skipped``: wiring disabled. ``errors``: ``(target, message)`` for settings I/O.
    ``WiredEntry.version`` never drives a re-wire: settings has no version field.
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
    """True if ``enabledPlugins`` holds ``target`` (``true`` or ``false``).

    Checks the project ``settings.json`` and ``settings.local.json`` only: the
    committed project file is team-wide and must not depend on one developer's
    ``~/.claude/settings.json``. A malformed/unreadable file counts as "no decision".
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


def _effective_enabled(project_root: Path, target: str) -> bool | None:
    """Return effective project/local state, preserving any false tombstone."""
    state: bool | None = None
    for rel in ("settings.json", "settings.local.json"):
        enabled = load_settings(project_root / ".claude" / rel).get("enabledPlugins")
        if not isinstance(enabled, dict):
            continue
        value = enabled.get(target)
        if value is False:
            return False
        if value is True:
            state = True
    return state


def _default_for_target(target: str) -> DefaultPlugin | None:
    """Return the reviewed built-in matching ``target``, if any."""
    return next((plugin for plugin in DEFAULT_PLUGINS if plugin.target == target), None)


def _expected_source(plugin: DefaultPlugin) -> dict[str, str]:
    """The canonical unpinned settings declaration for a reviewed default."""
    return {"source": "github", "repo": plugin.repo or ""}


def _is_legacy_sha_pin(source: object, plugin: DefaultPlugin) -> bool:
    """Whether ``source`` is exactly a dummyindex <= 0.33.x SHA pin of ``plugin``.

    Claude Code materialises marketplaces with ``git clone --branch <ref>``, which
    takes a branch/tag but never a commit SHA, so defaults cannot be pinned. Healable
    means the only difference from the unpinned shape is a ``ref`` holding a full
    lowercase 40-char SHA. A branch/tag ref (a deliberate user choice) or any extra
    key is not healable and keeps the preserve-or-refuse contract.
    """
    if not isinstance(source, dict) or set(source) != {"source", "repo", "ref"}:
        return False
    ref = source.get("ref")
    return (
        source.get("source") == "github"
        and source.get("repo") == plugin.repo
        and isinstance(ref, str)
        and re.fullmatch(r"[0-9a-f]{40}", ref) is not None
    )


def _declare_marketplace(
    settings_path: Path, plugin: DefaultPlugin
) -> tuple[bool, str | None]:
    """Declare an unpinned marketplace without overwriting a name conflict.

    Returns ``(ready, conflict_reason)``. A legacy SHA pin of the same repo
    (:func:`_is_legacy_sha_pin`) is healed to the unpinned shape, since left in
    place it fails at every session start. Any other difference (repo, shape,
    branch/tag ref, extra keys) is a conflict and is left unchanged.
    """
    if plugin.repo is None:
        return True, None
    settings = load_settings(settings_path)
    block = settings.get("extraKnownMarketplaces")
    if block is not None and not isinstance(block, dict):
        raise MalformedSettingsError(
            f"{settings_path} extraKnownMarketplaces is not an object; left unchanged"
        )
    existing = block.get(plugin.marketplace) if isinstance(block, dict) else None
    if existing is not None:
        source = existing.get("source") if isinstance(existing, dict) else None
        if source == _expected_source(plugin):
            return True, None
        if not _is_legacy_sha_pin(source, plugin):
            return False, (
                f"marketplace {plugin.marketplace!r} already declares a different "
                "source; left unchanged"
            )
    add_marketplace(
        settings_path,
        name=plugin.marketplace,
        repo=plugin.repo,
    )
    return True, None


def _marketplace_matches(settings_path: Path, plugin: DefaultPlugin) -> bool:
    """Whether the reviewed marketplace declaration is ready for install.

    Ready means the canonical unpinned declaration, or the healable legacy SHA pin
    (the install's own ``claude plugin marketplace add <repo>`` re-declares it
    unpinned). Any other difference is a user decision: not ready, so the install
    never overwrites it via the Claude CLI.
    """
    if plugin.repo is None:
        return True
    settings = load_settings(settings_path)
    block = settings.get("extraKnownMarketplaces")
    if not isinstance(block, dict):
        return False
    existing = block.get(plugin.marketplace)
    source = existing.get("source") if isinstance(existing, dict) else None
    return source == _expected_source(plugin) or _is_legacy_sha_pin(source, plugin)


def _split_target(target: str) -> tuple[str, str] | None:
    """Split a plugin ``target`` into ``(plugin, marketplace)``.

    Splits on the last ``@`` so a plugin name containing one is tolerated. Returns
    ``None`` for an invalid shape (no ``@``, or an empty half) so the caller can
    classify it needs-user instead of mis-wiring it.
    """
    plugin, sep, marketplace = target.rpartition("@")
    if not sep or not plugin or not marketplace:
        return None
    return plugin, marketplace


def classify_wired_entry(
    entry: WiredEntry, *, is_present: Callable[[str], bool]
) -> WiredClass:
    """Classify one declared ``entry`` against presence only — pure, no I/O.

    ``is_present(target)`` says whether project settings already decide it (e.g.
    :func:`_already_decided` bound to a root). Used by ``status`` and ``wire``:
    a skill (no skill-enable primitive) or a non-``<plugin>@<marketplace>`` target
    is ``NEEDS_USER``; a decided plugin is ``SATISFIED``; an absent one ``ACTED``.
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

    Runs inside headless, never-raise init, so it never prompts. Per plugin, by
    :func:`_effective_enabled`: ``false`` → ``already``; otherwise a reviewed
    third-party default's marketplace is declared (or healed) first, then ``true``
    → ``already``, absent → write ``true``. Installing is the separate
    :func:`install_default_plugins` pass; ``runner`` is unused (compatibility).
    """
    if not enabled:
        return PluginWireResult(skipped=tuple(e.target for e in wired))

    del runner
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
        try:
            state = _effective_enabled(project_root, entry.target)
        except (MalformedSettingsError, OSError) as exc:
            errors.append((entry.target, str(exc)))
            continue
        if state is False:
            already.append(entry.target)
            continue
        default = _default_for_target(entry.target)
        if default is not None:
            try:
                ready, reason = _declare_marketplace(settings_path, default)
            except (MalformedSettingsError, OSError) as exc:
                errors.append((entry.target, str(exc)))
                continue
            if not ready:
                needs_user.append((entry.target, reason or "marketplace conflict"))
                continue
        if state is True:
            already.append(entry.target)
            continue
        plugin, marketplace = parts
        try:
            enable_plugin(settings_path, plugin=plugin, marketplace=marketplace)
        except (MalformedSettingsError, OSError) as exc:
            errors.append((entry.target, str(exc)))
            continue
        enabled_now.append(entry.target)
    return PluginWireResult(
        enabled=tuple(enabled_now),
        already=tuple(already),
        needs_user=tuple(needs_user),
        errors=tuple(errors),
    )


# Materialisation. The ``enabledPlugins`` declaration travels via git; the plugin
# bits (marketplace clone, install registration) live per machine under
# ``~/.claude/plugins/``. Best-effort ``claude`` CLI shell-out: fixed argv, no shell,
# never raises; a missing ``claude`` degrades to "deferred" (installed next session).


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

    - ``installed``: materialised via ``claude plugin install``.
    - ``deferred``: left to Claude Code's next session (no CLI, or skip env set).
    - ``skipped``: not attempted (disabled, not enabled, or marketplace not ready).
    - ``errors``: ``(target, message)`` for a settings read error or CLI rejection.
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
        added = runner(
            [
                "claude",
                "plugin",
                "marketplace",
                "add",
                plugin.repo,
                "--scope",
                "project",
            ],
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
    project_root: Path,
    *,
    wired: tuple[WiredEntry, ...] | None = None,
    enabled: bool = True,
    runner: Runner | None = None,
) -> PluginInstallResult:
    """Materialise selected, effectively-enabled defaults via the Claude CLI.

    With ``wired``, only declared defaults effectively ``true`` (project/local
    precedence) are eligible; ``None`` takes every default not disabled. A target
    whose marketplace isn't ready is skipped; ``enabled=False`` skips all. With no
    ``claude`` CLI, or :data:`SKIP_INSTALL_ENV` set and no injected ``runner`` (the
    test seam), eligible targets are ``deferred``. CLI rejections go to ``errors``.
    """
    if wired is None:
        selected = DEFAULT_PLUGINS
    else:
        declared = {entry.target for entry in wired if entry.kind is WiredKind.PLUGIN}
        selected = tuple(
            plugin for plugin in DEFAULT_PLUGINS if plugin.target in declared
        )
    if not enabled:
        return PluginInstallResult(skipped=tuple(p.target for p in selected))

    eligible: list[DefaultPlugin] = []
    skipped: list[str] = []
    for plugin in selected:
        try:
            state = _effective_enabled(project_root, plugin.target)
            marketplace_ready = _marketplace_matches(
                project_root / ".claude" / "settings.json", plugin
            )
        except (MalformedSettingsError, OSError) as exc:
            return PluginInstallResult(errors=((plugin.target, str(exc)),))
        if (
            state is False
            or (wired is not None and state is not True)
            or not marketplace_ready
        ):
            skipped.append(plugin.target)
            continue
        eligible.append(plugin)
    if not eligible:
        return PluginInstallResult(skipped=tuple(skipped))

    injected = runner is not None
    if runner is None:
        runner = default_runner
    if not injected and os.environ.get(SKIP_INSTALL_ENV):
        return PluginInstallResult(
            deferred=tuple(p.target for p in eligible), skipped=tuple(skipped)
        )
    if not _claude_available(runner, project_root):
        return PluginInstallResult(
            deferred=tuple(p.target for p in eligible), skipped=tuple(skipped)
        )

    installed: list[str] = []
    deferred: list[str] = []
    errors: list[tuple[str, str]] = []
    for plugin in eligible:
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
        skipped=tuple(skipped),
        errors=tuple(errors),
    )


def describe_install_result(
    result: PluginInstallResult,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Render an install ``result`` into ``(stdout_lines, stderr_lines)``.

    ``result.skipped`` is not rendered: :func:`describe_wire_result` already
    announces the opt-out, so rendering it here would double-print it.
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
