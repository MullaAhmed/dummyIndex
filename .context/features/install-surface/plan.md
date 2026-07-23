# Install surface — plan

confidence: INFERRED

## Bounded context

The install surface owns host skill placement and the orchestration that turns a
Git repository into a host-ready dummyindex project. It decides when to build or
refresh context, when to write host guidance, and in what order Claude
integrations are reconciled. It does not own indexing algorithms, hook semantics,
equipment rendering policy, plugin package contents, or the Claude CLI; those are
downstream services coordinated by `dummyindex/installer/install.py`
(`dummyindex/installer/install.py:26-231`,
`dummyindex/installer/install.py:406-534`).

Within that boundary, default-plugin orchestration owns five guarantees: the
one-run opt-out is side-effect-free; third-party trust is disclosed before
mutation; malformed config fails closed; user/equipment intent is reconciled
before reviewed defaults; and project declaration completes before per-machine
materialisation (`dummyindex/installer/install.py:666-734`).

## Where it lives

- `dummyindex/__main__.py` and `dummyindex/installer/args.py` are the wire layer.
  They parse and forward the canonical nine-value install tuple — now including
  `dedupe` and `force_downgrade` — without owning policy, delegating the
  public→internal platform vocabulary mapping to `common.normalize_platform_arg()`
  (`dummyindex/__main__.py:289-312`, `dummyindex/installer/args.py:72-181`).
- `dummyindex/installer/install.py` is the application service. It places skill
  trees, chooses full build versus deterministic refresh, and sequences guidance,
  hooks, plugin reconciliation, and equipment refresh
  (`dummyindex/installer/install.py:26-231`,
  `dummyindex/installer/install.py:406-578`).
- `dummyindex/installer/repair.py` owns installed-copy discovery and repair
  policy: the single four-root `.dummyindex_version` scanner
  (`scan_installed_copies`, lifted out of `cli/check.py`), ownership-evidence and
  staleness gating, downgrade/unknown as report-only unless `--force-downgrade`,
  the symlink preflight plus its execute-time re-check, per-copy error isolation,
  and scoped dedupe (`dummyindex/installer/repair.py:175-203`,
  `dummyindex/installer/repair.py:213-321`,
  `dummyindex/installer/repair.py:323-366`,
  `dummyindex/installer/repair.py:369-443`,
  `dummyindex/installer/repair.py:490-505`).
- `dummyindex/context/default_plugins.py` is the reviewed-default domain and
  adapter boundary. It defines registry/model/result types, mutates only Claude
  plugin settings, and materialises through an injected runner
  (`dummyindex/context/default_plugins.py:64-235`,
  `dummyindex/context/default_plugins.py:472-760`).
- `dummyindex/context/domains/config.py` owns persisted project intent and
  migration. It reconciles equipment and reviewed defaults into an ordered
  `wired` ledger, then writes schema-v4 config atomically
  (`dummyindex/context/domains/config.py:160-301`,
  `dummyindex/context/domains/config.py:540-682`).
- `dummyindex/installer/common.py` and `uninstall.py` are filesystem plumbing for
  skill/command placement and removal; they do not participate in plugin policy.
  `common.py` additionally owns the public platform vocabulary boundary
  (`normalize_platform_arg`, `dummyindex/installer/common.py:112-137`) and the
  host-neutral `_PORTABLE_HOST_PREAMBLE` that `render_skill` prepends to the
  `.agents/skills` copy (`dummyindex/installer/common.py:66-93`,
  `dummyindex/installer/common.py:152-171`). `uninstall.py`'s no-follow removal
  was extracted into `_remove_skill_family()`
  (`dummyindex/installer/uninstall.py:82-166`) so it is shared with
  `repair.dedupe()`; dedupe reuses only that helper, never the full `uninstall()`
  orchestration, so slash commands and managed guidance blocks are untouched by a
  dedupe run.

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
   (`dummyindex/installer/args.py:121-181`,
   `dummyindex/installer/install.py:58-77`).
2. `install` validates scope/dedupe/platform and all managed-directory symlink
   boundaries before copying any selected host tree. It then plans repairs,
   installs skills and commands, registers user guidance, and invokes auto-init
   only for a Git target when `skill_only` is false
   (`dummyindex/installer/install.py:78-218`).
