# Project equipment toolkit — plan

`confidence: INFERRED`

## Where it lives

**Policy domain — `dummyindex/context/domains/equip/`.** Pure decisions, no
argv, no printing.

- `generate/` — `catalog.py` is the policy core (`build_catalog`,
  `dummyindex/context/domains/equip/generate/catalog.py:75-111`); `specialists.py`
  holds the capability→template table; `adopt.py` resolves coverage;
  `render.py` fills templates; `detect.py`, `gaps.py`, `plan.py`, `proposal.py`
  round it out.
- `lifecycle/` — `hashing.py` is the ownership authority
  (`dummyindex/context/domains/equip/lifecycle/hashing.py:17-19`); `status.py`
  carries `classify_item` / `status` / `refresh` / `reset` / `uninstall`
  (`dummyindex/context/domains/equip/lifecycle/status.py:1-24`); `manifest.py`
  reads and writes the ledger; `evolve.py` is the patch seam; `remove.py` the
  surgical single-record drop.
- `plugins/` — `marketplace.py` (catalog parsing), `blast_radius.py`
  (`dummyindex/context/domains/equip/plugins/blast_radius.py:33-38`),
  `install_plan.py` (pure native-vs-vendor + approval policy,
  `dummyindex/context/domains/equip/plugins/install_plan.py:36-53`),
  `sources.py` (the domain's one deliberate I/O exception, behind a `Runner`
  port), `discover.py`, `vendor.py`.
- `wiring/hooks.py` installs the format hook under equip's own sentinel
  (`dummyindex/context/domains/equip/wiring/hooks.py:31-55`); `wiring/safety.py`
  holds the never-clobber predicates.
- `models.py` / `enums.py` / `constants.py` / `errors.py` — frozen records, closed
  alphabets, `SCHEMA_VERSION = 4` and `EQUIP_SENTINEL`
  (`dummyindex/context/domains/equip/models.py:44-245`,
  `dummyindex/context/domains/equip/constants.py:14-21`).
- `eval/` — the pure scoring stage (`cases.py`, `score.py`, `models.py`).

**Base layer — `dummyindex/context/`.** Below the domains, importable by config
without a cycle.

- `default_plugins.py` — the reviewed built-ins, the `WiredEntry` adapter, trust
  disclosure, declaration, and target-filtered materialization
  (`dummyindex/context/default_plugins.py:64-235`,
  `dummyindex/context/default_plugins.py:472-760`).
- `claude_plugins.py` — marketplace and `enabledPlugins` settings primitives
  (`dummyindex/context/claude_plugins.py:105-171`).
- `claude_settings.py` — `load_settings` / `write_settings` /
  `install_hook_entry` / `remove_hook_entries` / `MalformedSettingsError`.
- `hooks.py` — the five managed session-hook events plus the statusLine
  (`dummyindex/context/hooks.py:270-276`, `dummyindex/context/hooks.py:486-571`).
- `output/bootstrap.py` — source of `ALWAYS_ON_TURN_REMINDER`, the string the
  `UserPromptSubmit` hook injects (`dummyindex/context/output/bootstrap.py:78-91`).
- `domains/atomic_io.py` — `_replace_bytes` / `write_text_atomic` /
  `normalize_eof_newline` (`dummyindex/context/domains/atomic_io.py:13-67`).

**CLI boundary — `dummyindex/cli/equip/` and `dummyindex/cli/hooks.py`.**
Wire-only. `dispatch.py` routes the verbs and owns the apply pipeline
(`dummyindex/cli/equip/dispatch.py:102-144`,
`dummyindex/cli/equip/dispatch.py:393-568`); `verbs.py` the lifecycle verbs;
`install.py` the interactive installer; `discover.py`, `plugin_state.py`,
`eval.py`, `seed.py`, `common.py` the rest. `cli/hooks.py` is the
`install|uninstall|status|defer-check` surface for the managed hooks.

## Architecture in three sentences

A pure policy core decides — `build_catalog` turns a stack profile plus
convention docs plus a preflight report into a `CatalogDecision`, and
`build_install_plan` turns candidates into mechanism-plus-approval decisions —
while thin CLI adapters interpret those decisions and perform every write. Every
generated artifact is fingerprinted at write time into an `origin_hash` recorded
in `.context/equipment.json`, and every later operation (apply, refresh, reset,
uninstall, re-vendor) re-hashes the file on disk and compares before touching it,
so "did the user take ownership of this?" is answered by data rather than
convention. External effects are pinched into narrow ports: subprocesses run
through injected `Runner` callables with fixed argv and no shell, and settings
mutation runs through the sentinel-keyed `claude_settings` primitives that
preserve-or-refuse on an unparseable file.

## Data model

No database. Persistence is four JSON stores with distinct authority, all written
through tmp-file + `replace`:

