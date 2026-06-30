# Default `superpowers` Plugin Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On first dummyindex init of a repo, enable `superpowers@claude-plugins-official` in the project's `.claude/settings.json` by default, with `--no-superpowers` and a `.context/config.json` opt-out.

**Architecture:** A new base-layer module `dummyindex/context/default_plugins.py` reuses `claude_plugins.enable_plugin` to enable a fixed set of default plugins, reporting outcomes via a frozen result (never raising). Two init seams call it — `installer/install.py` (the `install` auto-init) and `cli/init.py` (the `ingest`/`context init` path, which the `/dummyindex` skill drives). Opt-out is resolved at the call sites (CLI flag > `.context/config.json` `wire_superpowers` > default-on) so the base module never imports from `domains/` or `cli/`.

**Tech Stack:** Python 3.12, `from __future__ import annotations`, frozen `@dataclass`, pytest (`@pytest.mark.unit` / `@pytest.mark.integration`). Spec: `docs/specs/2026-06-16-superpowers-default-wiring-design.md`.

**Conventions to honor:** frozen dataclasses; module docstring stating the contract; base-layer modules import only base siblings; CLI boundary does the `print`/`sys.exit`; preserve-or-refuse on `settings.json`; black/ruff/isort formatting; snake_case functions, PascalCase classes.

**Branch:** all work on `feat/superpowers-default-wiring` (already checked out; spec committed).

---

### Task 1: Config field `wire_superpowers`

**Files:**
- Modify: `dummyindex/context/domains/config.py`
- Test: `tests/context/domains/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/context/domains/test_config.py`:

```python
@pytest.mark.unit
def test_default_config_wires_superpowers() -> None:
    from dummyindex.context.domains.config import default_config

    assert default_config().wire_superpowers is True


@pytest.mark.unit
def test_config_wire_superpowers_round_trips() -> None:
    from dummyindex.context.domains.config import Config

    cfg = default_config_with(wire_superpowers=False)
    assert cfg.to_dict()["wire_superpowers"] is False
    assert Config.from_dict(cfg.to_dict()).wire_superpowers is False


@pytest.mark.unit
def test_config_wire_superpowers_absent_defaults_true() -> None:
    from dummyindex.context.domains.config import Config, default_config

    payload = default_config().to_dict()
    payload.pop("wire_superpowers")
    assert Config.from_dict(payload).wire_superpowers is True


@pytest.mark.unit
def test_config_wire_superpowers_must_be_bool() -> None:
    from dummyindex.context.domains.config import Config, ConfigError, default_config

    payload = default_config().to_dict()
    payload["wire_superpowers"] = "yes"
    with pytest.raises(ConfigError):
        Config.from_dict(payload)
```

Add this helper near the top of the test module (after imports) if no equivalent exists:

```python
def default_config_with(**overrides: object):
    from dataclasses import replace
    from dummyindex.context.domains.config import default_config

    return replace(default_config(), **overrides)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/context/domains/test_config.py -k wire_superpowers -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'wire_superpowers'` / `AttributeError`.

- [ ] **Step 3: Implement the field**

In `dummyindex/context/domains/config.py`:

1. Add a default constant near the others (after `DEFAULT_AUTO_REFRESH_HOOK = True`):

```python
DEFAULT_WIRE_SUPERPOWERS = True
```

2. Add the field to the `Config` dataclass (after `reconcile_exclude`):

```python
    wire_superpowers: bool = DEFAULT_WIRE_SUPERPOWERS
```

3. In `to_dict`, add the key (after the `reconcile_exclude` line):

```python
            "wire_superpowers": self.wire_superpowers,
```

4. In `from_dict`, before the final `return cls(...)`, add:

```python
        wire_superpowers = payload.get("wire_superpowers", DEFAULT_WIRE_SUPERPOWERS)
        if not isinstance(wire_superpowers, bool):
            raise ConfigError("config.wire_superpowers must be a boolean")
```

   and pass it in the `return cls(...)` call:

```python
            wire_superpowers=wire_superpowers,
```

5. In `default_config()`, add to the `Config(...)` call:

```python
        wire_superpowers=DEFAULT_WIRE_SUPERPOWERS,
```

