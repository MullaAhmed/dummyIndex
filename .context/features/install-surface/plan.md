# Install surface — plan

confidence: INFERRED

## Bounded context

The install surface owns host skill placement and the orchestration that turns a
Git repository into a host-ready dummyindex project. It decides when to build or
refresh context, when to write host guidance, and in what order Claude
integrations are reconciled. It does not own indexing algorithms, hook semantics,
equipment rendering policy, plugin package contents, or the Claude CLI; those are
downstream services coordinated by `dummyindex/installer/install.py`
(`dummyindex/installer/install.py:26-163`,
`dummyindex/installer/install.py:337-465`).

Within that boundary, default-plugin orchestration owns five guarantees: the
one-run opt-out is side-effect-free; third-party trust is disclosed before
mutation; malformed config fails closed; user/equipment intent is reconciled
before reviewed defaults; and project declaration completes before per-machine
materialisation (`dummyindex/installer/install.py:597-665`).

## Where it lives

- `dummyindex/__main__.py` and `dummyindex/installer/args.py` are the wire layer.
  They parse and forward the canonical seven-value install tuple without owning
  policy (`dummyindex/__main__.py:270-289`,
  `dummyindex/installer/args.py:63-147`).
- `dummyindex/installer/install.py` is the application service. It places skill
  trees, chooses full build versus deterministic refresh, and sequences guidance,
  hooks, plugin reconciliation, and equipment refresh
  (`dummyindex/installer/install.py:26-163`,
  `dummyindex/installer/install.py:337-509`).
- `dummyindex/context/default_plugins.py` is the reviewed-default domain and
  adapter boundary. It defines registry/model/result types, mutates only Claude
  plugin settings, and materialises through an injected runner
  (`dummyindex/context/default_plugins.py:62-244`,
  `dummyindex/context/default_plugins.py:448-729`).
- `dummyindex/context/domains/config.py` owns persisted project intent and
  migration. It reconciles equipment and reviewed defaults into an ordered
  `wired` ledger, then writes schema-v4 config atomically
  (`dummyindex/context/domains/config.py:160-301`,
  `dummyindex/context/domains/config.py:540-682`).
- `dummyindex/installer/common.py` and `uninstall.py` are filesystem plumbing for
  skill/command placement and removal; they do not participate in plugin policy.

## Architecture in three sentences

The CLI forwards validated host, scope, and opt-out state to `install`, which
places host skills and conditionally invokes project auto-init for a Git target.
Auto-init preserves a curated index through deterministic refresh or builds a
new index, then independently coordinates guidance, hooks, default plugins, and
equipment with primary-build failure separated from best-effort integration
failure. Default plugins move through a strict pipeline—validate intent, migrate
and reconcile config, declare reviewed settings, then materialise eligible
per-machine bits—while explicit config and settings tombstones always win.

## Orchestration flow

1. `parse_install_args` collapses `--no-default-plugins` and the legacy
   `--no-superpowers` spelling into one boolean; `install` preserves the same
   compatibility collapse for direct callers
   (`dummyindex/installer/args.py:101-147`,
   `dummyindex/installer/install.py:56-60`).
2. `install` validates scope/platform and all managed-directory symlink
   boundaries before copying any selected host tree. It then installs skills and
   commands, registers user guidance, and invokes auto-init only for a Git target
   when `skill_only` is false (`dummyindex/installer/install.py:61-149`).
3. `_auto_init_project` chooses deterministic refresh for an enriched index and
   full build otherwise. Claude integrations run only when the selected platform
   contains Claude; Codex-only remains free of Claude settings and hooks
   (`dummyindex/installer/install.py:370-465`).
4. `_wire_default_plugins_step` returns immediately on the one-run opt-out. On an
   active run it discloses reviewed third-party provenance, strictly reads config,
   migrates stale schema, folds equipped plugins into `wired`, appends missing
   reviewed defaults, rereads config, and resolves durable applicability
   (`dummyindex/installer/install.py:597-653`).
5. `wire_default_plugins` declares matching marketplaces and
   `enabledPlugins=true` only for undecided plugin targets; skills, malformed
   targets, false tombstones, marketplace conflicts, and settings errors remain
   non-destructive result states (`dummyindex/context/default_plugins.py:448-530`).