| Store | Authority | Written by |
|---|---|---|
| `.context/equipment.json` | the lifecycle ledger: what dummyindex owns, its hash baseline, version, origin, and mechanism | `write_manifest` via `dummyindex/cli/equip/dispatch.py:535-540` |
| `.context/config.json` `wired` | declared project intent, `<plugin>@<marketplace>` + descriptive version | `_write_back_wired`, `dummyindex/cli/equip/install.py:449-490` |
| `.claude/settings.json` (+ `settings.local.json`) | effective marketplace declarations, `enabledPlugins` decisions, hook entries, `statusLine` | `claude_plugins` / `claude_settings` primitives |
| `.context/equipment-evals/*.result.json` | recorded eval runs, read back by `equip status` | `dummyindex/cli/equip/eval.py` |

Schema evolution is additive and tolerant: `SCHEMA_VERSION = 4` (the bump that
introduced `EquipmentKind.PLUGIN`), `EquipmentItem.from_dict` defaults every v2/v3
field to `None`, and `invariants` is omitted from `to_dict` when empty so a v3
manifest stays byte-identical (`dummyindex/context/domains/equip/models.py:114-159`,
`dummyindex/context/domains/equip/constants.py:11-14`).

There is no transaction spanning stores. `_apply_write` orders the steps so a
partial failure degrades rather than corrupts: files first, then hooks (a
`MalformedSettingsError` is a warning, files stay written), then the merged
manifest, then silent eval seeding
(`dummyindex/cli/equip/dispatch.py:469-545`). The atomicity that does exist is
per-file: `_replace_bytes` writes a **uniquely named** temporary sibling and
`replace`s it, precisely because hooks from two Claude profiles can write the same
repo-local cache concurrently (`dummyindex/context/domains/atomic_io.py:13-34`).

## Key decisions

**Hash baseline over sentinel.** The in-body `GENERATED_SENTINEL` is a human
marker; the sha256 recorded at write time is the authority
(`dummyindex/context/domains/equip/models.py:27-29`,
`dummyindex/context/domains/equip/lifecycle/status.py:8-12`). This is why
`write_text_atomic` is contractually byte-faithful — a silent EOL normalization
there would make every generated artifact look user-edited, so callers wanting
pre-commit-clean output call `normalize_eof_newline` *after*
(`dummyindex/context/domains/atomic_io.py:37-47`).

**Canary invariants as manifest metadata, not rendered bytes.** A template's
load-bearing convention substrings are recorded in `EquipmentItem.invariants` and
never written into the file, so they cannot shift the origin hash; a user edit
that deletes one is surfaced as `INVARIANT_BROKEN` rather than a silent
`CUSTOMIZED`, and refresh prints it as its own `⚠` alarm section
(`dummyindex/context/domains/equip/generate/specialists.py:63-78`,
`dummyindex/context/domains/equip/enums.py:78-94`,
`dummyindex/cli/equip/verbs.py:39-68`).

**Specialists are abilities, not opt-ins.** `_all_templated_capabilities` hands
the whole templated alphabet to `resolve_coverage` on every pass; `--specialist`
and `add-specialist` were demoted from gates to order-forcers so an
already-applied specialist keeps a stable manifest position and hash identity
(`dummyindex/context/domains/equip/generate/catalog.py:62-72`,
`dummyindex/cli/equip/dispatch.py:311-313`). Rejected: generating a specialist
only when a proposal happened to name its capability.

**Merge, never rebuild, the manifest.** Records this run does not re-derive are
carried forward verbatim, including a generated record under a now-stale name;
this run's records win name collisions
(`dummyindex/cli/equip/dispatch.py:513-533`). Rejected: rewriting the ledger from
the current catalog, which silently dropped marketplace and vendored entries.

**Explicit verb.** Bare `equip` prints usage and exits 2; only the read-only
`--dry-run` survives verblessly, because a help/discovery probe must never mutate
the repo (`dummyindex/cli/equip/dispatch.py:102-144`).

**Reviewed defaults stay in the base layer.** `default_plugins.py` imports
nothing from `cli/`, `installer/`, or `context/domains/`, so
`context/domains/config.py` can depend on `default_wired()` without a
config→equip→config cycle (`dummyindex/context/default_plugins.py:1-33`).
Rejected: moving the reviewed set under `domains/equip/`.

**Declaration and materialization are two operations.** `wire_default_plugins`
only classifies and writes settings; `install_default_plugins` runs the `claude`
CLI once per eligible target. This preserves useful project state when the
executable is absent and keeps settings mutation out of every installer
invocation (`dummyindex/context/default_plugins.py:472-554`,
`dummyindex/context/default_plugins.py:676-760`).