6. Add `"wire_superpowers": true,` to the schema doc comment block at the top (after the `auto_refresh_hook` line) for documentation parity.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/context/domains/test_config.py -v`
Expected: PASS (all config tests, including the new four).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/config.py tests/context/domains/test_config.py
git commit -m "feat(config): add wire_superpowers field (default true, no schema bump)"
```

---

### Task 2: `default_plugins.py` — dataclasses, `resolve_enabled`, `describe_wire_result`

**Files:**
- Create: `dummyindex/context/default_plugins.py`
- Test: `tests/context/test_default_plugins.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/context/test_default_plugins.py`:

```python
"""Tests for dummyindex's default-plugin wiring (context.default_plugins)."""

from __future__ import annotations

import pytest

from dummyindex.context.default_plugins import (
    DEFAULT_PLUGINS,
    DefaultPlugin,
    PluginWireResult,
    describe_wire_result,
    resolve_enabled,
)


@pytest.mark.unit
def test_default_plugins_contains_superpowers_official() -> None:
    assert DefaultPlugin("superpowers", "claude-plugins-official") in DEFAULT_PLUGINS
    target = DefaultPlugin("superpowers", "claude-plugins-official").target
    assert target == "superpowers@claude-plugins-official"


@pytest.mark.unit
def test_resolve_enabled_flag_wins() -> None:
    assert resolve_enabled(cli_opt_out=True, config_value=True) is False
    assert resolve_enabled(cli_opt_out=True, config_value=None) is False


@pytest.mark.unit
def test_resolve_enabled_honors_config() -> None:
    assert resolve_enabled(cli_opt_out=False, config_value=False) is False
    assert resolve_enabled(cli_opt_out=False, config_value=True) is True


@pytest.mark.unit
def test_resolve_enabled_defaults_on_when_no_config() -> None:
    assert resolve_enabled(cli_opt_out=False, config_value=None) is True


@pytest.mark.unit
def test_describe_wire_result_splits_info_and_warn() -> None:
    result = PluginWireResult(
        enabled=("superpowers@claude-plugins-official",),
        already=("a@b",),
        skipped=("c@d",),
        errors=(("e@f", "boom"),),
    )
    info, warn = describe_wire_result(result)
    assert any("enabled superpowers@claude-plugins-official" in line for line in info)
    assert any("a@b already enabled" in line for line in info)
    assert any("skipped c@d" in line for line in info)
    assert any("e@f" in line and "boom" in line for line in warn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/context/test_default_plugins.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dummyindex.context.default_plugins'`.

- [ ] **Step 3: Create the module (pure pieces only)**

Create `dummyindex/context/default_plugins.py`:

```python
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
```

(`wire_default_plugins` / `_already_decided` land in Task 3 — these tests don't exercise them.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/context/test_default_plugins.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/default_plugins.py tests/context/test_default_plugins.py
git commit -m "feat(context): default_plugins module — types, resolve_enabled, describe"
```

---

### Task 3: `wire_default_plugins` + `_already_decided`

**Files:**
- Modify: `dummyindex/context/default_plugins.py`
- Test: `tests/context/test_default_plugins.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/context/test_default_plugins.py`:

```python
import json
from pathlib import Path

from dummyindex.context.default_plugins import wire_default_plugins

_SUPERPOWERS = "superpowers@claude-plugins-official"


def _enabled_plugins(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8")).get("enabledPlugins", {})


@pytest.mark.unit
def test_wire_enables_superpowers_into_fresh_settings(tmp_path: Path) -> None:
    result = wire_default_plugins(tmp_path, enabled=True)

    settings = tmp_path / ".claude" / "settings.json"
    enabled = _enabled_plugins(settings)
    assert enabled.get(_SUPERPOWERS) is True
    # Official marketplace is natively known → no extraKnownMarketplaces entry.
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "extraKnownMarketplaces" not in data
    assert result.enabled == (_SUPERPOWERS,)
    assert result.already == ()


@pytest.mark.unit
def test_wire_disabled_writes_nothing(tmp_path: Path) -> None:
    result = wire_default_plugins(tmp_path, enabled=False)

    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert result.skipped == (_SUPERPOWERS,)
    assert result.enabled == ()


@pytest.mark.unit
def test_wire_skips_when_already_true_in_project_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )
    before = settings.read_text(encoding="utf-8")

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert result.enabled == ()
    assert settings.read_text(encoding="utf-8") == before  # untouched


@pytest.mark.unit
def test_wire_respects_explicit_false_in_project_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: False}}), encoding="utf-8"
    )

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert _enabled_plugins(settings).get(_SUPERPOWERS) is False  # NOT force-enabled


