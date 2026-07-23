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
(`dummyindex/installer/install.py:39-76`,
`dummyindex/installer/install.py:203-231`).

## User-visible behavior

### Installation and project initialisation

`dummyindex install` accepts `--platform claude|agents|both` (plus
`--dedupe user|project` and `--force-downgrade`), user or project scope, an
optional target directory, and a skill-only mode. `codex` is a deprecated alias:
`normalize_platform_arg()` maps `agents` to the internal `"codex"` token, passes
`claude`/`both` through, and accepts `codex` while printing a one-time
`warning: --platform codex is deprecated, use --platform agents` to stderr;
anything else raises `ValueError` and the parser exits 2 with
`--platform must be claude|agents|both`. `SUPPORTED_PLATFORMS`, `platforms_for()`,
and every internal `"codex"` comparison are unchanged
(`dummyindex/installer/common.py:112-137`,
`dummyindex/installer/common.py:96-103`, `dummyindex/installer/args.py:22-25`,
`dummyindex/installer/args.py:150-157`). Relatedly, the `.agents/skills` copy is
no longer Codex-specific: `render_skill()` prepends `_PORTABLE_HOST_PREAMBLE`, a
3-row behavior-class map (Claude Code / skill-native hosts / generic fallback),
in place of the removed `_CODEX_SKILL_PREAMBLE`
(`dummyindex/installer/common.py:66-93`,
`dummyindex/installer/common.py:152-171`).

It installs the main skill plus its companion and sibling skills for each
selected host; Claude also gets slash-command aliases, and user-scope installs
register the relevant host guidance (`dummyindex/installer/install.py:157-201`).
Every run also plans a repair pass: `plan_repairs()` from
`dummyindex/installer/repair.py` runs scoped to the invocation's selected
platforms and target scope, over a single four-root `.dummyindex_version`
scanner (`scan_installed_copies`, `dummyindex/installer/repair.py:175-203`).
`_install_skill_family` is therefore conditional — a host whose family dir is
absent, or exists but is unprovable (`is_owned_copy()` false: no version stamp
and no legacy `## Codex host compatibility` heading), is written directly, while
any provable existing dir defers entirely to `execute_repairs()` so it is never
double-written (`dummyindex/installer/install.py:157-171`,
`dummyindex/installer/repair.py:490-505`). A stale proven copy at the targeted
scope root is rewritten; stale copies at other roots and user+project duplicates
are report-only with a remediation hint; downgrade and unknown stamps are
report-only unless `--force-downgrade`
(`dummyindex/installer/repair.py:213-321`,
`dummyindex/installer/repair.py:538-597`). `--dedupe user|project` then calls
`repair.dedupe()`, which reuses `uninstall._remove_skill_family()` to remove
that scope's copy of a family proven duplicated at both scopes, filtered to the
invocation's platforms, best-effort with per-copy error isolation
(`dummyindex/installer/install.py:175-187`,
`dummyindex/installer/repair.py:369-443`,
`dummyindex/installer/uninstall.py:82-166`). The entry point remains thin: it
parses the nine install values — `(scope, project_dir, skill_only,
no_onboarding, defaults, no_default_plugins, platform, dedupe, force_downgrade)`
— and forwards them to `install` (`dummyindex/__main__.py:289-312`).

If the resolved target is a Git repository and `--skill-only` is absent, install
auto-initialises it. A curated `.context/` takes the deterministic refresh path
so feature taxonomy and authored feature docs survive; a fresh or deterministic
index takes the full-build path. Both paths write the selected project guidance,
and Claude-enabled paths install managed hooks, reconcile default plugins, and
refresh hash-baselined equipment when an equipment manifest exists
(`dummyindex/installer/install.py:406-534`,
`dummyindex/installer/install.py:537-578`). `--defaults` and `--no-onboarding`
write a host-aware config only when no config exists
(`dummyindex/installer/install.py:212-231`,
`dummyindex/installer/install.py:604-628`).

### Reviewed default plugins

The reviewed set is ordered and validated at import time:

- `superpowers@claude-plugins-official`, skills only, no code execution;
- `caveman@caveman`, from `JuliusBrussee/caveman` (tracks the latest upstream
  default branch),
  with skills, commands, and `SessionStart`/`UserPromptSubmit` Node command hooks;