3. Repair runs on every invocation, scoped to the selected platforms and target
   scope: `plan_repairs` classifies the four scanned copies, `_install_skill_family`
   is called directly only for an absent or unprovable family dir, and
   `execute_repairs` owns every provable one so no copy is written twice.
   `--dedupe user|project` then removes that scope's copy of a proven duplicate
   family (`dummyindex/installer/install.py:147-187`,
   `dummyindex/installer/repair.py:213-321`,
   `dummyindex/installer/repair.py:369-443`).
4. `_auto_init_project` chooses deterministic refresh for an enriched index and
   full build otherwise. Claude integrations run only when the selected platform
   contains Claude; Codex-only remains free of Claude settings and hooks
   (`dummyindex/installer/install.py:439-534`).
5. `_wire_default_plugins_step` returns immediately on the one-run opt-out. On an
   active run it discloses reviewed third-party provenance, strictly reads config,
   migrates stale schema, folds equipped plugins into `wired`, appends missing
   reviewed defaults, rereads config, and resolves durable applicability
   (`dummyindex/installer/install.py:666-722`).
6. `wire_default_plugins` declares matching marketplaces and
   `enabledPlugins=true` only for undecided plugin targets; skills, malformed
   targets, false tombstones, marketplace conflicts, and settings errors remain
   non-destructive result states (`dummyindex/context/default_plugins.py:472-554`).
7. `install_default_plugins` filters the hard-coded reviewed set by the selected
   ledger and effective settings, performs one CLI availability probe, then
   materialises each eligible target with fixed project-scoped argv. Unavailable
   CLI/network state defers; target failures accumulate without aborting later
   targets (`dummyindex/context/default_plugins.py:676-760`).

## Source-evidenced patterns

- **Application-service transaction script.** `_wire_default_plugins_step` owns
  sequence, not low-level policy: disclose → validate → migrate → recover custom
  intent → reconcile defaults → declare → materialise → render outcomes. Its
  early returns define the transaction's fail-closed boundaries
  (`dummyindex/installer/install.py:666-734`).
- **Reviewed registry as policy data.** `DEFAULT_PLUGINS` is an ordered tuple of
  frozen records validated for unique targets and non-empty reviewed surfaces
  before any install path can use it
  (`dummyindex/context/default_plugins.py:148-194`). The SHA-pin validation was
  removed along with the `ref` field: Claude Code materialises marketplaces with
  `git clone --branch <ref>`, which can never clone a commit SHA, so third-party
  defaults now track their upstream's latest default branch and there is
  deliberately no pin to validate.
- **Append-only intent reconciliation.** Equipment plugins and missing reviewed
  defaults append to `Config.wired`; existing entries and order survive, and
  no-op runs do not rewrite config
  (`dummyindex/context/domains/config.py:567-659`).
- **Tombstone precedence.** Any project or local `enabledPlugins=false` is final
  for that target. A later `true` in the other file cannot resurrect it
  (`dummyindex/context/default_plugins.py:328-340`,
  `dummyindex/context/default_plugins.py:521-548`).
- **Declaration/materialisation split.** Git-travelling project settings express
  team intent; marketplace clones and plugin registrations are per-machine. The
  first pass never executes the runner, and the second pass only consumes targets
  made effectively eligible by the first
  (`dummyindex/context/default_plugins.py:472-505`,
  `dummyindex/context/default_plugins.py:557-582`,
  `dummyindex/context/default_plugins.py:676-742`).
- **Anti-corruption adapter for an external CLI.** `Runner` converts the Claude
  process into `RunResult`; `default_runner` uses list argv, no shell, a bounded
  timeout, decoded output, and returncode 127 for process failures
  (`dummyindex/context/default_plugins.py:574-605`).
- **Conflict-preserving settings merge.** A third-party marketplace is added only
  when absent, exactly equal to the canonical unpinned shape
  `{"source": "github", "repo": <slug>}` (`_expected_source`,
  `dummyindex/context/default_plugins.py:348-351`), or exactly a dummyindex
  <= 0.33.x commit-SHA pin of the same reviewed repo (`_is_legacy_sha_pin`,
  `dummyindex/context/default_plugins.py:353-370`) — that one legacy shape is
  healed to the unpinned shape rather than treated as a conflict, because the
  stale pin can never clone. A deliberate branch/tag ref, another repo, a
  non-github shape, or any extra key is a conflict: needs-user and never
  overwritten (`dummyindex/context/default_plugins.py:373-410`).