@pytest.mark.unit
def test_wire_skips_when_present_in_settings_local(tmp_path: Path) -> None:
    local = tmp_path / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.already == (_SUPERPOWERS,)
    assert not (tmp_path / ".claude" / "settings.json").exists()


@pytest.mark.unit
def test_wire_ignores_user_settings_writes_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A global (~/.claude) enable must NOT suppress the committed project entry."""
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {_SUPERPOWERS: True}}), encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(fake_home))
    repo = tmp_path / "repo"
    repo.mkdir()

    result = wire_default_plugins(repo, enabled=True)

    assert result.enabled == (_SUPERPOWERS,)
    assert _enabled_plugins(repo / ".claude" / "settings.json").get(_SUPERPOWERS) is True


@pytest.mark.unit
def test_wire_malformed_settings_reports_error_no_raise(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json", encoding="utf-8")

    result = wire_default_plugins(tmp_path, enabled=True)

    assert result.enabled == ()
    assert result.errors and result.errors[0][0] == _SUPERPOWERS
    assert settings.read_text(encoding="utf-8") == "{not json"  # untouched


@pytest.mark.unit
def test_wire_is_idempotent(tmp_path: Path) -> None:
    first = wire_default_plugins(tmp_path, enabled=True)
    second = wire_default_plugins(tmp_path, enabled=True)

    assert first.enabled == (_SUPERPOWERS,)
    assert second.enabled == ()
    assert second.already == (_SUPERPOWERS,)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/context/test_default_plugins.py -k wire -v`
Expected: FAIL — `ImportError: cannot import name 'wire_default_plugins'`.

- [ ] **Step 3: Implement `wire_default_plugins` + `_already_decided`**

Append to `dummyindex/context/default_plugins.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/context/test_default_plugins.py -v`
Expected: PASS (all ~13 tests).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/default_plugins.py tests/context/test_default_plugins.py
git commit -m "feat(context): wire_default_plugins — enable defaults into project settings.json"
```

---

### Task 4: `--no-superpowers` flag in `parse_install_args`

**Files:**
- Modify: `dummyindex/installer/args.py`
- Test: `tests/test_install.py`

- [ ] **Step 1: Update existing tuple assertions + add the new test**

In `tests/test_install.py`, every `parse_install_args(...)` assertion currently
compares against a **5-tuple** `(scope, project_dir, skill_only, no_onboarding, defaults)`.
Append `, False` (the new `no_superpowers` default) to each. Concretely:

- `test_parse_defaults_user_scope_no_dir`: `("user", None, False, False, False)` → `("user", None, False, False, False, False)`.
- `test_parse_scope_long_form`: `("project", None, False, False, False)` → `(..., False)`.
- `test_parse_scope_equals_form`: same `+ , False`.
- `test_parse_skill_only_flag`: both tuples `("user", None, True, False, False)` → `(..., False)` and `("project", None, True, False, False)` → `(..., False)`.
- `test_parse_no_onboarding_and_defaults_flags`: all three tuples gain a trailing `, False`.
- For the destructuring tests (`test_parse_dir_long_form`, `test_parse_dir_equals_form`) that unpack the tuple, add a trailing capture variable, e.g.
  `scope, project_dir, skill_only, no_onboarding, defaults, no_superpowers = parse_install_args([...])` (or `*_ ` for the trailing field).

Then add the new test:

```python
@pytest.mark.unit
def test_parse_no_superpowers_flag() -> None:
    assert parse_install_args(["--no-superpowers"]) == (
        "user",
        None,
        False,
        False,
        False,
        True,
    )
    assert parse_install_args([]) == ("user", None, False, False, False, False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install.py -k parse -v`
Expected: FAIL — tuple length mismatch (5 vs 6) / new flag not parsed.

- [ ] **Step 3: Implement the flag**

In `dummyindex/installer/args.py`:

1. Update the return annotation:

```python
def parse_install_args(
    args: list[str],
) -> tuple[str, Optional[Path], bool, bool, bool, bool]:
```

2. Initialise the new var (after `defaults = False`):

```python
    no_superpowers = False
```

3. Add a parse branch (after the `--defaults` branch):

```python
        elif a == "--no-superpowers":
            no_superpowers = True
            i += 1
```

4. Update the return:

```python
    return scope, project_dir, skill_only, no_onboarding, defaults, no_superpowers
```

5. Add to `_INSTALL_USAGE` (after the `--defaults` line):

```
  --no-superpowers       don't enable the superpowers plugin on init
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_install.py -k parse -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/installer/args.py tests/test_install.py
git commit -m "feat(install): parse --no-superpowers flag"
```

---

### Task 5: Wire defaults in `install` auto-init (+ `__main__` dispatch)

**Files:**
- Modify: `dummyindex/installer/install.py`
- Modify: `dummyindex/__main__.py:245-256`
- Test: `tests/test_install.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_install.py` (the `install`, `SKILL_REL` imports already exist; add `import json` at the top if not present):

```python
_SUPERPOWERS = "superpowers@claude-plugins-official"


def _enabled_plugins(repo: Path) -> dict:
    import json

    settings = repo / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    return json.loads(settings.read_text(encoding="utf-8")).get("enabledPlugins", {})


@pytest.mark.integration
def test_install_auto_init_enables_superpowers_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)

    assert _enabled_plugins(repo).get(_SUPERPOWERS) is True
    assert "plugins" in capsys.readouterr().out


@pytest.mark.integration
def test_install_no_superpowers_flag_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo, no_superpowers=True)

    assert _SUPERPOWERS not in _enabled_plugins(repo)


@pytest.mark.integration
def test_install_config_opt_out_skips_superpowers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-existing .context/config.json with wire_superpowers=false opts out."""
    import json

    repo = tmp_path / "repo"
    _make_repo_with_source(repo)
    # Pre-seed an enriched-or-not index dir with a config that opts out.
    ctx = repo / ".context"
    ctx.mkdir(parents=True)
    from dummyindex.context.domains.config import default_config, write_config
    from dataclasses import replace

    write_config(ctx, replace(default_config(), wire_superpowers=False))
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    install(scope="project", project_dir=repo)

    assert _SUPERPOWERS not in _enabled_plugins(repo)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install.py -k superpowers -v`
Expected: FAIL — `install()` has no `no_superpowers` kwarg / superpowers not enabled.

- [ ] **Step 3: Thread the flag + wiring step in `install.py`**

In `dummyindex/installer/install.py`:

1. Add the parameter to `install(...)` (after `defaults: bool = False,`):

```python
    no_superpowers: bool = False,