**No commit pin for default marketplaces.** Claude Code materializes with
`git clone --branch <ref>`, which accepts branch/tag names but never a commit
SHA, so third-party defaults track the upstream default branch and disclose the
blast radius instead of pinning; a dummyindex ≤ 0.33.x SHA pin left in settings is
*healed* to the unpinned shape rather than treated as a conflict, because it fails
the clone at every session start
(`dummyindex/context/default_plugins.py:1-18`,
`dummyindex/context/default_plugins.py:353-409`). This is a reversal of the
earlier pinned-defaults design and is load-bearing for `i-have-adhd`, which now
declares an opt-in SessionStart shell hook and `runs_code=True`
(`dummyindex/context/default_plugins.py:185-191`).

**Declared surfaces never waive the gate.** `analyze_blast_radius` reads
attacker-controlled catalog metadata; `_plan_one` therefore sets
`requires_approval = not candidate.trusted` unconditionally
(`dummyindex/context/domains/equip/plugins/install_plan.py:36-49`). Trust policy
also stays out of the generic settings primitives: `add_marketplace` is a plain
upsert, and the reviewed-default wrapper adds its own identity guard at the policy
boundary (`dummyindex/context/claude_plugins.py:105-124`,
`dummyindex/context/default_plugins.py:373-409`).

**The per-prompt contract must survive a missing CLI.** The first
`UserPromptSubmit` command is a pure `printf` of a pre-serialized, `shlex.quote`d
JSON payload with no `command -v dummyindex` self-gate, so an alternate Claude
profile that can read project settings but has no `dummyindex` on PATH still gets
the behavior contract; `_guard_body` special-cases exactly that command when
adding the global defer-check guard
(`dummyindex/context/hooks.py:105-145`, `dummyindex/context/hooks.py:379-409`).
No project path or prompt text is interpolated into the command string.

**Install classifies by file bytes, not by body comparison.**
`install_hook_entry` preserves co-located user hooks inside the managed entry, so
comparing against the canonical body would report "refreshed" forever once a user
wires their own hook beside ours; the honest signal is a byte-level before/after
read of `settings.json` (`dummyindex/context/hooks.py:534-549`).

**Two sentinels, deliberately.** `DUMMYINDEX_AUTO_REFRESH` (legacy name, kept so
upgrades still recognize and scrub old entries) keys the managed session hooks;
`DUMMYINDEX_EQUIP:<event>` keys equip's format hook. They coexist and uninstall
independently (`dummyindex/context/hooks.py:56-73`,
`dummyindex/context/domains/equip/constants.py:16-21`).

**Preserve-or-refuse everywhere settings are touched.** An unparseable
`settings.json` is never overwritten: hook uninstall records the error and skips,
the legacy scrub returns empty, `install_statusline` returns an advisory nudge,
and `wire_default_plugins` records the error per target and continues
(`dummyindex/context/hooks.py:644-678`,
`dummyindex/context/hooks.py:574-584`, `dummyindex/context/hooks.py:366-375`,
`dummyindex/context/default_plugins.py:521-547`).

## Open questions

- `add_marketplace` overwrites a same-name entry whose source differs, while
  `_declare_marketplace` refuses it. Should the interactive `equip install` path
  adopt the same identity-conflict contract, or is upsert the intended behavior
  for a user-driven install (`dummyindex/context/claude_plugins.py:105-124`,
  `dummyindex/context/default_plugins.py:373-409`)?
- Native dynamic installs record `origin_ref=None` and enable a moving
  marketplace HEAD, while vendoring pins a resolved SHA. The base layer documents
  why a commit pin is not expressible for Claude Code's clone
  (`dummyindex/context/default_plugins.py:1-10`) — does that constraint also make
  a recorded ref useless for the native path, or should equip resolve one purely
  for lifecycle/audit purposes (`dummyindex/cli/equip/install.py:258-287`,
  `dummyindex/cli/equip/install.py:335-446`)?
- Reviewed defaults never enter `.context/equipment.json`; they live in
  `config.wired`, settings, and Claude's per-machine registry. That means
  `equip status` cannot report them at all. Is the absence from the ledger the
  intended long-term contract (`dummyindex/context/default_plugins.py:676-760`,
  `dummyindex/cli/equip/verbs.py:74-118`)?
- `_USER_PROMPT_SUBMIT_PAYLOAD` bakes `ALWAYS_ON_TURN_REMINDER` verbatim into
  `settings.json` with no version stamp inside the command. `hooks install`
  rewrites the body when the text changes, but nothing else does — is a
  reinstall the only intended upgrade path for a repo whose reminder text has
  drifted (`dummyindex/context/hooks.py:110-145`,
  `dummyindex/context/hooks.py:534-549`)?
- `wire_default_plugins` keeps a `runner` parameter it immediately `del`s as a
  compatibility shim, and no in-tree caller passes it
  (`dummyindex/context/default_plugins.py:477`,
  `dummyindex/context/default_plugins.py:505`; callers at
  `dummyindex/cli/init.py:73`, `dummyindex/cli/wire.py:240`,
  `dummyindex/installer/install/project_init.py:345`). What still depends on the
  signature?
