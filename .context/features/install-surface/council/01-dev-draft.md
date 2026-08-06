# Install surface — plan

`confidence: INFERRED`

## Where it lives

**Wire layer.** `dummyindex/__main__.py:292-321` dispatches `install` /
`uninstall`; `dummyindex/installer/args.py` owns flag parsing and the two usage
strings (`args.py:10-67`, `84-217`, `220-287`). No policy here — it validates,
normalizes `--platform` through `common.normalize_platform_arg`, and forwards.

**`dummyindex/installer/` — placement and orchestration.** Both `install.py`
and `link.py` are packages now (each grew past the repo's 600-line split
threshold); their `__init__` re-exports keep the old import paths working.

- `install/orchestrate.py:50-531` — the application service. Validates, refuses
  unsafe symlinks, plans repairs, direct-writes or defers per family, dispatches
  link mode, dedupes, registers commands and host guidance, auto-inits.
- `install/family_write.py:22-149` (`_install_skill_family`, writes the
  `.dummyindex_version` stamp last) and `:150-172`
  (`_symlinked_skill_install_directory`, the refusal predicate).
- `install/link_dispatch.py` — the four helpers `orchestrate` needs around the
  link decision: `_all_claude_families_missing:27-50`,
  `_backfill_sibling_stamps:51-125`, `_claude_narrowing_link_gate:178-216`,
  `_print_link_install_result:217-242`.
- `install/project_init.py:28-156` — `_auto_init_project`, plus the four
  satellite steps: `_refresh_equipment_step:159-200`,
  `_install_project_hooks:203-223`, `_write_default_config:226-250`,
  `_wire_default_plugins_step:288-356`.
- `link/` — `families.py` (the 8-family enumeration and temp-artifact names),
  `models.py:17-125` (`FamilyLinkState`, `LinkResult`, `LinkInstallResult`,
  `LinkCapabilityError`), `classify.py:199-336` (fail-closed classification),
  `create.py:466-587` (`create_family_links` and its rename-aside internals),
  `orchestrate.py:130-220` (`run_link_install`, the tri-state dispatcher),
  `sweep.py:31-72` (`remove_dangling_family_links`).
- `repair.py` — installed-copy discovery and repair policy: one four-root
  scanner (`scan_installed_copies:185-214`), classification
  (`plan_repairs:331-446`), execution with a re-run symlink preflight
  (`execute_repairs:447-492`), scoped deletion (`dedupe:493-604`), rendering
  (`describe_plan:605-650`).
- `common.py` — the shared vocabulary and filesystem primitives:
  `LinkMode:47-68`, `_SIBLING_SKILLS:87-97`, `platforms_for:141-149`,
  `normalize_platform_arg:157-180`, `render_skill:197-223`,
  `_install_commands:231-266`, `is_owned_copy:336-353`,
  `_remove_owned_tree_no_follow:354-380`, `_compare_stamp:398-408`.
- `uninstall.py:22-133` — removal orchestration; `_remove_skill_family:134-220`
  is the no-follow primitive shared with `repair.dedupe()`.

**`dummyindex/context/` — the wired-at-install-time surfaces.**

- `hooks.py` — the whole managed Claude hook set: five canonical bodies
  (`:120-267`), the install-order tuple (`:270-276`), the global defer-check
  wrapper (`_guard_body:379-409`), `install:486-571`, `uninstall:617-688`,
  `status:694-713`, `install_statusline:346-376`, and the legacy scrub
  (`_scrub_legacy_claude_hooks:574-611`).
- `default_plugins.py` — the reviewed registry (`:165-193`), disclosure
  (`:196-215`), declaration (`wire_default_plugins:472-572`), and
  materialisation through an injected runner
  (`install_default_plugins:676-761`, `default_runner:589-606`).
- `domains/config.py` — durable project intent: `default_config:424-479`,
  `migrate_config_in_place:540-566`,
  `reconcile_wired_with_equipment:567-621`,
  `reconcile_default_plugins:622-661`.
- `output/bootstrap.py:33-101` — the policy text the guidance block and the
  UserPromptSubmit hook both carry (`ALWAYS_ON_TURN_REMINDER:78-92`).
- `domains/equip/lifecycle/status.py:221-313` — the hash-baselined equipment
  refresh the install triggers.

**Tests.** `tests/test_install.py`, `tests/test_install_link.py`,
`tests/test_install_link_primitives.py`, `tests/test_install_repair.py`,
`tests/context/test_hooks.py`, `tests/context/test_default_plugins.py`,
`tests/context/domains/equip/test_equip_lifecycle_plugins.py`, and the legacy
fixture `tests/fixtures/legacy_skill_md/SKILL.md`.

## Architecture in three sentences