```

2. Update the auto-init call site (replace the existing `_auto_init_project` call):

```python
    if not skill_only and target_is_repo:
        init_ran = _auto_init_project(auto_init_target, no_superpowers=no_superpowers)
        if init_ran and (defaults or no_onboarding):
            _write_default_config(auto_init_target)
```

3. Change `_auto_init_project`'s signature:

```python
def _auto_init_project(project_root: Path, *, no_superpowers: bool = False) -> bool:
```

4. In **both** return branches of `_auto_init_project`, replace
   `return _install_project_hooks(project_root, install_hooks_fn)` with:

```python
    hooks_ok = _install_project_hooks(project_root, install_hooks_fn)
    _wire_default_plugins_step(project_root, no_superpowers=no_superpowers)
    return hooks_ok
```

5. Add the new helper at the end of the module:

```python
def _wire_default_plugins_step(project_root: Path, *, no_superpowers: bool) -> None:
    """Enable dummyindex's default plugins in the project settings.json.

    Best-effort, like the hook install: a settings snag is reported but never
    fails the init. Reads ``.context/config.json`` (if present) for a persisted
    opt-out; the ``--no-superpowers`` flag overrides it.
    """
    from dummyindex.context.default_plugins import (
        describe_wire_result,
        resolve_enabled,
        wire_default_plugins,
    )

    config_value: bool | None = None
    try:
        from dummyindex.context.domains.config import ConfigError, read_config

        cfg = read_config(project_root / ".context")
        config_value = cfg.wire_superpowers if cfg is not None else None
    except ConfigError:
        config_value = None

    enabled = resolve_enabled(cli_opt_out=no_superpowers, config_value=config_value)
    result = wire_default_plugins(project_root, enabled=enabled)
    info, warn = describe_wire_result(result)
    for line in info:
        print(f"  {line}")
    for line in warn:
        print(f"  {line}", file=sys.stderr)