- **Best-effort satellite fan-out.** Guidance, hooks, plugins, and equipment are
  siblings after the primary build/refresh decision. Each reports locally; none
  calls another, and secondary failure does not convert a successful index build
  into auto-init failure (`dummyindex/installer/install.py:443-534`).
- **Ownership evidence before any rewrite or removal.** Repair never treats a
  bare directory-name match as proof. A copy is actionable only when it carries a
  `.dummyindex_version` stamp or the legacy `## Codex host compatibility`
  heading, and the same predicate gates `install()`'s direct-write branch,
  rewrite selection, and duplicate detection
  (`dummyindex/installer/repair.py:481-505`,
  `dummyindex/installer/repair.py:538-597`,
  `dummyindex/installer/repair.py:620-648`).

## Dependencies and state ownership

- **Upstream:** `__main__.main` is the process entry and delegates to installer
  parsing and `install` (`dummyindex/__main__.py:278-312`). Reinstall/update paths
  reuse the same idempotent `install` service rather than a separate migration
  architecture.
- **Build/guidance/hooks/equipment:** `_auto_init_project` lazily imports context
  build, Claude/Codex guidance, and hook services; equipment refresh is guarded
  by `.context/equipment.json` and calls equip only when present
  (`dummyindex/installer/install.py:426-434`,
  `dummyindex/installer/install.py:537-578`).
- **Config:** `.context/config.json` owns durable project intent. `Config.wired`
  is ordered desired equipment; `default_plugins_enabled` is the reviewed-default
  applicability state, not a duplicate per-target ledger
  (`dummyindex/context/domains/config.py:160-212`).
- **Settings:** project `.claude/settings.json` owns shared plugin and marketplace
  declarations; `.claude/settings.local.json` can add a local false tombstone.
  User-global settings are intentionally outside effective-state resolution
  (`dummyindex/context/default_plugins.py:307-340`).
- **Installed copies:** the four canonical roots (project/user × claude/codex)
  own placement state, recorded by the `.dummyindex_version` stamp that
  `_install_skill_family` writes last. `repair.py` is the only reader of all four
  at once, and the stamp — not the directory's existence — is what a rewrite,
  duplicate report, or dedupe acts on
  (`dummyindex/installer/repair.py:175-203`,
  `dummyindex/installer/repair.py:647-648`).
- **Reviewed policy:** `default_plugins.py` owns `DefaultPlugin`, `WiredEntry`,
  target formatting, and the reviewed tuple. `config.py` imports those base
  types; `default_plugins.py` never imports config, preventing a policy/persistence
  cycle (`dummyindex/context/default_plugins.py:64-235`,
  `dummyindex/context/domains/config.py:68-75`).
- **External runtime:** the `claude` executable and `~/.claude/plugins/` own
  per-machine materialisation. The repository records intent, not installed
  package state (`dummyindex/context/default_plugins.py:557-570`,
  `dummyindex/context/default_plugins.py:637-666`).

## Data model

- `DefaultPlugin` is a frozen trust record: target identity, optional source
  repo, reviewed surfaces, and code-execution disclosure
  (`dummyindex/context/default_plugins.py:121-146`). The `ref` field and its
  `__post_init__` "a default plugin ref requires a marketplace repo" check no
  longer exist — third-party records track the upstream's latest default branch.
  It is release policy, not runtime configuration.
- `WiredEntry` is a serialisable desired-state record with `kind`, `target`, and
  descriptive `version`; `default_wired()` derives reviewed plugin entries from
  the registry so config and install share target identity
  (`dummyindex/context/default_plugins.py:64-110`,
  `dummyindex/context/default_plugins.py:217-235`).
- `Config.default_plugins_enabled` has three meanings: `true` applicable,
  `false` durable all-defaults opt-out, and `null` not applicable to a Codex-only
  baseline. Legacy schemas migrate conservatively, including recognition of the
  exact prior Codex baseline (`dummyindex/context/domains/config.py:378-455`).
- `PluginWireResult` and `PluginInstallResult` preserve stage-specific outcomes.
  Declaration reports enabled/already/needs-user/skipped/errors; materialisation
  reports installed/deferred/skipped/errors
  (`dummyindex/context/default_plugins.py:238-304`,
  `dummyindex/context/default_plugins.py:608-623`).