6. `install_default_plugins` filters the hard-coded reviewed set by the selected
   ledger and effective settings, performs one CLI availability probe, then
   materialises each eligible target with fixed project-scoped argv. Unavailable
   CLI/network state defers; target failures accumulate without aborting later
   targets (`dummyindex/context/default_plugins.py:645-729`).

## Source-evidenced patterns

- **Application-service transaction script.** `_wire_default_plugins_step` owns
  sequence, not low-level policy: disclose → validate → migrate → recover custom
  intent → reconcile defaults → declare → materialise → render outcomes. Its
  early returns define the transaction's fail-closed boundaries
  (`dummyindex/installer/install.py:597-665`).
- **Reviewed registry as policy data.** `DEFAULT_PLUGINS` is an ordered tuple of
  frozen records validated for unique targets, non-empty reviewed surfaces, and
  immutable third-party SHAs before any install path can use it
  (`dummyindex/context/default_plugins.py:118-202`).
- **Append-only intent reconciliation.** Equipment plugins and missing reviewed
  defaults append to `Config.wired`; existing entries and order survive, and
  no-op runs do not rewrite config
  (`dummyindex/context/domains/config.py:567-659`).
- **Tombstone precedence.** Any project or local `enabledPlugins=false` is final
  for that target. A later `true` in the other file cannot resurrect it
  (`dummyindex/context/default_plugins.py:337-349`,
  `dummyindex/context/default_plugins.py:497-524`).
- **Declaration/materialisation split.** Git-travelling project settings express
  team intent; marketplace clones and plugin registrations are per-machine. The
  first pass never executes the runner, and the second pass only consumes targets
  made effectively eligible by the first
  (`dummyindex/context/default_plugins.py:448-481`,
  `dummyindex/context/default_plugins.py:533-558`,
  `dummyindex/context/default_plugins.py:645-711`).
- **Anti-corruption adapter for an external CLI.** `Runner` converts the Claude
  process into `RunResult`; `default_runner` uses list argv, no shell, a bounded
  timeout, decoded output, and returncode 127 for process failures
  (`dummyindex/context/default_plugins.py:550-581`).
- **Conflict-preserving settings merge.** A third-party marketplace is added only
  when absent or exactly equal to the reviewed GitHub repo/ref. A same-name,
  different-source declaration becomes needs-user and is never overwritten
  (`dummyindex/context/default_plugins.py:357-406`,
  `dummyindex/context/default_plugins.py:505-524`).
- **Best-effort satellite fan-out.** Guidance, hooks, plugins, and equipment are
  siblings after the primary build/refresh decision. Each reports locally; none
  calls another, and secondary failure does not convert a successful index build
  into auto-init failure (`dummyindex/installer/install.py:374-465`).

## Dependencies and state ownership

- **Upstream:** `__main__.main` is the process entry and delegates to installer
  parsing and `install` (`dummyindex/__main__.py:259-289`). Reinstall/update paths
  reuse the same idempotent `install` service rather than a separate migration
  architecture.
- **Build/guidance/hooks/equipment:** `_auto_init_project` lazily imports context
  build, Claude/Codex guidance, and hook services; equipment refresh is guarded
  by `.context/equipment.json` and calls equip only when present
  (`dummyindex/installer/install.py:357-365`,
  `dummyindex/installer/install.py:468-509`).
- **Config:** `.context/config.json` owns durable project intent. `Config.wired`
  is ordered desired equipment; `default_plugins_enabled` is the reviewed-default
  applicability state, not a duplicate per-target ledger
  (`dummyindex/context/domains/config.py:160-212`).
- **Settings:** project `.claude/settings.json` owns shared plugin and marketplace
  declarations; `.claude/settings.local.json` can add a local false tombstone.
  User-global settings are intentionally outside effective-state resolution
  (`dummyindex/context/default_plugins.py:316-349`).
- **Reviewed policy:** `default_plugins.py` owns `DefaultPlugin`, `WiredEntry`,
  target formatting, and the reviewed tuple. `config.py` imports those base
  types; `default_plugins.py` never imports config, preventing a policy/persistence
  cycle (`dummyindex/context/default_plugins.py:62-244`,
  `dummyindex/context/domains/config.py:68-75`).
- **External runtime:** the `claude` executable and `~/.claude/plugins/` own
  per-machine materialisation. The repository records intent, not installed
  package state (`dummyindex/context/default_plugins.py:533-546`,
  `dummyindex/context/default_plugins.py:613-642`).