```

- [ ] **Step 4: Update `__main__.py` dispatch**

In `dummyindex/__main__.py`, the `cmd == "install"` block (≈245-256):

```python
    if cmd == "install":
        (
            scope,
            project_dir,
            skill_only,
            no_onboarding,
            defaults,
            no_superpowers,
        ) = parse_install_args(sys.argv[2:])
        install(
            scope=scope,
            project_dir=project_dir,
            skill_only=skill_only,
            no_onboarding=no_onboarding,
            defaults=defaults,
            no_superpowers=no_superpowers,
        )
        return
```

(The `cmd == "uninstall"` block uses `scope, project_dir, *_rest` — unchanged.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_install.py -v`
Expected: PASS (all install tests, including the three new superpowers ones).

- [ ] **Step 6: Commit**

```bash
git add dummyindex/installer/install.py dummyindex/__main__.py tests/test_install.py
git commit -m "feat(install): wire superpowers by default on auto-init (flag + config opt-out)"
```

---

### Task 6: Wire defaults in `cli/init.py` (`ingest` / `context init`)

**Files:**
- Modify: `dummyindex/cli/init.py`
- Test: `tests/cli/test_init_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/cli/test_init_cli.py` (imports `Path`, `pytest`, `from dummyindex.cli import init` already present; add `import json`):

```python
_SUPERPOWERS = "superpowers@claude-plugins-official"


def _make_min_repo(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (target / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8"
    )


def _enabled(repo: Path) -> dict:
    settings = repo / ".claude" / "settings.json"
    if not settings.exists():
        return {}
    return json.loads(settings.read_text(encoding="utf-8")).get("enabledPlugins", {})


@pytest.mark.integration
def test_init_enables_superpowers_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["."])

    assert rc == 0
    assert _enabled(repo).get(_SUPERPOWERS) is True


@pytest.mark.integration
def test_init_no_superpowers_flag_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _make_min_repo(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(repo)

    rc = init.run(["--no-superpowers", "."])

    assert rc == 0
    assert _SUPERPOWERS not in _enabled(repo)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_init_cli.py -k superpowers -v`
Expected: FAIL — superpowers not enabled / `--no-superpowers` rejected as unknown arg.

- [ ] **Step 3: Implement in `cli/init.py`**

In `dummyindex/cli/init.py::run`:

1. Pull the flag out alongside `--no-hooks` / `--force` (replace those three lines):

```python
    install_hooks = "--no-hooks" not in args
    force = "--force" in args
    no_superpowers = "--no-superpowers" in args
    args = [a for a in args if a not in ("--no-hooks", "--force", "--no-superpowers")]
```

2. After the `if install_hooks:` hook-install block (just before `return 0`), add:

```python
    from dummyindex.context.default_plugins import (
        describe_wire_result,
        resolve_enabled,
        wire_default_plugins,
    )

    config_value: bool | None = None
    try:
        from dummyindex.context.domains.config import ConfigError, read_config

        cfg = read_config(out_root / ".context")
        config_value = cfg.wire_superpowers if cfg is not None else None
    except ConfigError:
        config_value = None

    enabled = resolve_enabled(cli_opt_out=no_superpowers, config_value=config_value)
    wire_result = wire_default_plugins(out_root, enabled=enabled)
    info, warn = describe_wire_result(wire_result)
    for line in info:
        print(f"  {line}")
    for line in warn:
        print(f"  {line}", file=sys.stderr)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/cli/test_init_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/init.py tests/cli/test_init_cli.py
git commit -m "feat(ingest): wire superpowers by default on init (flag + config opt-out)"
```

---

### Task 7: Disclose the wiring in the skill doc

**Files:**
- Modify: `dummyindex/skills/skill.md:169` (the "What you get:" list)

