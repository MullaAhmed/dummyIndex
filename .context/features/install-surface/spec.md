# Install surface — spec

confidence: INFERRED

## Intent

Install dummyindex's host-specific skill family and, when the target is a Git
repository, leave that repository ready for the selected host without destroying
curated context or user-owned settings. The core policy is host-aware project
initialisation plus reviewed default-plugin reconciliation; skill copying, CLI
parsing, reporting, and teardown are plumbing around that policy. Claude-enabled
installs add managed guidance, hooks, and reviewed plugins, while Codex-only
installs add project guidance and deliberately avoid Claude plugin state
(`dummyindex/installer/install.py:37-58`,
`dummyindex/installer/install.py:134-163`).

## User-visible behavior

### Installation and project initialisation

`dummyindex install` accepts `--platform claude|codex|both`, user or project
scope, an optional target directory, and a skill-only mode. It installs the main
skill plus its companion and sibling skills for each selected host; Claude also
gets slash-command aliases, and user-scope installs register the relevant host
guidance (`dummyindex/installer/install.py:26-132`). The entry point remains thin:
it parses the seven install values and forwards them to `install`
(`dummyindex/__main__.py:270-289`).

If the resolved target is a Git repository and `--skill-only` is absent, install
auto-initialises it. A curated `.context/` takes the deterministic refresh path
so feature taxonomy and authored feature docs survive; a fresh or deterministic
index takes the full-build path. Both paths write the selected project guidance,
and Claude-enabled paths install managed hooks, reconcile default plugins, and
refresh hash-baselined equipment when an equipment manifest exists
(`dummyindex/installer/install.py:337-465`,
`dummyindex/installer/install.py:468-509`). `--defaults` and `--no-onboarding`
write a host-aware config only when no config exists
(`dummyindex/installer/install.py:143-163`,
`dummyindex/installer/install.py:535-559`).

### Reviewed default plugins

The reviewed set is ordered and validated at import time:

- `superpowers@claude-plugins-official`, skills only, no code execution;
- `caveman@caveman`, pinned to
  `JuliusBrussee/caveman@0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0`,
  with skills, commands, and `SessionStart`/`UserPromptSubmit` Node command hooks;
- `i-have-adhd@i-have-adhd`, pinned to
  `ayghri/i-have-adhd@0241185d6c7f2d0763a988ce52eceb13ea9f5c1f`, with one
  skill and no executable hook.

Duplicate targets, defaults without reviewed surfaces, and third-party defaults
without a full lowercase 40-character commit SHA are rejected
(`dummyindex/context/default_plugins.py:118-202`). Before config reconciliation,
settings mutation, or a runner probe, the installer prints each third-party
source, immutable ref, reviewed surfaces, code-execution status, and the
`--no-default-plugins` escape hatch
(`dummyindex/context/default_plugins.py:205-223`,
`dummyindex/installer/install.py:629-643`).

`--no-default-plugins` is the canonical one-run opt-out;
`--no-superpowers` is a compatibility alias. Both collapse to one early gate, so
an opted-out run performs no default-plugin config migration/backfill, settings
read/write, runner probe, or trust disclosure
(`dummyindex/installer/args.py:8-29`,
`dummyindex/installer/args.py:63-147`,
`dummyindex/installer/install.py:56-60`,
`dummyindex/installer/install.py:597-612`).

### Config policy and migration

Config schema v4 persists `default_plugins_enabled` as `true`, `false`, or
`null`. A fresh Claude or both-host config seeds the three defaults and stores
`true`; a Codex-only baseline stores an empty ledger and `null`. Schema v1-v3
loads are migrated in memory: the old `wire_superpowers` boolean maps to the
whole reviewed set, non-empty legacy ledgers map to enabled, empty ledgers map to
disabled except for the exact historical Codex baseline, which maps to not
applicable (`dummyindex/context/domains/config.py:24-57`,
`dummyindex/context/domains/config.py:378-455`).

Before a Claude-enabled wiring pass, reconciliation preserves `false` as a
durable all-defaults opt-out, promotes `null` to `true`, and appends missing
reviewed defaults after existing custom entries without reordering them. Codex
is mutation-free, malformed config fails closed, and no-op reconciliation does
not rewrite the file (`dummyindex/context/domains/config.py:622-659`,
`dummyindex/installer/install.py:634-653`). Equipment-installed plugins are
folded into the same `wired` ledger before defaults are appended, preserving
custom intent (`dummyindex/context/domains/config.py:567-619`).