## Data model

- `DefaultPlugin` is a frozen trust record: target identity, optional source and
  immutable ref, reviewed surfaces, and code-execution disclosure. It is release
  policy, not runtime configuration
  (`dummyindex/context/default_plugins.py:118-202`).
- `WiredEntry` is a serialisable desired-state record with `kind`, `target`, and
  descriptive `version`; `default_wired()` derives reviewed plugin entries from
  the registry so config and install share target identity
  (`dummyindex/context/default_plugins.py:62-108`,
  `dummyindex/context/default_plugins.py:226-244`).
- `Config.default_plugins_enabled` has three meanings: `true` applicable,
  `false` durable all-defaults opt-out, and `null` not applicable to a Codex-only
  baseline. Legacy schemas migrate conservatively, including recognition of the
  exact prior Codex baseline (`dummyindex/context/domains/config.py:378-455`).
- `PluginWireResult` and `PluginInstallResult` preserve stage-specific outcomes.
  Declaration reports enabled/already/needs-user/skipped/errors; materialisation
  reports installed/deferred/skipped/errors
  (`dummyindex/context/default_plugins.py:247-313`,
  `dummyindex/context/default_plugins.py:584-599`).

## Key decisions

- **Primary success means the skill tree and project index path succeeded.** Hook,
  guidance, plugin, config-default, and equipment failures are reported as
  partial integration failures. This keeps installation usable in incomplete
  host environments but means callers cannot infer full readiness from the
  command's terminal success alone
  (`dummyindex/installer/install.py:337-368`,
  `dummyindex/installer/install.py:384-465`).
- **The one-run opt-out is stronger than durable policy reconciliation.** It exits
  before trust text, config migration, settings reads/writes, or runner probes;
  `Config.false` remains the persistent policy for future runs
  (`dummyindex/installer/install.py:597-612`,
  `dummyindex/context/domains/config.py:622-659`).
- **Trust changes are source changes.** A new default or ref update must modify
  the reviewed tuple and pass structural validation; user config cannot nominate
  an arbitrary plugin for the reviewed-default materialiser
  (`dummyindex/context/default_plugins.py:149-202`,
  `dummyindex/context/default_plugins.py:670-697`).
- **User intent is monotonic during reconciliation.** Custom entries are retained,
  false applicability is retained, false settings tombstones are retained, and
  same-name marketplace conflicts are retained for user resolution. Automated
  reconciliation only fills absence
  (`dummyindex/context/domains/config.py:567-659`,
  `dummyindex/context/default_plugins.py:337-406`).
- **Malformed config is not absence.** Orchestration performs a strict read before
  tolerant migration helpers, so corrupt state warns and stops instead of
  falling back to the reviewed defaults
  (`dummyindex/installer/install.py:634-649`).
- **Codex and Claude share install entry points but not native side effects.** A
  Codex-only baseline carries no Claude plugin ledger and no plugin applicability;
  Claude and both-host baselines do. This host distinction is established in
  config and enforced by auto-init branching
  (`dummyindex/context/domains/config.py:424-455`,
  `dummyindex/installer/install.py:370-465`).
- **Curated context is never collateral damage of reinstall.** Existing enriched
  taxonomy takes deterministic refresh; a full re-cluster requires an explicit
  rebuild/ingest path (`dummyindex/installer/install.py:374-427`).

## Open questions

- Should install return a structured aggregate separating primary success from
  guidance, hook, config, plugin-declaration, plugin-materialisation, and
  equipment outcomes? The current print-based boundary makes automation parse
  prose to detect partial readiness.
- Should the reviewed registry, declaration service, and external materialiser
  split into separate modules if the default set or host count grows?
  `default_plugins.py` currently holds policy models, renderers, settings I/O,
  classification, and subprocess adaptation.
- What release gate approves a third-party default ref or reviewed-surface change?
  Structural validation proves immutability and completeness, not the quality of
  the human review.
- Should durable policy become per-default? Today it combines an all-defaults
  config switch with per-target settings tombstones, distributing policy across
  two stores.
- Should uninstall expose an explicit project-integration teardown for managed
  guidance, hooks, marketplace declarations, and enabled-plugin decisions?
  Current uninstall scope is the installed skill family.