- [ ] **Step 1: Add the disclosure bullet**

In `dummyindex/skills/skill.md`, immediately after the line
`- A drift manifest at \`.context/cache/manifest.json\`.` (≈line 169), insert:

```markdown
- The **`superpowers` plugin** enabled in `.claude/settings.json`
  (`enabledPlugins["superpowers@claude-plugins-official"]`) — a sane default
  wired on first init. Opt out with `--no-superpowers` or
  `"wire_superpowers": false` in `.context/config.json`. An existing per-repo
  decision (the key already present, enabled or disabled) is left as-is.
```

- [ ] **Step 2: Verify no skill-content test breaks**

Run: `pytest tests/ -k "skill" -q`
Expected: PASS (or "no tests ran" — there is no strict skill-body snapshot test; if one asserts a phrase, confirm it still holds).

- [ ] **Step 3: Commit**

```bash
git add dummyindex/skills/skill.md
git commit -m "docs(skill): disclose default superpowers wiring + opt-out"
```

---

### Task 8: Full-suite verification + coverage

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -q`
Expected: PASS — all tests green (existing + new).

- [ ] **Step 2: Coverage on the new module**

Run: `pytest --cov=dummyindex.context.default_plugins --cov=dummyindex.context.domains.config --cov-report=term-missing tests/context/test_default_plugins.py tests/context/domains/test_config.py`
Expected: `dummyindex/context/default_plugins.py` ≥ 80% (target 100% — it's small and fully exercised).

- [ ] **Step 3: Lint / format / type-check**

Run: `ruff check dummyindex/ && black --check dummyindex/ tests/ && mypy dummyindex/context/default_plugins.py`
Expected: clean (fix any findings, re-run).

- [ ] **Step 4: Manual smoke (optional, in a scratch repo)**

```bash
cd $(mktemp -d) && git init -q && printf 'def f():\n    return 1\n' > a.py
dummyindex ingest .
python3 -c "import json; print(json.load(open('.claude/settings.json'))['enabledPlugins'])"
```
Expected: prints a dict containing `'superpowers@claude-plugins-official': True`.

- [ ] **Step 5: No commit** (verification only). If lint/format changed files, commit them:

```bash
git add -A && git commit -m "chore: lint/format pass for superpowers wiring"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:

| Spec item | Task |
|---|---|
| New `default_plugins.py` module (types, `resolve_enabled`, `describe_wire_result`) | 2 |
| `wire_default_plugins` + `_already_decided` (project-files-only, enable-only) | 3 |
| Config `wire_superpowers` field (no schema bump, default true) | 1 |
| Opt-out precedence (flag > config > on) | 2 (resolve), 5 + 6 (call sites) |
| `--no-superpowers` in `installer/args.py` | 4 |
| `install` auto-init call site + `__main__` dispatch | 5 |
| `cli/init.py` (`ingest`/`context init`, skill Phase 1) call site | 6 |
| Enable-only (no `extraKnownMarketplaces`) | 3 (test asserts absence) |
| Decoupled from `equipment.json` | inherent (no equip code touched) |
| Uninstall leaves superpowers enabled | inherent (`uninstall.py` untouched — no task) |
| Disclosure: SKILL.md bullet + live output line | 7 (doc) + 5/6 (output) |
| Preflight disclosure | **Deferred** (noted in spec; live output + SKILL.md cover it) |
| Tests + 80%+ coverage | 1,2,3,5,6 + 8 |

**2. Placeholder scan** — no TBD/TODO; every code step shows full code; every test step shows the assertion. ✔

**3. Type consistency** — `DefaultPlugin.target`, `PluginWireResult` field names (`enabled`/`already`/`skipped`/`errors`), `resolve_enabled(cli_opt_out=, config_value=)`, `wire_default_plugins(project_root, *, enabled=)`, `_already_decided`, `_wire_default_plugins_step(project_root, *, no_superpowers=)`, and the 6-tuple from `parse_install_args` are used identically across Tasks 2–6. ✔

**Known deviation from spec:** the preflight inventory line (spec §"Docs") is deferred — disclosure is delivered by the live init-output line (Tasks 5/6) and the SKILL.md bullet (Task 7) instead, to avoid touching the preflight domain renderer.