`__main__` → `args` → `install/orchestrate.install()` is a transaction script:
it validates, then runs a fixed sequence of steps against the filesystem,
printing one aligned line per step and never returning structured state. Every
step below it is a best-effort satellite that reports locally and calls no
sibling — hooks, default plugins, equipment, and guidance are all reached from
`project_init.py` and none of their failures can turn a successful `.context/`
build into an install failure. The dominant pattern is *evidence before
mutation*: a `.dummyindex_version` stamp before any rewrite or delete, a closed
`FamilyLinkState` classification before any symlink replacement, a sentinel
substring before touching a hook entry, and a `false` in settings as a
permanent tombstone.

## Data model

No database. The persistent state this feature owns is four kinds of files:

- **Installed-copy stamps.** `.dummyindex_version` written last by
  `_install_skill_family` (`install/family_write.py:22-149`). It — not the
  directory's existence — is what `repair.py` acts on; `InstalledCopy` carries
  `scope`, `host`, family `path`, and the raw stamp or `None`
  (`repair.py:70-87`), and `RepairPlan` keeps `to_rewrite` separate from
  `to_report` and `duplicates` (`repair.py:123-138`) so "what will be written"
  is a distinct field from "what the user must resolve".
- **`.claude/settings.json`.** Hook entries under five event keys, each
  recognized by `SENTINEL in command` (`hooks.py:64-73`); `enabledPlugins`
  target booleans; marketplace declarations; and the `statusLine` scalar (the
  one un-sentinelled value this feature writes, hence write-if-absent-only).
  `.claude/settings.local.json` can add a local `false` tombstone.
- **`.context/config.json`.** Schema v4. `Config.wired` is the ordered desired
  set of `WiredEntry(kind, target, version)` records
  (`default_plugins.py:64-110`); `default_plugins_enabled` is tri-valued —
  `true` applicable, `false` durable all-defaults opt-out, `null` not
  applicable to a Codex-only baseline (`config.py:424-479`). Reconciliation is
  append-only: equipment entries fold in first
  (`reconcile_wired_with_equipment:567-621`), missing reviewed defaults append
  after (`reconcile_default_plugins:622-661`), existing entries and their order
  survive, and a no-op run does not rewrite the file.
- **`.context/equipment.json`.** Read-only to this feature: its presence gates
  the refresh, and the refresh re-baselines hashes for PRISTINE items only.

In-memory result types are all frozen dataclasses returned rather than raised:
`HookResult(installed, skipped, removed, errors, refreshed, nudges)`
(`hooks.py:447-466`), `HookStatus` (five booleans, `hooks.py:428-444`),
`PluginWireResult` / `PluginInstallResult`
(`default_plugins.py:238-270`, `608-624`), `LinkResult` / `LinkInstallResult`
(`link/models.py:59-125`), `RepairPlan` / `RepairExecutionResult` /
`DedupeResult` (`repair.py:123-184`).

## Key decisions

- **Five events, ten commands, one entry per event.** Each managed hook event
  holds exactly one sentinel-bearing entry whose `hooks` array may hold several
  commands (`hooks.py:270-276`). That shape is what lets `install_hook_entry`
  preserve a user's co-located hook inside the managed entry, and it is why
  "refreshed vs skipped" is decided by a byte-level before/after of
  `settings.json` rather than by comparing to the canonical body — the naive
  comparison would report `refreshed` forever once a user adds their own command
  beside ours (`hooks.py:532-551`).
- **The static per-turn reminder is deliberately un-gated.** The first
  UserPromptSubmit command is a `printf` of pre-built JSON with no
  `command -v dummyindex` check (`hooks.py:120-131`), because it must still fire
  on an alternate Claude profile that can read project settings but has no CLI
  on PATH. That is the one command `_guard_body` cannot patch through a gate, so
  the global-scope wrapper inserts a silent gate *plus* the defer-check guard
  after the managed comment instead (`hooks.py:379-409`).
- **Feedback is split across two events by blast radius.** Mining is
  SessionStart-only, fully silenced with `>/dev/null 2>&1`, and writes only the
  bounded gitignored cache (`hooks.py:185-196`); reading it is per-prompt and
  keeps stdout because that is the channel its JSON travels on
  (`hooks.py:132-143`). Both `memory` verbs swallow every exception and return 0
  (`cli/memory.py:87-128`) — generated feedback must never block a turn. Stop
  was deliberately left at its two commands; the test asserts that
  (`tests/context/test_hooks.py:1108-1117`).
- **The freshness badge is an ability, not an opt-in.** `install_statusline`
  writes only when neither scope defines a truthy `statusLine`, and refuses
  (returning a hand-edit nudge) rather than clobber an unparseable file
  (`hooks.py:310-376`). Idempotence without a sentinel is bought entirely by
  never-clobber.
- **Preserve-or-refuse on every settings file.** A `MalformedSettingsError` is
  reported in `errors` and the file is left byte-identical — in install
  (`hooks.py:550-551`), in the legacy scrub (`hooks.py:581-584`), and in
  uninstall (`hooks.py:646-650`). The same discipline governs config: the
  orchestration does a *strict* `read_config` before the tolerant migration
  helpers, so corrupt state warns and stops rather than seeding defaults
  (`project_init.py:326-340`).
