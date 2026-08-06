# Install surface — plan

`confidence: INFERRED`

> Citation law for this doc: **full paths, always.** Four filenames are
> ambiguous inside this feature — `orchestrate.py` (`installer/install/` vs
> `installer/link/`), `models.py`/`classify.py` (`installer/link/` vs
> `context/domains/*/`), `hooks.py` (`context/` vs `cli/`), `config.py`
> (`context/domains/` vs `cli/`). Bare-name citations silently resolve to the
> wrong file.

## Where it lives

**Bounded context.** This feature owns *placement and wiring*: where the skill
tree lands, which host trees are real vs linked, and which project surfaces get
declared at install time. It does **not** own what it wires — index building,
hook *behavior*, equipment rendering, plugin *contents*, and the `claude` CLI
are all downstream services reached through narrow seams.

**Wire layer.** `dummyindex/__main__.py:292-321` dispatches `install` /
`uninstall`. `dummyindex/installer/args.py` owns flag parsing and the two usage
strings (`args.py:10-67`, `84-217`, `220-287`). No policy — it validates,
normalizes `--platform` via `common.normalize_platform_arg`, and forwards.

**`dummyindex/installer/` — placement and orchestration.** Both `install` and
`link` are packages now (each grew past the repo's 600-line split threshold);
their `__init__` re-exports preserve the old import paths.

- `installer/install/orchestrate.py:50-531` — the application service. Validates,
  refuses unsafe symlinks, plans repairs, direct-writes or defers per family,
  dispatches link mode, dedupes, registers commands and host guidance, auto-inits.
- `installer/install/family_write.py:22-149` (`_install_skill_family`, writes the
  `.dummyindex_version` stamp last) and `:150-172`
  (`_symlinked_skill_install_directory`, the refusal predicate).
- `installer/install/link_dispatch.py` — the four helpers `orchestrate` needs
  around the link decision: `_all_claude_families_missing:27-50`,
  `_backfill_sibling_stamps:51-125`, `_claude_narrowing_link_gate:178-216`,
  `_print_link_install_result:217-242`.
- `installer/install/project_init.py:28-156` — `_auto_init_project`, plus the four
  satellite steps: `_refresh_equipment_step:159-200`,
  `_install_project_hooks:203-223`, `_write_default_config:226-250`,
  `_wire_default_plugins_step:288-356`.
- `installer/link/` — strictly layered, no back-edges (see *Dependencies*):
  `families.py:16-24` (family enumeration + temp-artifact names),
  `models.py:17-125` (`FamilyLinkState`, `LinkResult`, `LinkInstallResult`,
  `LinkCapabilityError`), `classify.py:199-336` (fail-closed classification),
  `create.py:466-587` (`create_family_links` and its rename-aside internals),
  `orchestrate.py:130-220` (`run_link_install`, the tri-state dispatcher),
  `sweep.py:31-72` (`remove_dangling_family_links`).
- `installer/repair.py` — installed-copy discovery and repair policy: one
  four-root scanner (`scan_installed_copies:185-214`), classification
  (`plan_repairs:331-446`), execution with a re-run symlink preflight
  (`execute_repairs:447-492`), scoped deletion (`dedupe:493-604`), rendering
  (`describe_plan:605-650`).
- `installer/common.py` — shared vocabulary and filesystem primitives:
  `LinkMode:47-68`, `_SIBLING_SKILLS:87-95`, `platforms_for:141-149`,
  `normalize_platform_arg:157-180`, `render_skill:197-223`,
  `_install_commands:231-266`, `is_owned_copy:336-353`,
  `_remove_owned_tree_no_follow:354-380`, `_compare_stamp:398-408`.
- `installer/uninstall.py:22-133` — removal orchestration;
  `_remove_skill_family:134-220` is the no-follow primitive shared with
  `repair.dedupe()`.

**`dummyindex/context/` — the wired-at-install-time surfaces (downstream).**

- `context/hooks.py` — the managed Claude hook set: five canonical bodies
  (`:120-267`), the install-order tuple (`_CLAUDE_HOOKS:270-276`), the global
  defer-check wrapper (`_guard_body:379-409`), `install:486-571`,
  `uninstall:617-688`, `status:694-713`, `install_statusline:346-376`, and the
  legacy scrub (`_scrub_legacy_claude_hooks:574-611`).
- `context/default_plugins.py` — the reviewed registry (`:165-193`), disclosure
  (`:196-215`), declaration (`wire_default_plugins:472-572`), and
  materialisation through an injected runner
  (`install_default_plugins:676-761`, `default_runner:589-606`).
- `context/domains/config.py` — durable project intent: `default_config:424-479`,
  `migrate_config_in_place:540-566`, `reconcile_wired_with_equipment:567-621`,
  `reconcile_default_plugins:622-661`.
- `context/output/bootstrap.py:33-101` — the policy text the guidance block and
  the UserPromptSubmit hook both carry (`ALWAYS_ON_TURN_REMINDER:78-92`).
- `context/domains/equip/lifecycle/status.py:221-313` — the hash-baselined
  equipment refresh the install triggers.

**Tests.** `tests/test_install.py`, `tests/test_install_link.py`,
`tests/test_install_link_primitives.py`, `tests/test_install_repair.py`,
`tests/context/test_hooks.py`, `tests/context/test_default_plugins.py`,
`tests/context/domains/equip/test_equip_lifecycle_plugins.py`, and the legacy
fixture `tests/fixtures/legacy_skill_md/SKILL.md`.

## Architecture in three sentences

`__main__` → `args` → `installer/install/orchestrate.install()` is a
**transaction script**: it validates, then runs a fixed sequence of steps
against the filesystem, printing one aligned line per step and never returning
structured state. Every step below it is a **best-effort satellite** that
reports locally and calls no sibling — hooks, default plugins, equipment, and
guidance are all reached from `project_init.py` and none of their failures can
turn a successful `.context/` build into an install failure. The dominant
pattern is **evidence before mutation**: a `.dummyindex_version` stamp before
any rewrite or delete, a closed `FamilyLinkState` classification before any
symlink replacement, a sentinel substring before touching a hook entry, and a
`false` in settings as a permanent tombstone.

**Patterns in play, each with its seam:**

| Pattern | Where |
|---|---|
| Transaction script (application service) | `installer/install/orchestrate.py:50-531` |
| Best-effort satellite fan-out | `installer/install/project_init.py:110-117`, `148-155` |
| Evidence before mutation (stamp-last) | `installer/install/family_write.py:22-149` |
| Fail-closed classification (closed enum) | `installer/link/classify.py:199-336`, `installer/link/models.py:17-49` |
| Deferred-write / exactly-one-of invariant | `installer/install/orchestrate.py:326-330`, `384-441` |
| Sentinel-keyed merge (preserve foreign entries) | `context/hooks.py:64-73`, `532-551` |
| Write-if-absent (idempotence without a sentinel) | `context/hooks.py:306-376` |
| Declaration / materialisation split | `context/default_plugins.py:472-572` vs `676-761` |
| Anti-corruption adapter (injected `Runner`) | `context/default_plugins.py:589-606` |
| Append-only intent reconciliation | `context/domains/config.py:567-621`, `622-661` |
| Package-attribute indirection as test seam | `installer/install/orchestrate.py:5-13`, `:21` |
| Deferred import to break a cycle | `installer/install/orchestrate.py:251`, `:445` |

## Data model

No database. The persistent state this feature owns is four kinds of files.

- **Installed-copy stamps.** `.dummyindex_version`, written last by
  `_install_skill_family` (`installer/install/family_write.py:22-149`). It — not
  the directory's existence — is what `repair.py` acts on; `InstalledCopy`
  carries `scope`, `host`, family `path`, and the raw stamp or `None`
  (`installer/repair.py:70-87`), and `RepairPlan` keeps `to_rewrite` separate
  from `to_report` and `duplicates` (`installer/repair.py:123-138`) so "what will
  be written" is a distinct field from "what the user must resolve".
- **`.claude/settings.json`.** Hook entries under five event keys, each
  recognized by `SENTINEL in command` (`context/hooks.py:64-73`);
  `enabledPlugins` target booleans; marketplace declarations; and the
  `statusLine` scalar (the one un-sentinelled value this feature writes, hence
  write-if-absent-only). `.claude/settings.local.json` can add a local `false`
  tombstone.
- **`.context/config.json`.** Schema v4. `Config.wired` is the ordered desired
  set of `WiredEntry(kind, target, version)` records
  (`context/default_plugins.py:64-110`); `default_plugins_enabled` is tri-valued
  — `true` applicable, `false` durable all-defaults opt-out, `null` not
  applicable to a Codex-only baseline (`context/domains/config.py:424-479`).
  Reconciliation is append-only: equipment entries fold in first
  (`:567-621`), missing reviewed defaults append after (`:622-661`), existing
  entries and their order survive, and a no-op run does not rewrite the file.
- **`.context/equipment.json`.** Read-only to this feature: its presence gates
  the refresh, and the refresh re-baselines hashes for PRISTINE items only.

**The 10-value install tuple.** `parse_install_args` returns a *positional*
`tuple[str, Path|None, bool, bool, bool, bool, str, str|None, bool, LinkMode]`
(`installer/args.py:84-86`, built at `:203-214`), unpacked positionally at
`__main__.py:293-304` and immediately re-bound to keywords at `:305-316`. Four
adjacent `bool` slots (`skill_only`, `no_onboarding`, `defaults`,
`no_default_plugins`) are mutually type-compatible, so a reorder on either side
is a silent semantic swap that neither the type checker nor a smoke test
catches. The keyword re-binding at the call site is the only thing that makes
the coupling readable; it is not a guard.

In-memory result types are all frozen dataclasses returned rather than raised:
`HookResult(installed, skipped, removed, errors, refreshed, nudges)`
(`context/hooks.py:447-466`), `HookStatus` (five booleans,
`context/hooks.py:428-444`), `PluginWireResult` / `PluginInstallResult`
(`context/default_plugins.py:238-270`, `608-624`), `LinkResult` /
`LinkInstallResult` (`installer/link/models.py:59-125`), `RepairPlan` /
`RepairExecutionResult` / `DedupeResult` (`installer/repair.py:123-184`).

## Dependencies

**Upstream (into this feature).** `__main__.main` → `parse_install_args`
(`installer/args.py:84-217`) → `installer/install/orchestrate.install`. The only
inbound contract is the 10-value tuple above.

**Downstream (out of this feature), all reached from `project_init.py`.**
`context.build` / `build.runner`, `context.hooks.install`,
`context.output.agents_md` + `claude_md`, `context.default_plugins`,
`context.domains.config`, `context.domains.equip`. Every one is a
**function-level import inside a `try`** (`installer/install/project_init.py:49-59`,
`172-173`, `235`, `262`, `280`, `305-318`) — the installer must remain importable
and runnable when a downstream module is broken or absent, so import failure
degrades to a printed skip, never a crash.

**One real cycle, deliberately broken.** `installer/repair.py:65` imports
`.install` at module level (it needs `_install_skill_family` and
`_symlinked_skill_install_directory`). `installer/install/orchestrate.py`
therefore cannot import `..repair` at module level and imports it *inside the
function* at `:251` and `:445`. Anyone hoisting those two imports to the top
reintroduces the cycle. `installer/uninstall.py` is the acyclic leaf both
depend on: `repair.py:67` imports `_remove_skill_family` from it, and
`uninstall.py` imports only `.common` and `.link`.

**`installer/link/` is strictly layered, no back-edges.**
`common` → `families`/`models` → `classify` → `create` →
`orchestrate`/`sweep`. `families.py:1-6` states the import law explicitly
(stdlib + `..common` only, never a sibling that would cycle back to
`install`/`repair`/`uninstall`). This is what lets `link/` be imported by
`install/`, `repair.py`, and `uninstall.py` alike.

**Package-attribute indirection is load-bearing, not an accident.**
`installer/install/orchestrate.py:21` and `project_init.py:22` do
`import dummyindex.installer.install as _install_pkg`; `link/sweep.py:10` does
the same for `link`. Calls go through the package attribute
(`_install_pkg.run_link_install` at `orchestrate.py:399`,
`_install_pkg._install_project_hooks` at `project_init.py:111`, `:149`) so that
`monkeypatch.setattr(install_module, ...)` in `tests/test_install_link.py` is
observed. A bare-name call resolved through the module's own globals would not
be. The rationale is recorded at `installer/install/orchestrate.py:5-13`;
"simplifying" these to direct calls silently breaks the tests.

**State ownership by lifetime.** `.context/config.json` = durable project
intent (git); `.claude/settings.json` = shared team declaration (git);
`.claude/settings.local.json` = local tombstones (not git);
`~/.claude/plugins/` = per-machine materialisation (never git).

## Key decisions

- **Five events, ten commands, one entry per event.** Each managed hook event
  holds exactly one sentinel-bearing entry whose `hooks` array may hold several
  commands (`context/hooks.py:270-276`): UserPromptSubmit 2, SessionStart 4,
  Stop 2, PreCompact 1, PreToolUse 1. That shape is what lets
  `install_hook_entry` preserve a user's co-located hook inside the managed
  entry, and it is why "refreshed vs skipped" is decided by a byte-level
  before/after of `settings.json` rather than by comparing to the canonical
  body — the naive comparison would report `refreshed` forever once a user adds
  their own command beside ours (`context/hooks.py:532-551`).
- **The static per-turn reminder is deliberately un-gated.** The first
  UserPromptSubmit command is a `printf` of pre-built JSON with no
  `command -v dummyindex` check (`context/hooks.py:120-131`), because it must
  still fire on an alternate Claude profile that can read project settings but
  has no CLI on PATH. That is the one command `_guard_body` cannot patch through
  a gate, so the global-scope wrapper inserts a silent gate *plus* the
  defer-check guard after the managed comment instead
  (`context/hooks.py:379-409`).
- **Feedback is split across two events by blast radius.** Mining is
  SessionStart-only, fully silenced with `>/dev/null 2>&1`, and writes only the
  bounded gitignored cache (`context/hooks.py:185-196`); reading it is per-prompt
  and keeps stdout because that is the channel its JSON travels on
  (`context/hooks.py:132-143`). Both `memory` verbs swallow every exception and
  return 0 (`cli/memory.py:87-128`) — generated feedback must never block a turn.
  Stop was deliberately left at its two commands; the test asserts that
  (`tests/context/test_hooks.py:1108-1117`).
- **stdout redirection is decided per command by protocol, not by taste.**
  `2>/dev/null` (stderr muted, stdout live) for anything whose stdout carries
  protocol meaning — the UserPromptSubmit JSON, the Stop gate's
  `decision: block`, the PreToolUse guard's `permissionDecision: deny`
  (`context/hooks.py:132-143`, `213-225`, `250-264`). Full `>/dev/null 2>&1`
  only where output is pure side effect — memory mining and the PreCompact
  breadcrumb (`context/hooks.py:185-196`, `229-243`). Getting this backwards
  either leaks noise into every turn or silently disables a gate.
- **The freshness badge is an ability, not an opt-in.** `install_statusline`
  writes only when neither scope defines a truthy `statusLine`, and refuses
  (returning a hand-edit nudge) rather than clobber an unparseable file
  (`context/hooks.py:306-376`). Idempotence without a sentinel is bought
  entirely by never-clobber; the trade-off is that a user who edits our value
  keeps their edit forever and we can never migrate the badge command.
- **Preserve-or-refuse on every settings file.** A `MalformedSettingsError` is
  reported in `errors` and the file is left byte-identical — in install
  (`context/hooks.py:550-551`), in the legacy scrub (`:581-584`), and in
  uninstall (`:646-650`). The same discipline governs config: the orchestration
  does a *strict* `read_config` before the tolerant migration helpers, so
  corrupt state warns and stops rather than seeding defaults
  (`installer/install/project_init.py:326-340`).
- **The one-run opt-out outranks durable policy.** `--no-default-plugins`
  returns before trust disclosure, config migration, settings I/O, or the runner
  probe (`installer/install/project_init.py:300-303`);
  `config.default_plugins_enabled=false` is the persistent form and survives
  reconciliation.
- **`--no-superpowers` collapses into `--no-default-plugins` three times, by
  design.** At parse (`installer/args.py:141-143`, which is why the tuple has no
  `no_superpowers` slot), at the public API
  (`installer/install/orchestrate.py:118`), and again at
  `_auto_init_project` (`installer/install/project_init.py:47`). The second and
  third exist because both functions are public call seams that predate the
  rename; each must accept the old spelling independently. The cost is three
  places to touch when the alias is finally dropped.
- **`--defaults` and `--no-onboarding` stay two booleans and are ORed at the
  call site**, not at parse (`installer/install/orchestrate.py:489`). They carry
  one meaning today; keeping them distinct through the tuple preserves the
  ability to diverge, at the price of two of the four interchangeable bool slots
  noted above.
- **Declaration is separated from materialisation.** Project `settings.json`
  travels in git and expresses team intent; marketplace clones and plugin
  registration are per-machine. The first pass never executes the runner
  (`context/default_plugins.py:472-572`), the second only consumes targets the
  first made effectively eligible (`:676-761`), and an absent `claude` CLI defers
  rather than fails.
- **No commit pin for third-party defaults — rejected because it cannot work.**
  Claude Code materialises marketplaces with `git clone --branch <ref>`, which
  accepts a branch or tag but never a SHA; dummyindex ≤ 0.33.x pinned SHAs and
  every third-party default silently failed to materialise. The `ref` field and
  its validation are gone; `_is_legacy_sha_pin`
  (`context/default_plugins.py:353-370`) exists solely to *heal* the old shape
  instead of reporting it as a conflict. The accepted cost: we consume whatever
  bytes the upstream branch serves at clone time.
- **Trust changes are source changes.** `DEFAULT_PLUGINS` is validated at import
  for unique targets and non-empty reviewed surfaces
  (`context/default_plugins.py:148-193`); user config cannot nominate an
  arbitrary plugin for the reviewed-default materialiser.
- **Repair is scoped to the invocation and only writes the targeted scope.**
  Stale copies at other roots and user+project duplicates are report-only with a
  remediation command; downgrade and unparseable stamps stay report-only unless
  `--force-downgrade`; deletion happens only under an explicit `--dedupe`,
  filtered to the same platform set (`installer/repair.py:331-446`, `493-604`,
  `651-711`).
- **Link direction is fixed `.claude → .agents`, and the family list is
  enumerated, never globbed.** `.agents` is the portable rendering; Claude Code
  is the only host that reads solely `.claude`. The 8 families are main + the 7
  `_SIBLING_SKILLS` labels (`installer/common.py:87-95`), derived in
  `installer/link/families.py:16-24`, because a `dummyindex*` glob would also
  match the equip-generated `dummyindex-verify` skill this feature does not own.
- **Link-mode sequencing is pinned.** `plan_repairs` → direct-write →
  `execute_repairs` → sibling-stamp backfill → `run_link_install`, so links are
  never created against a stale or partially written `.agents` tree
  (`installer/install/orchestrate.py:253-442`). The blank-slate Claude write is
  *deferred* and landed only if linking never happened, enforcing "exactly one of
  {8 links, 8 real dirs}, never a mix, never neither"
  (`installer/install/orchestrate.py:384-441`). The invariant is scoped to the
  blank slate: a hand-deleted partial layout that also hits an unexpected link
  failure can end with siblings absent, which is non-destructive and self-heals
  on rerun (`:407-428`).
- **Symlink allowlists are passed in, never derived from `$HOME`.** One
  `claude_link_allowlist` per run — `frozenset()` at project scope, the two
  `.claude` roots at user scope — is threaded through the preflight, the
  direct-write loop, the link dispatch, and `_install_commands`
  (`installer/install/orchestrate.py:153-164`, reused at `:463`).
- **Curated context is never collateral damage of a reinstall.** An enriched
  `.context/` takes the deterministic-refresh path; a re-cluster requires an
  explicit `rebuild --full` or `ingest`
  (`installer/install/project_init.py:65-118`).
- **Primary success is the skill tree plus the index path.** Guidance, hook,
  plugin, config, and equipment failures print and continue
  (`installer/install/project_init.py:203-223` returns `True` even when the hook
  install raised). The cost is real: a caller cannot infer full readiness from
  the process exit code alone.

## Open questions

- Should the 10-value positional tuple become a frozen dataclass
  (`InstallArgs`)? It would remove the four-interchangeable-bools hazard and let
  `install()` take one argument, at the cost of a public signature change in
  `parse_install_args` and every test that unpacks it.
- Should `install` return a structured aggregate instead of printing? Today the
  only machine-readable signal is the exit code, and partial readiness (hooks
  installed but plugins deferred, say) is discoverable only by parsing prose.
- Is `HookResult.nudges` general or single-purpose? It exists for exactly one
  advisory (`_STATUSLINE_UNWRITABLE_NUDGE`, `context/hooks.py:321-327`) and has
  no rendering contract of its own beyond the caller printing it.
- Should the reviewed registry, the declaration service, and the subprocess
  adapter be separate modules? `context/default_plugins.py` is 783 lines holding
  policy data, settings I/O, classification, rendering, and process adaptation —
  near the repo's split threshold, and the same threshold that already forced
  `install` and `link` into packages.
- What release gate approves a third-party default or a reviewed-surface change?
  The structural validation proves unique targets and non-empty surfaces; it
  cannot prove the quality of the human review, and with no pin it says nothing
  about the bytes the upstream branch will serve at clone time.
- Should durable plugin policy be per-default rather than an all-defaults config
  switch plus per-target settings tombstones? Policy currently lives in two
  stores with different lifetimes.
- Should `uninstall` offer an explicit project-integration teardown (managed
  guidance, hooks, marketplace declarations, plugin decisions)? Today it removes
  the skill family and slash commands only; `context/hooks.uninstall:617-688`
  exists but is not reached from the `dummyindex uninstall` path.

## Index conflict (code wins)

`.context/map/symbols.json` is **stale for `dummyindex/context/hooks.py`** as of
this revision. It places `HookStatus` at 322 (real: 429), `install` at 376
(real: 486), `uninstall` at 503 (real: 617), `status` at 580 (real: 694) — a
+64 to +114 drift — and still names a `statusline_nudge` symbol the code no
longer defines (the current function is `install_statusline`, at
`context/hooks.py:346`). Every `hooks.py` range in this document was re-derived
from source and is correct against HEAD. Fix the artefact with
`dummyindex context rebuild --changed`; do not "correct" this document to match
the index.
