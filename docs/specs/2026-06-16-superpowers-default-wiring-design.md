# Wire `superpowers` as a default plugin on dummyindex init

- **Date:** 2026-06-16
- **Status:** Approved (design) → ready for implementation plan
- **Author:** Ahmed Mulla (with Claude Code)

## Summary

When dummyindex first initializes a repository, it should automatically enable the
**`superpowers@claude-plugins-official`** plugin in the project's
`.claude/settings.json`, on by default, with an opt-out. This makes the
superpowers skill family available to every Claude Code session in a
dummyindex-managed repo without a manual `equip install` step.

## Motivation

dummyindex already writes per-repo Claude Code wiring at init time (the
`SessionStart`/`Stop`/`PreCompact` drift hooks and the managed `CLAUDE.md`
block). The superpowers plugin is a high-value, broadly-applicable toolkit
(brainstorming, TDD, debugging, planning skills). Wiring it as a sane default
removes a setup step and makes a fresh dummyindex repo "batteries included."

## Decisions (resolved with the user)

| Fork | Decision | Rationale |
|------|----------|-----------|
| **Source** | `superpowers@claude-plugins-official` | Anthropic-official marketplace — `trusted=True` in `SEED_MARKETPLACES`, natively known to every Claude Code install, and exactly how superpowers is installed today. **Enable-only**: no `extraKnownMarketplaces` entry needed. |
| **Settings file** | Project `<repo>/.claude/settings.json` | Committed + shared; the same file dummyindex already writes the drift hook into. Consistent with existing managed-block behavior. |
| **Default** | On by default + opt-out | Matches the "default wired plugin" intent. Opt out via `--no-superpowers` CLI flag or `.context/config.json` `wire_superpowers: false`. |
| **Uninstall** | Leave superpowers enabled | `dummyindex uninstall` removes *dummyindex's own* plumbing (hooks, managed block). Superpowers is a user-facing capability they may now depend on; ripping it out on uninstall would surprise. Reversible by hand or `/plugin`. |

### Explicitly out of scope

- **`obra/superpowers` upstream marketplace** — rejected in favor of the trusted official source.
- **`equipment.json` recording** — the equip ledger may not exist at init. Confirmed `equip status` only reconciles plugins it recorded, so an enabled-but-unrecorded plugin is invisible to it, never false-flagged. Init wiring stays fully decoupled from the equip manifest.
- **User-scope (`~/.claude/settings.json`) wiring** — this feature is per-repo only.
- **Extending the default-plugin set** — the data structure is built to be extended (a tuple), but superpowers is the only default we ship now (YAGNI).

## Architecture

### New module: `dummyindex/context/default_plugins.py`

Base-layer module (sibling of `claude_plugins.py` / `claude_settings.py`).
Pure orchestration over the existing `enable_plugin` primitive. **Imports only
from the base `context/` layer** (`claude_plugins`, `claude_settings`) — never
from `cli/`, `installer/`, or `context/domains/` — to preserve strict layering.

```python
@dataclass(frozen=True)
class DefaultPlugin:
    plugin: str
    marketplace: str

# The only default we ship today; a tuple so adding more is a one-line edit.
DEFAULT_PLUGINS: tuple[DefaultPlugin, ...] = (
    DefaultPlugin(plugin="superpowers", marketplace="claude-plugins-official"),
)

@dataclass(frozen=True)
class PluginWireResult:
    """Outcome of a wire_default_plugins call. Mirrors HookResult: carries
    errors rather than raising, so a settings snag never fails init."""
    enabled: tuple[str, ...]      # "<plugin>@<marketplace>" newly enabled
    already: tuple[str, ...]      # already enabled somewhere — left alone
    skipped: tuple[str, ...]      # not attempted because enabled=False
    errors: tuple[tuple[str, str], ...]  # (target, message)

def resolve_enabled(*, cli_opt_out: bool, config_value: bool | None) -> bool:
    """Pure precedence resolver. CLI flag wins; else config; else default on."""
    if cli_opt_out:
        return False
    return True if config_value is None else config_value

def wire_default_plugins(
    project_root: Path, *, enabled: bool = True
) -> PluginWireResult:
    """For each DEFAULT_PLUGINS entry, enable it in the project settings.json
    unless already enabled in project settings.json / settings.local.json /
    user settings.json. enabled=False → wire nothing (all skipped)."""
```

Behavior of `wire_default_plugins`:

- `enabled=False` → return all targets in `skipped`, write nothing.
- For each default: if already enabled in **any** of the three settings files
  (project `settings.json`, project `settings.local.json`, user
  `~/.claude/settings.json`), record it in `already` and skip — respects an
  existing user choice and avoids a redundant write.
- Otherwise call `enable_plugin(<repo>/.claude/settings.json, plugin=…,
  marketplace=…)` and record in `enabled`.
- Catch `MalformedSettingsError` / `OSError`, record `(target, str(exc))` in
  `errors`, **never raise**. (A malformed settings.json is left untouched by
  the underlying preserve-or-refuse contract.)

A private `_already_enabled(project_root, target) -> bool` reads the three
settings files via `claude_settings.load_settings` (treating
`MalformedSettingsError`/`OSError` as "not enabled", like equip's
`_already_enabled_in`).

### Config schema change: `dummyindex/context/domains/config.py`

Add an optional `wire_superpowers: bool = True` field to `Config`
(back-compat, **no `schema_version` bump** — mirrors how `reconcile_exclude`
was added):