- **The one-run opt-out outranks durable policy.** `--no-default-plugins`
  returns before trust disclosure, config migration, settings I/O, or the runner
  probe (`project_init.py:300-303`); `config.default_plugins_enabled=false` is
  the persistent form and survives reconciliation.
- **Declaration is separated from materialisation.** Project `settings.json`
  travels in git and expresses team intent; marketplace clones and plugin
  registration are per-machine. The first pass never executes the runner
  (`default_plugins.py:472-572`), the second only consumes targets the first made
  effectively eligible (`default_plugins.py:676-761`), and an absent `claude`
  CLI defers rather than fails.
- **No commit pin for third-party defaults — rejected because it cannot work.**
  Claude Code materialises marketplaces with `git clone --branch <ref>`, which
  accepts a branch or tag but never a SHA; dummyindex ≤ 0.33.x pinned SHAs and
  every third-party default silently failed to materialise. The `ref` field and
  its validation are gone; `_is_legacy_sha_pin` (`default_plugins.py:353-370`)
  exists solely to *heal* the old shape instead of reporting it as a conflict.
- **Trust changes are source changes.** `DEFAULT_PLUGINS` is validated at import
  for unique targets and non-empty reviewed surfaces
  (`default_plugins.py:148-193`); user config cannot nominate an arbitrary
  plugin for the reviewed-default materialiser.
- **Repair is scoped to the invocation and only writes the targeted scope.**
  Stale copies at other roots and user+project duplicates are report-only with a
  remediation command; downgrade and unparseable stamps stay report-only unless
  `--force-downgrade`; deletion happens only under an explicit `--dedupe`,
  filtered to the same platform set (`repair.py:331-446`, `493-604`,
  `651-711`).
- **Link direction is fixed `.claude → .agents`, and the family list is
  enumerated, never globbed.** `.agents` is the portable rendering; Claude Code
  is the only host that reads solely `.claude`. The 8 families come from
  `_SIBLING_SKILLS` because a `dummyindex*` glob would also match the
  equip-generated `dummyindex-verify` skill (`link/families.py:16-24`).
- **Link-mode sequencing is pinned.** `plan_repairs` → direct-write →
  `execute_repairs` → sibling-stamp backfill → `run_link_install`, so links are
  never created against a stale or partially written `.agents` tree
  (`install/orchestrate.py:253-442`). The blank-slate Claude write is *deferred*
  and landed only if linking never happened, enforcing "exactly one of
  {8 links, 8 real dirs}, never a mix, never neither"
  (`orchestrate.py:384-441`).
- **Symlink allowlists are passed in, never derived from `$HOME`.** One
  `claude_link_allowlist` per run — `frozenset()` at project scope, the two
  `.claude` roots at user scope — is threaded through the preflight, the
  direct-write loop, the link dispatch, and `_install_commands`
  (`orchestrate.py:153-164`).
- **Curated context is never collateral damage of a reinstall.** An enriched
  `.context/` takes the deterministic-refresh path; a re-cluster requires an
  explicit `rebuild --full` or `ingest` (`project_init.py:65-118`).
- **Primary success is the skill tree plus the index path.** Guidance, hook,
  plugin, config, and equipment failures print and continue
  (`project_init.py:203-223` returns `True` even when the hook install raised).
  The cost is real: a caller cannot infer full readiness from the process exit
  code alone.

## Open questions

- Should `install` return a structured aggregate instead of printing? Today the
  only machine-readable signal is the exit code, and partial readiness (hooks
  installed but plugins deferred, say) is discoverable only by parsing prose.
- Is `HookResult.nudges` general or single-purpose? It exists for exactly one
  advisory (`_STATUSLINE_UNWRITABLE_NUDGE`) and has no rendering contract of its
  own beyond the caller printing it.
- Should the reviewed registry, the declaration service, and the subprocess
  adapter be separate modules? `default_plugins.py` is 783 lines holding policy
  data, settings I/O, classification, rendering, and process adaptation — near
  the repo's split threshold.
- What release gate approves a third-party default or a reviewed-surface change?
  The structural validation proves unique targets and non-empty surfaces; it
  cannot prove the quality of the human review, and with no pin it says nothing
  about the bytes the upstream branch will serve at clone time.
- Should durable plugin policy be per-default rather than an all-defaults
  config switch plus per-target settings tombstones? Policy currently lives in
  two stores with different lifetimes.
- Should `uninstall` offer an explicit project-integration teardown (managed
  guidance, hooks, marketplace declarations, plugin decisions)? Today it removes
  the skill family and slash commands only; `hooks.uninstall` exists but is not
  reached from the `dummyindex uninstall` path.
- Line-range citations in this document are anchored to the current HEAD; the
  hook bodies in `hooks.py:110-276` have moved twice in the last two commits, so
  treat any range that does not land on the named symbol as drift and re-derive
  it from the code.
