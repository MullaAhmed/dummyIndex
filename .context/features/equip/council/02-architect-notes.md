# Architect notes — Project equipment toolkit

## What I changed

- **Added an explicit bounded-context statement** at the top of "Where it lives".
  The dev's draft opened with a file tour; it never said what equip *does not*
  own. It now names the exclusions (init orchestration, convention-doc
  authorship, Claude Code's own materialization) and names the real shape of the
  seam: a decision boundary, not a package boundary — three of the four stores
  are written by modules outside `domains/equip/`.
- **Converted the package tour into a role/anchor table.** Same information,
  ~40% fewer words, and every row now carries a verified `path:range` instead of
  a whole-file cite. Replaced `models.py:44-245` (whole file) with
  `models.py:82-159` (the record + its serialization pair) and expanded
  `lifecycle/status.py:1-24` with the five verb line numbers from
  `map/symbols.json` (`classify_item:143`, `status:190`, `refresh:221`,
  `reset:314`, `uninstall:343`).
- **Added a "Patterns in use" table** with a why-not-the-alternative column. Each
  row is a pattern name + `path:range` + the trade-off. No pattern is asserted
  without both.
- **Added a `## Dependencies` section.** The dev's draft implied direction
  ("importable by config without a cycle") but never enumerated it. Now upstream,
  downstream, the near-cycle, and the shared-mechanism coupling are separate,
  verified lists.
- **Promoted three decisions the draft left implicit** (below).
- **Fixed four citation ranges**, verified line-by-line against source:
  `plugins/blast_radius.py:33-38` → `:33-37` (the file is 37 lines);
  `enums.py:78-94` → `:79-95` (the `ItemState` class body);
  `generate/specialists.py:63-78` → `:66-80` (the invariants paragraph plus the
  field declaration); `plugins/sources.py:31-56` → `:31-49` (the port and its
  default adapter, excluding the unrelated `ToolAvailability`).
- **Kept, after verifying, every citation the brief flagged.** The five managed
  events are `_CLAUDE_HOOKS` at `hooks.py:270-276`
  (`UserPromptSubmit`/`SessionStart`/`Stop`/`PreCompact`/`PreToolUse`); the
  `UserPromptSubmit` payload does bake `ALWAYS_ON_TURN_REMINDER`
  (`output/bootstrap.py:78-91`) through `shlex.quote` at `hooks.py:110-128`; the
  unpinned-default healing is exactly `_is_legacy_sha_pin`
  (`default_plugins.py:353-370`); `_replace_bytes` does use `NamedTemporaryFile`
  with `delete=False` for a unique sibling (`atomic_io.py:13-34`). None trimmed.
- **Cut filler:** the "`detect.py`, `gaps.py`, `plan.py`, `proposal.py` round it
  out" tail, the repeated "pure policy / thin CLI" restatement in three sections,
  and prose paraphrases of docstrings that a `path:range` already carries.

## Patterns named

Each is in the plan's pattern table with a `path:range` and its trade-off:

- **Functional core / imperative shell** — `generate/catalog.py:75-111` decides,
  `cli/equip/dispatch.py:393` writes. Cost named: partial-failure ordering
  cannot live in the pure core and therefore leaks into the CLI.
- **Hash-baseline lifecycle** — `lifecycle/hashing.py:17-19` +
  `enums.py:79-95`. Named the state *lattice*, not just the three states:
  `CUSTOMIZED` and `INVARIANT_BROKEN` are refinements of `USER_MODIFIED`
  reachable only when an item carries invariants (`enums.py:91-95`).
- **Verb table dispatcher** — `cli/equip/dispatch.py:102-144`, chosen over
  argparse subparsers so the verbless `--dry-run` carve-out is one branch.
- **Port / adapter** — `Runner = Callable[[list[str]], RunResult]` at
  `plugins/sources.py:31`, injected at `default_plugins.py:676-700`.
- **Sentinel-keyed idempotent upsert** — `wiring/hooks.py:31-55` over
  `claude_settings.install_hook_entry:64`.
- **Ledger merge, last-writer-per-name** — `cli/equip/dispatch.py:512-533`.
- **Tolerant reader / strict writer** — `models.py:114-159`.
- **Out-of-band canary metadata** — `generate/specialists.py:66-80`; recording
  the invariants cannot shift the hash they police.
- **Declare-then-materialize** — `default_plugins.py:472-554` then `:676-700`.
- **Narrow legacy-shape healing** — `default_plugins.py:353-370`, exact-shape
  match only.
- **Preserve-or-refuse (fail-closed write)** — four sites, all verified.
- **Ability, not opt-in** — the draft named this only for specialists. It is
  actually a *recurring* policy shape at three sites: specialists
  (`generate/catalog.py:62-72`), statusLine (`hooks.py:553-562`, "it is an
  ability, not an opt-in"), and the per-turn reminder (`hooks.py:110-145`).
  Unifying them is the single largest structural insight added.

## Dependencies surfaced

- **Equip's domain reaches out to exactly four places**, verified by import
  grep, not inferred: `domains/preflight/models.PreflightReport`
  (`generate/catalog.py:26`), `domains/dev_pick.SubagentType`
  (`generate/adopt.py:31`), `domains/atomic_io.write_text_atomic`
  (`lifecycle/evolve.py:16`), and `claude_settings`/`claude_plugins`.
- **No base-layer module imports `domains.equip`.** `claude_settings.py:3-4` and
  `default_plugins.py:72` mention it in docstrings only. This is what makes the
  layering claim true rather than aspirational, and it is now stated as such.
- **The near-cycle is named and located:** `domains/config.py:68` imports
  `WiredEntry`/`WiredKind`/`default_wired` from `default_plugins`, while
  `cli/equip/install.py:20` imports the same module. Moving reviewed defaults
  under `domains/equip/` would create `config → equip → config`.
- **Shared-mechanism coupling distinguished from a cycle:** `claude_settings` is
  consumed by both hook owners under different sentinels — `hooks.py:56-73`
  (`DUMMYINDEX_AUTO_REFRESH`, five events) and `constants.py:16-21`
  (`DUMMYINDEX_EQUIP:<event>`, the format hook).
- **Downstream enumerated:** `cli/equip/*`, `cli/status.py`, `cli/help.py`,
  `cli/build_loop/waves.py`, `domains/audit/catalog.py`,
  `domains/buildloop/mapping.py`, `installer/install/project_init.py`.

## Decisions promoted

- **Ordering policy lives in the CLI because the domain is pure.** The draft
  described `_apply_write`'s degrade-don't-corrupt sequence but never said *why*
  it is not in the domain. A pure function cannot express "already wrote three
  files, now degrade." Stated as a decision with its cost.
- **Mechanism in the base layer, policy in its caller.** This is the reason
  `add_marketplace` (`claude_plugins.py:105-124`) is a plain upsert while
  `_declare_marketplace` (`default_plugins.py:373-409`) refuses an identity
  conflict — the draft reported the divergence as an open question without
  naming the rule that produced it. Both now appear: the rule under Key
  decisions, the unresolved consequence under Open questions.
- **The split-brain is structural, not accidental.** Promoted from a single open
  question into the Data model: there are *five* stores, the fifth (Claude's
  per-machine registry) is not written by dummyindex, and nothing reconciles
  them. `equip status` reads the manifest plus the evals dir only
  (`cli/equip/verbs.py:74-118`), which is precisely why reviewed defaults are
  invisible to it.
- **`install_hook_entry` sits in `claude_settings`, not equip**, because two
  sentinel families need the same merge primitive. Stated where the base layer
  is described.
- **Healing is deliberately shape-exact.** `set(source) == {"source","repo","ref"}`
  plus a 40-hex ref (`default_plugins.py:362-370`) — so a clonable branch/tag
  pin stays a conflict. The draft cited the healing but not its narrowness.
- **The second `UserPromptSubmit` command does not redirect stdout** because
  that stream carries the hook's JSON (`hooks.py:132-142`). Load-bearing and
  easy to "clean up" into a bug.
- **Hash-baseline trade-off made explicit:** a semantically-null whitespace edit
  permanently forfeits refresh for that file; `reset`
  (`lifecycle/status.py:314`) is the deliberate escape hatch.

## Audit trail — conflicts found

Code wins in all three. The plan cites source line numbers, not the index.

1. **`map/symbols.json` is stale for `domains/atomic_io.py`.** It records
   `write_text_atomic` at line 12 and `normalize_eof_newline` at 28; the file
   actually has `_replace_bytes:13`, `write_text_atomic:37`,
   `normalize_eof_newline:50`, and `_replace_bytes` is absent from the index
   entirely. The index predates the unique-tempfile extraction. Fix with
   `dummyindex context rebuild --changed`.
2. **`map/symbols.json` is stale for `generate/catalog.py`.** It records
   `build_catalog` at line 61; the function is at 75. Line 62 is now
   `_all_templated_capabilities`, which the index does not list at all.
3. **A source docstring contradicts the code.** `atomic_io.py:42` refers to
   `equip/lifecycle/hashing.text_hash`; the function is `content_hash`
   (`lifecycle/hashing.py:17`) and no `text_hash` exists anywhere in the tree.
   Harmless today, misleading to anyone tracing the baseline. Not fixed here —
   this council writes docs, not source.

No catalogued prose doc was quoted. Every `docs.md` entry touching equip is
`DocConfidence.MEDIUM` with large `broken_refs` sets — e.g.
`docs/plans/2026-06-10-equip-plugin-manager.md` lists `Runner`,
`.context/equipment.json`, and `.claude/settings.json` among 29+ broken
references, and `docs/internal/plans/2026-06-06-equip-v2.md` cites a
`domains/equip/hookwire.py` that no longer exists. Treated as historical
context; every claim in the plan is anchored to source read this session.