- `from_dict`: `payload.get("wire_superpowers", True)`; reject non-bool with `ConfigError`.
- `to_dict`: emit `"wire_superpowers": self.wire_superpowers`.
- `default_config()`: pass `wire_superpowers=True` (explicit, for `--defaults`).
- Absent key in an existing config → reads as `True` (default on).

### Opt-out resolution & precedence

At each init call site:

1. Read `--no-superpowers` from the CLI args → `cli_opt_out: bool`.
2. Load config: `cfg = read_config(<root>/.context)` (catch `ConfigError` → treat as `None`, best-effort); `config_value = cfg.wire_superpowers if cfg else None`.
3. `enabled = resolve_enabled(cli_opt_out=cli_opt_out, config_value=config_value)`.
4. `result = wire_default_plugins(root, enabled=enabled)`; print a one-line outcome.

**Timing note:** at a fresh `dummyindex install`, `.context/config.json`
usually does not exist yet (it's written later by onboarding or `--defaults`),
so `config_value is None` → default on, as intended. A persisted
`wire_superpowers: false` survives re-inits.

## Call sites & data flow

Two init seams converge here (both confirmed):

| Entry point | Code path | Covers |
|---|---|---|
| `dummyindex install` (auto-init) | `installer/install.py::_auto_init_project` | the `install` command |
| `dummyindex ingest` / `context init` | `cli/init.py::run` | the CLI **and** the `/dummyindex` skill's Phase 1 (`ingest` → `init`) |

### `dummyindex/installer/install.py`

- `install(...)` gains `no_superpowers: bool = False`.
- After `_install_project_hooks` succeeds in `_auto_init_project` (both the
  full-build and the enriched-refresh paths), resolve enabled-ness and call
  `wire_default_plugins`. Print, e.g.:
  - `  superpowers      ->  enabled (superpowers@claude-plugins-official)`
  - `  superpowers      ->  already enabled (left as-is)`
  - `  superpowers      ->  skipped (--no-superpowers)`
  - `  superpowers      ->  warning: <error>` (to stderr; init still succeeds)

### `dummyindex/cli/init.py`

- Pull `--no-superpowers` out of args alongside `--no-hooks` / `--force`.
- After the hook-install block, run the same resolve + wire + print sequence.

### `dummyindex/installer/args.py`

- `parse_install_args` return tuple grows to 6:
  `(scope, project_dir, skill_only, no_onboarding, defaults, no_superpowers)`.
- Parse `--no-superpowers`. Add it to `_INSTALL_USAGE`.

### `dummyindex/__main__.py`

- Unpack the 6-tuple for `cmd == "install"`; pass `no_superpowers=…` to `install()`.
- `cmd == "uninstall"` already does `scope, project_dir, *_rest` — unaffected.

### Docs (disclosure)

- `dummyindex/skills/skill.md` — Phase 0 / "what dummyindex writes" gets a line noting superpowers is wired into `settings.json` on init (and how to opt out).
- `dummyindex/cli/preflight.py` — the preflight summary mentions the pending superpowers wiring so the skill flow discloses it before any write.

## Error handling, idempotency & safety

- **Idempotent:** the 3-file pre-check skips an already-enabled plugin; `enable_plugin` itself also returns `False` when the key is already `true`.
- **Preserve-or-refuse:** a malformed `settings.json` is never overwritten (existing `claude_settings` contract); the error is reported and init still succeeds (partial success, like a hook snag).
- **No domain coupling:** the base module imports nothing from `domains/` or `cli/`; config resolution happens at the call sites, which may freely import `domains/config.py` (`cli/` and `installer/` are top layers — `cli/init.py` adds the `read_config` import; `installer/install.py` already has it via `_write_default_config`).
- **Atomic writes:** inherited from `enable_plugin` → `write_settings` (tmp + rename).

## Testing (TDD — write tests first)

- **`tests/context/test_default_plugins.py`** (new, `@pytest.mark.unit`):
  - `resolve_enabled`: flag wins (`cli_opt_out=True` → False even if config True); config honored; `None` → True.
  - `wire_default_plugins(enabled=True)` enables `superpowers@claude-plugins-official` into a fresh `settings.json` (assert `enabledPlugins` key, no `extraKnownMarketplaces`).
  - already-enabled in project `settings.json` → `already`, no write; likewise when enabled in `settings.local.json` and in user `~/.claude/settings.json` (monkeypatch `Path.home`).
  - `enabled=False` → writes nothing, all targets in `skipped`.
  - malformed `settings.json` → `errors` populated, file content untouched, no raise.
  - idempotent re-run → second call reports `already`.
- **`tests/test_install.py`** (update + add):
  - update every `parse_install_args` tuple assertion to the 6-tuple; add `test_parse_no_superpowers_flag`.
  - integration: default `install` auto-init enables superpowers; `--no-superpowers` skips; a pre-existing `wire_superpowers: false` config skips.
- **`tests/cli/test_init_cli.py` / `test_ingest_command.py`**: `ingest`/`init` enables superpowers by default; `--no-superpowers` skips.
- **`tests/context/domains/.../test config`**: round-trip the new `wire_superpowers` field; absent key defaults to `True`; non-bool → `ConfigError`; no `schema_version` bump.
- Full suite stays green (`pytest`), 80%+ coverage on the new module.

## Reporting / UX

Init output gains exactly one line per default plugin (see install.py examples
above), so the user always sees whether superpowers was enabled, already
present, skipped, or errored — never a silent settings.json mutation.