### Declaration, materialisation, and tombstones

Wiring and installation are separate passes. `wire_default_plugins` declares
eligible plugin targets in project `.claude/settings.json` and declares pinned
third-party marketplaces without overwriting a conflicting marketplace name. A
`false` value in either project or local settings is a tombstone and is never
re-enabled; skills and malformed plugin targets are reported as needs-user
instead of being guessed (`dummyindex/context/default_plugins.py:337-421`,
`dummyindex/context/default_plugins.py:448-530`).

`install_default_plugins` materialises only reviewed defaults that are both in
the selected `wired` ledger and effectively enabled after project/local
precedence. It probes the Claude CLI once, defers when the CLI or install-time
network path is unavailable, and records per-target failures without raising;
the declaration remains the team-shared source of intent
(`dummyindex/context/default_plugins.py:645-729`).

### Project guidance

Claude and Codex project guidance carry one shared always-on output policy:
combine the caveman and ADHD behaviors, lead with the outcome or next action,
keep prose compact, number multi-step work, suppress tangents, restate current
state, and retain technical and safety detail. Explicit user formatting and
safety requirements take precedence (`dummyindex/context/output/bootstrap.py:26-45`,
`dummyindex/context/output/agents_md.py:33-52`). The policy is project-scoped in
Codex guidance and is not copied into the user-global Codex block
(`dummyindex/context/output/agents_md.py:54-65`,
`dummyindex/context/output/agents_md.py:110-129`).

## Contracts

- `parse_install_args(args: list[str]) -> tuple[str, Path | None, bool, bool, bool, bool, str]`
  returns `(scope, project_dir, skill_only, no_onboarding, defaults,
  no_default_plugins, platform)`; help exits 0 and invalid arguments exit 2
  (`dummyindex/installer/args.py:63-147`).
- `install(*, scope: str = "user", project_dir: Path | None = None,
  skill_only: bool = False, no_onboarding: bool = False, defaults: bool = False,
  no_default_plugins: bool = False, no_superpowers: bool = False,
  platform: str = "claude") -> None` installs the selected host surfaces and
  performs host-aware auto-init when applicable
  (`dummyindex/installer/install.py:26-60`).
- `_auto_init_project(project_root: Path, *, no_default_plugins: bool = False,
  no_superpowers: bool = False, platform: str = "claude",
  codex_guidance_owner: str = "project") -> bool` reports whether the primary
  build or deterministic refresh succeeded; secondary integration failures are
  warnings (`dummyindex/installer/install.py:337-465`).
- `default_wired() -> tuple[WiredEntry, ...]` adapts the reviewed defaults to the
  config ledger (`dummyindex/context/default_plugins.py:226-244`).
- `wire_default_plugins(wired: tuple[WiredEntry, ...], project_root: Path, *,
  enabled: bool = True, runner: Runner | None = None) -> PluginWireResult`
  performs declaration only and never raises for settings failures
  (`dummyindex/context/default_plugins.py:448-530`).
- `install_default_plugins(project_root: Path, *, wired: tuple[WiredEntry, ...] |
  None = None, enabled: bool = True, runner: Runner | None = None) ->
  PluginInstallResult` materialises the selected, effectively-enabled reviewed
  defaults through the runner seam (`dummyindex/context/default_plugins.py:645-729`).
- `default_config(*, platform: str = "claude") -> Config` produces the
  host-aware schema-v4 baseline
  (`dummyindex/context/domains/config.py:424-455`).
- `reconcile_default_plugins(context_dir: Path, *, platform: str) -> bool`
  upgrades applicability and appends missing defaults without overriding a
  durable opt-out (`dummyindex/context/domains/config.py:622-659`).
- `bootstrap_project_agents_md(project_root: Path, *, owner: str = "project") ->
  Path` writes the managed Codex project block at the active instruction target
  (`dummyindex/context/output/agents_md.py:110-129`).

## Examples

```bash
dummyindex install --platform claude
dummyindex install --platform both --dir ./repo --defaults
dummyindex install --platform codex --scope project --dir ./repo
dummyindex install --no-default-plugins
dummyindex install --no-superpowers       # compatibility alias
DUMMYINDEX_SKIP_PLUGIN_INSTALL=1 dummyindex install
dummyindex uninstall --platform both --scope project --dir ./repo
```
