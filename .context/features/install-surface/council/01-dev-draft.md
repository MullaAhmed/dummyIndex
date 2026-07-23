# Install surface — plan

confidence: INFERRED

## Where it lives

The wire layer is `dummyindex/__main__.py` plus `dummyindex/installer/args.py`;
they parse and dispatch without owning install policy
(`dummyindex/__main__.py:270-289`, `dummyindex/installer/args.py:63-147`). The
installer package owns skill/command placement and project auto-init, with
`install.py` as the orchestrator and `common.py`/`uninstall.py` as filesystem
plumbing (`dummyindex/installer/__init__.py:1-28`). Core default-plugin policy is
lower in `dummyindex/context/default_plugins.py`, persisted policy is in
`dummyindex/context/domains/config.py`, and shared managed project prose is in
`dummyindex/context/output/bootstrap.py` and `agents_md.py`.

## Architecture in three sentences

The CLI parses one canonical host/scope/options tuple and calls `install`, which
copies the selected skill surfaces before deciding whether the target qualifies
for project auto-init. Auto-init chooses full build or deterministic refresh,
then fans out to host guidance, Claude hooks, config/default-plugin
reconciliation, and equipment refresh, with each secondary integration reporting
its own failure. Default-plugin core logic validates a fixed reviewed set, keeps
declaration separate from per-machine materialisation, and uses schema-v4 config
plus settings tombstones to preserve explicit user decisions.

## Data model

- `DefaultPlugin` is a frozen reviewed-source record: plugin, marketplace,
  optional GitHub repo and immutable ref, reviewed surfaces, and whether those
  surfaces execute code. `_validate_default_plugins` enforces unique targets,
  non-empty surfaces, and immutable third-party pins
  (`dummyindex/context/default_plugins.py:118-202`).
- `WiredEntry` is the persisted declaration: `kind` (`plugin` or `skill`), target,
  and optional descriptive version. `default_wired` derives these entries from
  `DEFAULT_PLUGINS`, so config targets and reviewed defaults share one target
  formatter (`dummyindex/context/default_plugins.py:62-108`,
  `dummyindex/context/default_plugins.py:226-244`).
- `Config.default_plugins_enabled: bool | None` is independent of the ordered
  `wired` tuple. `false` is the durable all-defaults opt-out, `true` makes
  reviewed defaults applicable, and `null` means they have not been applicable
  to a Codex-only baseline (`dummyindex/context/domains/config.py:160-212`).
- `PluginWireResult` and `PluginInstallResult` are frozen outcome records. They
  preserve per-target acted/already/needs-user/skipped/error or
  installed/deferred/skipped/error states instead of converting best-effort
  failures into exceptions (`dummyindex/context/default_plugins.py:247-313`,
  `dummyindex/context/default_plugins.py:584-599`).
- Project settings own two independent declarations: `enabledPlugins` and
  `extraKnownMarketplaces`. Project and local `enabledPlugins=false` values act
  as tombstones; a marketplace declaration must exactly match the reviewed
  GitHub source and ref before materialisation
  (`dummyindex/context/default_plugins.py:316-406`).

## Key decisions

- Keep the reviewed set in one ordered tuple and validate it at import time.
  Adding or changing a third-party default is a trust-boundary change, not a
  casual config edit; it requires a new immutable ref and a new surface review
  (`dummyindex/context/default_plugins.py:149-202`).
- Disclose trust before mutation. The installer renders provenance and blast
  radius before config reconciliation, settings writes, or subprocess probing
  (`dummyindex/context/default_plugins.py:205-223`,
  `dummyindex/installer/install.py:629-643`).
- Make the one-run opt-out a true early gate. It intentionally leaves config and
  settings byte-stable and emits no trust noise, while `Config.false` remains the
  separate durable opt-out (`dummyindex/installer/install.py:597-612`,
  `dummyindex/context/domains/config.py:622-659`).
- Reconcile in a fixed order: validate config, migrate schema, recover equipped
  custom plugins into `wired`, append missing reviewed defaults, reread config,
  declare targets, then materialise eligible targets. This order prevents stale
  or malformed config from silently seeding defaults and keeps custom ledger
  order intact (`dummyindex/installer/install.py:634-659`).
- Preserve any explicit settings tombstone. A `false` in either project or local
  settings wins over `true`, so reinstall and upgrade never resurrect a plugin a
  project explicitly disabled (`dummyindex/context/default_plugins.py:337-349`,
  `dummyindex/context/default_plugins.py:478-524`).
- Separate declaration from materialisation. Repository settings carry shared
  intent through Git; the Claude CLI materialises per-machine bits only after
  declaration succeeds, with one availability probe and best-effort per-target
  errors (`dummyindex/context/default_plugins.py:533-581`,
  `dummyindex/context/default_plugins.py:645-729`).
- Keep host semantics explicit. Claude and both-host baselines receive native
  plugins; Codex-only baselines remain plugin-neutral but get the same project
  output behavior through managed instructions
  (`dummyindex/context/domains/config.py:424-455`,
  `dummyindex/context/output/agents_md.py:33-65`).
- Preserve curated work on reinstall. An enriched index is deterministically
  refreshed instead of re-clustered, and equipment refresh is hash-baselined so
  user-modified generated tools remain untouched
  (`dummyindex/installer/install.py:374-427`,
  `dummyindex/installer/install.py:468-509`).

## Open questions

- What release review and user communication are mandatory when a pinned
  third-party default changes ref, surfaces, or code-execution status? The code
  enforces the pin shape, but governance remains procedural.
- Should the durable policy eventually support per-default applicability rather
  than one `default_plugins_enabled` switch plus settings tombstones? The current
  model is deliberately simple, but mixed opt-in policy lives across config and
  settings.
- Should materialisation report a consolidated partial-success status to callers?
  `_auto_init_project` returns success for a completed index build even when
  hooks, settings, or plugin installation warn, so automation must inspect
  output for secondary failures.
- Should `dummyindex uninstall` offer an explicit project-integration cleanup
  mode for managed guidance, hooks, marketplace declarations, and plugin
  decisions? Current teardown is skill-family focused.