- `i-have-adhd@i-have-adhd`, from `ayghri/i-have-adhd` (tracks the latest
  upstream default branch), with one
  skill and no executable hook.

Third-party defaults carry no commit pin: Claude Code materialises
marketplaces with `git clone --branch <ref>`, which accepts branch/tag names
but never a commit SHA, so a SHA pin can never install (dummyindex <= 0.33.x
pinned SHAs and every third-party default failed to materialise). Duplicate
targets and defaults without reviewed surfaces are rejected
(`dummyindex/context/default_plugins.py`). Before config reconciliation,
settings mutation, or a runner probe, the installer prints each third-party
source, reviewed surfaces, code-execution status, and the
`--no-default-plugins` escape hatch.

`--no-default-plugins` is the canonical one-run opt-out;
`--no-superpowers` is a compatibility alias. Both collapse to one early gate, so
an opted-out run performs no default-plugin config migration/backfill, settings
read/write, runner probe, or trust disclosure
(`dummyindex/installer/args.py:10-37`,
`dummyindex/installer/args.py:72-181`,
`dummyindex/installer/install.py:58-77`,
`dummyindex/installer/install.py:666-681`).

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
`dummyindex/installer/install.py:703-722`). Equipment-installed plugins are
folded into the same `wired` ledger before defaults are appended, preserving
custom intent (`dummyindex/context/domains/config.py:567-619`).

### Declaration, materialisation, and tombstones

Wiring and installation are separate passes. `wire_default_plugins` declares
eligible plugin targets in project `.claude/settings.json` and declares
unpinned third-party marketplaces without overwriting a conflicting
marketplace name; a legacy SHA-pinned declaration for the same reviewed repo
is healed to the unpinned shape. A
`false` value in either project or local settings is a tombstone and is never
re-enabled; skills and malformed plugin targets are reported as needs-user
instead of being guessed (`dummyindex/context/default_plugins.py:328-445`,
`dummyindex/context/default_plugins.py:472-554`).

`install_default_plugins` materialises only reviewed defaults that are both in
the selected `wired` ledger and effectively enabled after project/local
precedence. It probes the Claude CLI once, defers when the CLI or install-time
network path is unavailable, and records per-target failures without raising;
the declaration remains the team-shared source of intent
(`dummyindex/context/default_plugins.py:676-760`).

### Project guidance

Claude and Codex project guidance carry one shared always-on output policy:
combine the caveman and ADHD behaviors, lead with the outcome or next action,
keep prose compact, number multi-step work, suppress tangents, restate current
state, and retain technical and safety detail. Explicit user formatting and
safety requirements take precedence (`dummyindex/context/output/bootstrap.py:26-45`,
`dummyindex/context/output/agents_md.py:33-53`). The policy is project-scoped in
Codex guidance and is not copied into the user-global Codex block
(`dummyindex/context/output/agents_md.py:55-67`,
`dummyindex/context/output/agents_md.py:112-131`).

## Contracts

- `parse_install_args(args: list[str]) -> tuple[str, Path | None, bool, bool, bool, bool, str, str | None, bool]`
  returns `(scope, project_dir, skill_only, no_onboarding, defaults,
  no_default_plugins, platform, dedupe, force_downgrade)`; `platform` is
  normalized through `normalize_platform_arg()` before return, `dedupe` must be
  `user|project` when present, help exits 0, and invalid arguments — unknown
  flag, bad scope/platform/dedupe value, missing value — exit 2
  (`dummyindex/installer/args.py:72-181`).
- `normalize_platform_arg(value: str) -> str` maps the public
  `claude|agents|both` vocabulary to the internal platform token, warns once on
  the deprecated `codex` spelling, and raises `ValueError` otherwise
  (`dummyindex/installer/common.py:112-137`).
