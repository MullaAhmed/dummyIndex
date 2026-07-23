"""Wire dummyindex's default Claude Code plugins into a repo at init time.

When dummyindex first initialises a project (``install`` auto-init, or
``ingest`` / ``context init``), it enables a small, reviewed set of default
plugins in the project's ``.claude/settings.json`` so a fresh dummyindex repo
is "batteries included". Third-party defaults track their upstream's latest
default branch — Claude Code materialises marketplaces with ``git clone
--branch <ref>``, which accepts branch/tag names but never a commit SHA, so a
pin cannot be expressed here. The reviewed blast radius is still disclosed
before callers mutate settings or invoke Claude Code.

Base-layer module: it reuses :func:`context.claude_plugins.enable_plugin` and
:func:`context.claude_settings.load_settings` and imports nothing from ``cli/``,
``installer/``, or ``context/domains/`` — callers depend on it, never the
reverse. Like :class:`context.hooks.HookResult`, :func:`wire_default_plugins`
reports problems in its result and never raises, so a malformed or unwritable
``settings.json`` cannot fail an otherwise-successful init.
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
    for *non-official* marketplaces. Third-party records track the upstream's
    latest default branch — Claude Code cannot clone a commit SHA, so there is
    deliberately no pin field. ``surfaces`` and ``runs_code`` record the
    reviewed blast radius; they are disclosure metadata, never a substitute for
    equip's approval gate for arbitrary third-party sources.
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


# Ordered, reviewed built-ins. The official marketplace needs no declaration;
# both third-party sources track their upstream's latest default branch (see
# the module docstring for why a commit pin is not expressible).
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
            surfaces=("skill",),
            runs_code=False,
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

    The default declaration moves from code-as-law to config-as-declaration:
    Claude/both-host ``default_config()`` baselines seed ``config.wired`` from
    this (Codex-only has no Claude plugins), and the v1→v2 read migration uses
    it for ``wire_superpowers: true``.
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

    Healable means the ONLY difference from the canonical unpinned shape is a
    ``ref`` holding a full lowercase 40-char commit SHA — the shape old
    dummyindex wrote and Claude Code's ``git clone --branch <ref>`` can never
    clone. A branch/tag ref (clonable, so a deliberate user choice) or any
    other extra key is NOT healable and keeps the preserve-or-refuse contract.
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

    A declaration that is exactly a dummyindex <= 0.33.x commit-SHA pin of the
    same reviewed repo is *healed* to the unpinned shape rather than treated as
    a conflict: Claude Code's ``git clone --branch <ref>`` materialisation can
    never clone a commit SHA, so left in place the stale pin fails at every
    session start. Anything else that differs — another repo, a non-github
    shape, a deliberate branch/tag ref, extra keys — is a conflict and is left
    unchanged.
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

    Ready means the canonical unpinned declaration is present, or the one
    healable legacy shape (a <= 0.33.x commit-SHA pin of the same repo) that
    the wiring pass rewrites and the eager install's own
    ``claude plugin marketplace add <repo>`` re-declares unpinned anyway. A
    declaration that differs any other way is a user decision — not ready, so
    the install never overwrites it via the Claude CLI.
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
    - ``kind=plugin`` declared but absent → **acted** (``enabled``): declare a
      reviewed pinned marketplace first when needed, then write ``true`` into
      project settings. Materialisation is a separate, target-filtered
      :func:`install_default_plugins` pass.

    ``enabled=False`` (empty ``wired`` / ``--no-superpowers``) wires nothing —
    every target lands in ``skipped``. ``WiredEntry.version`` is recorded only,
    never used to trigger a re-wire. ``runner`` remains as a compatibility
    parameter but is intentionally unused: declaration never executes the
    Claude CLI. Any settings-write error is captured in ``errors`` — never
    raised.
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

    ``wired`` is the target-aware declaration set. When provided, only reviewed
    defaults present in it and effectively ``true`` after project/local
    precedence are eligible. ``None`` preserves the legacy all-defaults direct
    call; installer/init pass their selected set.

    ``enabled=False`` installs nothing (selected targets land in ``skipped``). When
    the ``claude`` CLI is unavailable — or :data:`SKIP_INSTALL_ENV` is set on the
    production path — every target lands in ``deferred`` (the wired declaration
    still lets Claude Code install on next session). Each install is idempotent
    (a no-op if already present) and best-effort: a CLI rejection is recorded in
    ``errors``, never raised.

    ``runner`` defaults to :func:`default_runner` (real subprocess). Injecting a
    runner is the test seam and also bypasses :data:`SKIP_INSTALL_ENV`, so unit
    tests exercise the install logic regardless of the ambient env guard.
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