- `InstalledCopy` is the repair domain's unit: `scope`, `host`, family `path`,
  and the raw `.dummyindex_version` stamp or `None`. `RepairPlan` separates
  `to_rewrite` from `to_report` and `duplicates`, so "what will be written" is a
  distinct field from "what the user must resolve"
  (`dummyindex/installer/repair.py:68-127`).

## Key decisions

- **Primary success means the skill tree and project index path succeeded.** Hook,
  guidance, plugin, config-default, and equipment failures are reported as
  partial integration failures. This keeps installation usable in incomplete
  host environments but means callers cannot infer full readiness from the
  command's terminal success alone
  (`dummyindex/installer/install.py:406-437`,
  `dummyindex/installer/install.py:453-534`).
- **The one-run opt-out is stronger than durable policy reconciliation.** It exits
  before trust text, config migration, settings reads/writes, or runner probes;
  `Config.false` remains the persistent policy for future runs
  (`dummyindex/installer/install.py:666-681`,
  `dummyindex/context/domains/config.py:622-659`).
- **Trust changes are source changes.** A new default, a repo change, or a
  reviewed-surface change must modify the reviewed tuple and pass structural
  validation — unique targets, non-empty surfaces; user config cannot nominate an
  arbitrary plugin for the reviewed-default materialiser. There is no longer any
  "ref update" to review: the `ref` field was removed
  (`dummyindex/context/default_plugins.py:121-163`,
  `dummyindex/context/default_plugins.py:701-728`).
- **Repair is scoped to the invocation, and only the targeted scope is written.**
  A stale proven copy at this run's own scope root is rewritten; every other
  detected root and every user+project duplicate is report-only with a
  remediation command, and a downgrade or unparseable stamp stays report-only
  unless `--force-downgrade`. Deletion happens only under an explicit
  `--dedupe user|project` and is filtered to the same platform set
  (`dummyindex/installer/repair.py:213-321`,
  `dummyindex/installer/repair.py:369-443`,
  `dummyindex/installer/repair.py:538-597`).
- **User intent is monotonic during reconciliation.** Custom entries are retained,
  false applicability is retained, false settings tombstones are retained, and
  same-name marketplace conflicts are retained for user resolution. Automated
  reconciliation only fills absence
  (`dummyindex/context/domains/config.py:567-659`,
  `dummyindex/context/default_plugins.py:373-410`).
- **Malformed config is not absence.** Orchestration performs a strict read before
  tolerant migration helpers, so corrupt state warns and stops instead of
  falling back to the reviewed defaults
  (`dummyindex/installer/install.py:703-718`).
- **Codex and Claude share install entry points but not native side effects.** A
  Codex-only baseline carries no Claude plugin ledger and no plugin applicability;
  Claude and both-host baselines do. This host distinction is established in
  config and enforced by auto-init branching
  (`dummyindex/context/domains/config.py:424-455`,
  `dummyindex/installer/install.py:439-534`).
- **Curated context is never collateral damage of reinstall.** Existing enriched
  taxonomy takes deterministic refresh; a full re-cluster requires an explicit
  rebuild/ingest path (`dummyindex/installer/install.py:443-496`).

## Open questions

- Should install return a structured aggregate separating primary success from
  guidance, hook, config, plugin-declaration, plugin-materialisation, and
  equipment outcomes? The current print-based boundary makes automation parse
  prose to detect partial readiness.
- Should the reviewed registry, declaration service, and external materialiser
  split into separate modules if the default set or host count grows?
  `default_plugins.py` currently holds policy models, renderers, settings I/O,
  classification, and subprocess adaptation.
- What release gate approves a third-party default repo or reviewed-surface
  change? Structural validation proves unique targets and completeness, not the
  quality of the human review — and with the `ref` pin gone it cannot prove
  anything about the bytes the upstream branch will serve at clone time.
- Should durable policy become per-default? Today it combines an all-defaults
  config switch with per-target settings tombstones, distributing policy across
  two stores.
- Should uninstall expose an explicit project-integration teardown for managed
  guidance, hooks, marketplace declarations, and enabled-plugin decisions?
  Current uninstall scope is the installed skill family, and `repair.dedupe()`
  now reuses that same family-only primitive.