- `install(*, scope: str = "user", project_dir: Path | None = None,
  skill_only: bool = False, no_onboarding: bool = False, defaults: bool = False,
  no_default_plugins: bool = False, no_superpowers: bool = False,
  platform: str = "claude", dedupe: str | None = None,
  force_downgrade: bool = False) -> None` installs the selected host surfaces,
  runs a scoped repair pass, and performs host-aware auto-init when applicable
  (`dummyindex/installer/install.py:26-38`). An out-of-range `dedupe` exits 1
  alongside the existing scope check (`dummyindex/installer/install.py:84-89`).
  `platform` here is the **internal** vocabulary (`claude|codex|both`) only:
  `install()` hands its argument straight to `platforms_for()` without calling
  `normalize_platform_arg()`, so a direct API call with the public `agents`
  token prints `error: --platform must be claude|codex|both, got 'agents'` and
  exits 1 (`dummyindex/installer/install.py:90-94`,
  `dummyindex/installer/common.py:96-103`). `uninstall()` is asymmetric — it
  normalizes first and therefore accepts `agents`
  (`dummyindex/installer/uninstall.py:33-37`). CLI callers are unaffected
  because `parse_install_args()` normalizes before dispatch.
- `plan_repairs(*, project_root: Path, user_home: Path, target_scope: str,
  selected_platforms: tuple[str, ...], skill_only: bool = False,
  force_downgrade: bool = False, package_version: str = PACKAGE_VERSION) ->
  RepairPlan` classifies the four scanned
  copies into rewrite candidates, report-only entries, and duplicate families;
  `package_version` is the value every scanned `.dummyindex_version` stamp is
  compared against, so it decides current/stale/downgrade/unknown, and
  `skill_only` is accepted for call-site symmetry with `install()` and has no
  effect (`dummyindex/installer/repair.py:213-321`); `execute_repairs(plan) ->
  RepairExecutionResult` rewrites only the candidates, re-running the symlink
  preflight immediately before each write
  (`dummyindex/installer/repair.py:323-366`).
- `dedupe(scope: str, *, project_root: Path, user_home: Path,
  selected_platforms: tuple[str, ...] | None = None) -> DedupeResult` removes
  that scope's copy of every proven duplicate family in the selected platforms,
  reusing `_remove_skill_family()` rather than the full `uninstall()`
  orchestration (`dummyindex/installer/repair.py:369-443`).
- `_auto_init_project(project_root: Path, *, no_default_plugins: bool = False,
  no_superpowers: bool = False, platform: str = "claude",
  codex_guidance_owner: str = "project") -> bool` reports whether the primary
  build or deterministic refresh succeeded; secondary integration failures are
  warnings (`dummyindex/installer/install.py:406-534`).
- `default_wired() -> tuple[WiredEntry, ...]` adapts the reviewed defaults to the
  config ledger (`dummyindex/context/default_plugins.py:217-235`).
- `wire_default_plugins(wired: tuple[WiredEntry, ...], project_root: Path, *,
  enabled: bool = True, runner: Runner | None = None) -> PluginWireResult`
  performs declaration only and never raises for settings failures
  (`dummyindex/context/default_plugins.py:472-554`).
- `install_default_plugins(project_root: Path, *, wired: tuple[WiredEntry, ...] |
  None = None, enabled: bool = True, runner: Runner | None = None) ->
  PluginInstallResult` materialises the selected, effectively-enabled reviewed
  defaults through the runner seam (`dummyindex/context/default_plugins.py:676-760`).
- `default_config(*, platform: str = "claude") -> Config` produces the
  host-aware schema-v4 baseline
  (`dummyindex/context/domains/config.py:424-455`).
- `reconcile_default_plugins(context_dir: Path, *, platform: str) -> bool`
  upgrades applicability and appends missing defaults without overriding a
  durable opt-out (`dummyindex/context/domains/config.py:622-659`).
- `bootstrap_project_agents_md(project_root: Path, *, owner: str = "project") ->
  Path` writes the managed Codex project block at the active instruction target
  (`dummyindex/context/output/agents_md.py:112-131`).

## Examples

```bash
dummyindex install --platform claude
dummyindex install --platform both --dir ./repo --defaults
dummyindex install --platform agents --scope project --dir ./repo
dummyindex install --platform codex        # deprecated alias; warns on stderr
dummyindex install --dedupe user
dummyindex install --force-downgrade
dummyindex install --no-default-plugins
dummyindex install --no-superpowers       # compatibility alias
DUMMYINDEX_SKIP_PLUGIN_INSTALL=1 dummyindex install
dummyindex uninstall --platform both --scope project --dir ./repo
```
