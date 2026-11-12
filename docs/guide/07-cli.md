# 07 — CLI surface

Every command. What it does. Why it exists.

> **The CLI is the agent's backbone. You do not run it by hand.** The skill and council invoke these commands to move bytes around atomically. Everything that needs judgment stays in markdown (see [the closing rule](#what-is-not-a-cli-command)). A human's interface is **slash commands** in Claude Code or `$skill` mentions in Codex. The one exception is the one-time **Installation** bootstrap below.

> It is `pip install dummyindex` plus `dummyindex install`. A human runs it in a terminal to put the skill in place.

## Installation — the human bootstrap (run once)

The one place a human uses the terminal. Every later section is invoked by an agent.

### `dummyindex install [--platform claude|agents|both] [--scope user|project] [--dir PATH] [--skill-only] [--no-onboarding] [--defaults] [--no-default-plugins] [--no-superpowers] [--dedupe user|project] [--force-downgrade]`

- Copies all eight skills into `.claude/skills/` for Claude Code. It copies them into `.agents/skills/` for the platform-agnostic `agents` selector. That selector covers Codex, Cursor, Copilot CLI, OpenCode, Amp, Gemini CLI, Goose, Pi, Cline, and other Agent-Skills/AGENTS.md harnesses. **The default is `both`.** A flagless install produces the universal layout. This is a documented compatibility break with the previous claude-only default.

  Pass `--platform claude` or `--platform agents` to narrow to one host.

  `codex` still works as a **deprecated alias** for `agents`.

  It prints a one-time deprecation warning on stderr. It renders a byte-identical `.agents/skills` tree.
- `--scope user` (default) installs under the user's home. `--scope project` installs under `<PATH>`.
- Claude uses `/dummyindex*`. Codex discovers the same family through `/skills`. Codex invokes it as `$dummyindex*`.
- Claude's `/tokens` remains a host-specific command. Its reporter reads Claude transcript files. Codex uses native `/status` for current context and session tokens. Codex uses `/usage` for account usage.
- **Auto-init**: on a git repo, auto-init builds `.context/` and writes the selected host guidance. Claude receives `.claude/CLAUDE.md` and hooks. Codex receives its active project instruction file and no Claude settings. Pass `--skill-only` to copy skills alone.
- **Installs five managed Claude hook events** during auto-init. The five events are UserPromptSubmit, SessionStart, Stop, PreCompact, and PreToolUse Write. UserPromptSubmit runs the static per-turn output and skill contract, plus dynamic `memory prompt-context`. SessionStart runs `plan-update`, `memory session-start`, `gc signal`, and silent `memory mine`. Stop runs `memory nudge` and `reconcile-gate`.

  PreCompact runs `memory breadcrumb`. PreToolUse Write runs `guard-doc-write`. None of them rebuilds the index. None of them stamps the anchor. The legacy pre-v0.13.5 shell-rebuild hooks did both.
- **When Claude is selected, auto-init refreshes equip-generated tools** to the current templates. This lets `/dummyindex-update` carry that Claude toolkit forward. A Codex-only install neither creates nor refreshes Claude equipment.
- `--defaults` and `--no-onboarding` write config non-interactively. Claude-only installs default to `sonnet` with hooks on. Codex-only installs default to `current` with hooks off. `both` defaults to portable `current` with Claude hooks on.
- `--no-default-plugins` skips every native default plugin for this run. `--no-superpowers` remains a compatibility alias with identical behavior. The flags do not persist an opt-out. They keep the always-on project output policy described below.
- **Repair on reinstall.** Rerunning `install` also repairs stale copies. An older dummyindex version left these copies behind. Repair covers stale preambles and stale managed guidance blocks. It is scoped to the invocation's selected platforms and targeted scope. Everything else is reported with the exact command to fix it.

  A duplicate copy at both user and project scope is reported.

  It is never deleted, unless `--dedupe user|project` is passed. A copy stamped newer than the running package is left alone, unless `--force-downgrade` is passed. Symlinked copies are always refused. See [docs/COMMANDS.md](../COMMANDS.md#platform-selector-repair-on-reinstall-and-dedupe) for the full contract.

#### Reviewed default plugins and always-on behavior

When `claude` or `both` is selected, install and auto-init declare the selected defaults in project `.claude/settings.json`. They make one best-effort materialization pass:

1. `superpowers@claude-plugins-official` from the official marketplace.
2. `caveman@caveman`, with marketplace source `JuliusBrussee/caveman` (tracks the latest upstream default branch). The reviewed plugin exposes skills and commands. It also exposes `SessionStart` and `UserPromptSubmit` Node command hooks. So `runs_code=true`. Install writes `.caveman.json` as `{"defaultMode": "manual"}`.

   Caveman therefore starts inactive.

   Install skips the write when `.caveman.json` or `.caveman/config.json` already exists. Install also skips the user home directory, Codex-only installs, and `caveman@caveman` set to `false`. `/caveman` still works. Env var `CAVEMAN_DEFAULT_MODE` overrides the file.
<!-- test-anchor:policy-selfapply:begin -->
3. `i-have-adhd@i-have-adhd`, with marketplace source `ayghri/i-have-adhd` (tracks the latest upstream default branch). The reviewed plugin exposes one skill plus an opt-in `SessionStart` shell command hook. So `runs_code=true`. The hook requires a per-profile `.i-have-adhd-always` flag. The skill sets `disable-model-invocation: true`.

   Enabling the plugin alone never makes it self-apply.

   Dummyindex's managed project policy and per-prompt reminder carry the behavior across profiles. They stand alone without the plugin.
<!-- test-anchor:policy-selfapply:end -->
4. `ponytail@ponytail`, with marketplace source `DietrichGebert/ponytail` (tracks the latest upstream default branch). The reviewed plugin exposes skills and commands. Its hooks are `SessionStart`, `SubagentStart`, and `UserPromptSubmit` Node command hooks. It also includes a band UI module with a local task ledger. So `runs_code=true`.

   The webhook is empty by default.

   Once a user sets it, every task row leaves the machine. The `SubagentStart` hook injects the ponytail ruleset into every subagent. This includes dummyindex-dispatched subagents. The hook applies when mode is not `off`. The default mode is `full`.

The three third-party entries are a narrow, reviewed built-in exception. They track latest because Claude Code materializes marketplaces with `git clone --branch <ref>`. That command accepts branch and tag names only, never a commit SHA. So a commit pin can never install. Sources and blast radii are disclosed before settings or runner action.

Adding or swapping a source requires another source review and release.

This does **not** relax `context equip`'s approval requirement for any other third-party source. Marketplace declaration is preserved even when the Claude CLI is unavailable, so Claude Code can resolve the target later. Failures are reported per target, and they do not fail indexing or prevent later independent defaults from being attempted.

<!-- test-anchor:policy-restatement:begin -->
A Codex-only install writes no `.claude/**` files. It invokes no Claude runner. It receives the behavior through the active managed **project** instruction file instead. Claude's managed project block carries the same always-on output policy. Apply it on every reply without waiting for an invocation.

Replies use the `i-have-adhd` shape at minimum verbosity.

Replies do not use `caveman` chat voice. Lead with the outcome or next action. Keep prose compact. Number multi-step work, at most 5 items per group. Suppress tangents, restate current state, and preserve technical and safety detail.

Subagent prompts and SendMessage bodies use concise Chinese with caveman rules.

Code, commits, docs, and final reports stay English. Repo docs follow ASD-STE100. Before acting, compare the request with every exposed skill's trigger rules. Invoke every match without waiting to be asked. Explicit user formatting requests and safety requirements win.

The policy is not written to Codex's global guidance.
<!-- test-anchor:policy-restatement:end -->

There are three distinct opt-out layers for the native defaults.

- **One run, all four:** pass `--no-default-plugins`, or its legacy `--no-superpowers` alias. The gate runs before config reconciliation, marketplace or settings changes, runner probes, and code execution. A current config remains byte-identical.
- **Durable, all four:** set `.context/config.json` field `default_plugins_enabled` to `false`. Reinstall or update does not backfill missing defaults. This holds while this explicit state remains disabled.
- **Durable, one target:** set its project or local `enabledPlugins` value to `false`. That tombstone takes precedence over project and local values. It remains `false`. Dummyindex never materializes it.

Malformed config fails closed. Install and init warn. They perform no default marketplace declaration, enabled-plugin write, runner action, backfill, or config mutation. The built-in tuple stays unused.

### `dummyindex uninstall [--platform claude|agents|both] [--scope user|project] [--dir PATH]`

- Removes the selected host's skill family and version stamp. Claude command aliases owned by dummyindex are removed with a Claude selection.
- Project-scope Codex removal cleans that project's managed guidance. User scope cleans global guidance. It also cleans only a current or `--dir` project block. That block is stamped as the auto-init of that user install. Explicit project and ingest blocks are preserved, and so are legacy unowned blocks.

  Claude guidance and project hooks have separate lifecycle commands.

  They are left intact.
- Best-effort cleanup removes now-empty skill and command parent directories.

## Backbone

### `dummyindex ingest [path] [--root DIR] [--platform claude|agents|both] [--no-hooks] [--no-default-plugins] [--no-superpowers] [--force] [--depth light|standard|deep] [--docs PATH]...`

- Primary entry point. Equivalent to `context init`.
- Runs the deterministic backbone on `path`.
- Writes `.context/` and host guidance. Codex uses its active project instruction file. That file is `AGENTS.override.md`, `AGENTS.md`, or a configured fallback. Claude uses `.claude/CLAUDE.md`. Claude also installs hooks by default.
- Refuses to replace a curated/enriched index unless `--force` is explicit. Use `rebuild --changed` for a non-destructive refresh. `--depth` is a one-run council-depth override. `--no-default-plugins` (or compatibility alias `--no-superpowers`) applies the one-run native-default gate above.
- Smart default: a relative `path` under cwd writes output to cwd. An absolute path writes output to that path.
- `--docs PATH` (repeatable) adds external doc folders to the source-docs catalog. The in-repo docs are discovered automatically. They are `README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any root-level `*.md`, and the folders `docs/`, `doc/`, `documentation/`, `ADR/`, and `RFC/`.

### `dummyindex context init [path] [--root DIR] [--platform claude|agents|both] [--no-hooks] [--no-default-plugins] [--no-superpowers] [--force] [--depth light|standard|deep] [--docs PATH]...`

- Same as `ingest`.

### `dummyindex context rebuild [--changed] [--full] [path] [--root DIR] [--docs PATH]...`

- Full or incremental rebuild.
- `--changed` re-extracts only files whose content hash changed. This is the manual incremental path. The manifest tracks both code and in-repo docs. So a README edit is detected. As of v0.13.5, you run this manually.

  It does not run from a hook.
- **Non-destructive on an enriched index.** When `features/INDEX.json` carries a curated taxonomy, `--changed` no longer re-clusters or re-stubs. A curated taxonomy means a feature renamed off `community-*`, or an `INFERRED` confidence. It refreshes only the deterministic, enrichment-free artefacts (`map/files.json`, `map/symbols.json`, `conventions/naming.{json,md}`, `source-docs/INDEX.{json,md}`, `features/symbol-graph.json`). It preserves `tree.json` abstracts and every per-feature `spec.md`. It prints a reconcile report with drifted features and unassigned new files.

  It deliberately leaves `meta.indexed_commit` unchanged until the curated reconcile procedure finishes.

  Then that procedure runs `reconcile-stamp`. A fresh deterministic-only index, with all `community-*` and `EXTRACTED` entries, still full-builds.
- `--full` forces the destructive full re-cluster regardless. It prints a warning. The warning says the run discards any curated taxonomy and enrichment. Run the full rebuild after an intentional from-scratch reset. Otherwise, pass `--changed` for the non-destructive path.
- `--docs PATH` accepts the same form as `ingest`. Pass it on every rebuild that should preserve the same external doc roots.
- Outputs `added / modified / removed` summary (or the reconcile report on the enriched path).

### `dummyindex context check [path] [--root DIR] [--auto-refresh] [--quiet] [--docs PATH]... [--versions]`

- Manifest-based drift detection. It compares current source and doc content hashes to the stored manifest. It reports `added / modified / removed`.
- `--auto-refresh` runs `rebuild --changed` automatically when drift is detected.
- `--quiet` suppresses human-readable output. The exit code still reports clean (`0`), drift (`1`), or usage or setup failure (`2`).
- `--docs PATH` mirrors `ingest`. External doc roots are not reported as `removed`.
- `--versions` is a separate, read-only diagnostic. It compares the running CLI, the `.context` stamp, and every repo or user skill stamp, for Claude and for Codex. It compares each one independently. It reports PATH shadowing. It never fixes anything.

  It always exits 0.
- A manual inspection command. It **no longer auto-refreshes**. It is **not** the SessionStart hook. The SessionStart hook is `plan-update`, which is described below.

**`check` ratchets and reference checks:**

- `--budget` enforces word-count ratchets in `.context/doc-budget.txt` and `tests/data/skill-budget.txt`.
- `--style` enforces the style ratchet in `.context/style-budget.txt`. It flags sentences over 20 words and filler words.
- With no style ratchet, `--style` only reports and prints the seed command. It exits 0.
- `--refs` lists durable docs that cite `proposals/` or `audits/`. A hit exits 1.
- `--update-ratchet` needs `--budget` or `--style`. It updates only the named group and only lowers entries. Alone, it exits 2.
- Word or violation growth, or an unrecorded overage, exits 1.

### `dummyindex context plan-update [path] [--root DIR]`

- The SessionStart-hook command (v0.13.5).
- It prints a markdown drift report to stdout. It prints one line per feature. That line appears when the feature's source-file mtime exceeds the newest mtime of its docs. Stdout is empty when nothing is stale.
- Claude Code's `SessionStart` hook takes the plain stdout as `additionalContext`. It needs no JSON wrapping.
- It is advisory only. It does not rebuild or rewrite anything. The running session reconciles the named features' docs in place.

### `dummyindex context reconcile-gate [path] [--root DIR]`

- The Stop-hook reconcile gate (v0.23.0). It reads the Stop hook's JSON from stdin (`stop_hook_active`, `session_id`, `transcript_path`).
- It prints a Claude Code `{"decision":"block","reason":…}` payload. It blocks the session exit once. It prints this payload when `.context/` is stale (`compute_drift` reports drift). It prints it after a substantial session. A substantial session has subagent runs, or main-thread output at or above the significance threshold.

  The `reason` is a scoped directive.

  It tells the agent to re-run the council for the drifted features, using `/dummyindex --recouncil <feature>`. It also tells the agent to place any new files. Then it runs `dummyindex context reconcile-stamp`.
- It stays silent and allows the stop in these cases. The index is fresh. The stop is re-entrant (`stop_hook_active` true). The session is trivial. The user opts out through `"auto_council": false` in `.context/config.json`.

  On a re-entrant stop, it blocks **once** and never traps the session.
- The **hook never writes or stamps `.context/`**. The agent runs the council and advances the anchor. This preserves the "no hook may stamp" invariant. It always exits 0. A Stop hook must never fail the turn.

### `dummyindex context bootstrap [path] [--root DIR] [--platform claude|agents|both]`

- Regenerates the selected host guidance without rebuilding `.context/`. For Claude, it regenerates the managed block in `.claude/CLAUDE.md`. For Codex, it regenerates the active project-level instruction file. It can regenerate both.
- The default remains `claude` for backward compatibility. `codex` still works as a deprecated alias for `agents`. See Installation above.
- Use it when managed guidance text changes, for example during schema bumps.

## Hooks (installed by `ingest` or `install --scope project`)

### `dummyindex context hooks install [path] [--root DIR]`

- It is idempotent. It installs **five** `.claude/settings.json` hook events. None of them rebuilds the index or stamps the anchor:
  - UserPromptSubmit injects the compact always-on output and skill-routing contract. It also injects an independent `memory prompt-context` payload. That payload covers validated recurring corrections and the current prompt.
  - SessionStart runs `dummyindex context plan-update`. That command prints the drift report and refreshes the freshness badge cache. It also runs `dummyindex context memory session-start` for the memory block. It runs `dummyindex context gc signal` for the commit-throttled `/dummyindex-gc` nudge. It runs one fully silent `dummyindex context memory mine` refresh.
  - Stop runs `dummyindex context memory nudge` for the handoff checkpoint call to action. It also runs `dummyindex context reconcile-gate` for the block-once reconcile gate.
  - PreCompact runs `dummyindex context memory breadcrumb`. That command writes a breadcrumb to `now.md`.
  - PreToolUse (`Write`) runs `dummyindex context guard-doc-write`. This is the managed doc homes guard.
- `--global` writes `~/.claude/settings.json` instead. The hooks then fire in **every** repo. Each hook gates itself on `.context/` existing. A repo's own `--local` install overrides the global one. Global hook bodies carry a `dummyindex context hooks defer-check` guard.

  That guard yields when the repo has its own dummyindex hooks.
- **Upgrade scrub** (local scope) removes any legacy `git post-commit` script. It also removes a sentinel-bearing `PostToolUse` entry. Pre-v0.13.5 versions installed both. User-authored hooks have no sentinel. The scrub leaves them untouched.

**PreToolUse language hint.** The PreToolUse matcher is `Write|Edit|MultiEdit|Agent|Task|SendMessage`. For `Agent` and `Task`, the hook reads `prompt`. For `SendMessage`, it reads `message`. Code, URLs, and paths are removed first. Text under 200 characters is then not judged.

It warns when the CJK share (CJK characters / (CJK characters + Latin words)) is below 0.5.

The warning goes out as `additionalContext`. It never denies, and `doc_guard_enabled` does not turn it off.

### `dummyindex context hooks defer-check [path] [--root DIR]`

- It is a silent exit-code probe. The `--global` hook guard uses it. It exits 0 (defer) when the repo has its own `--local` dummyindex hooks. Otherwise it exits 1.

### `dummyindex context hooks uninstall [path] [--root DIR]`

- Removes the managed hook entries and scrubs any legacy entries. It leaves the rest of `.git/hooks` and `settings.json` untouched.

### `dummyindex context hooks status [path] [--root DIR]`

- Prints whether each managed hook is installed. The `HookStatus` type carries `claude_user_prompt_submit`, `claude_session_start`, `claude_stop`, `claude_pre_compact`, and `claude_pre_tool_use`. `all_installed` requires all five.

## Onboarding & preflight

### `dummyindex context preflight [path] [--root DIR] [--json]`

- It is a read-only inventory of the repo's existing `.claude/` setup. It runs before any write. The inventory is actionable for a Claude run. It is informational for a Codex-only run.
- The skill runs it as Phase 0 on every invocation and surfaces the summary.

### `dummyindex context onboard [path] [--root DIR] --model current|opus|sonnet|haiku|fable [--scope repo|subdir|explicit] [--scope-path PATH] [--mode light|standard|deep] [--hook|--no-hook] [--doc PATH]... [--platform claude|agents|both] [--defaults]`

- Persists the first-run council preferences (scope, mode, model, session hooks, external docs) to `.context/config.json`.
- The model is never silently defaulted. `--model` or `--defaults` is required.
- `--defaults` uses an explicit `--platform` when you supply one. Otherwise it infers the managed Claude and Codex guidance markers. It preserves the historical Claude baseline only when neither marker exists. `codex` still works as a deprecated alias for `agents` here. See Installation above.
- The skill's platform-aware Phase 1.2 setup drives this. Claude-only asks five questions. Codex-only asks only portable preferences. It passes `--model current --no-hook`. A both-host run uses `current`.

  It asks for or retains the Claude hook preference.

  Re-run it through the active host's `--reconfigure` skill invocation.

### `dummyindex context config show [path] [--root DIR]`

- Prints `.context/config.json`. It exits 1 when no config exists yet. The skill reads that exit as its "needs onboarding" signal.
- `get`/`set` are reserved for a future release.

## Enrichment (called by the council)

### `dummyindex context enrich-plan [path] [--root DIR]`

- It emits `.context/cache/_enrich_plan.json`. This work list covers the `tree.json` stubs.
- Grouped into per-file batches.
- Used by the dev to enrich tree abstracts.

### `dummyindex context enrich-apply [path] [--root DIR] --from-json FILE`

- Merges `{node_id: abstract}` into `tree.json` atomically.
- Bumps `confidence: EXTRACTED → INFERRED` on each touched node.
- Warns and exits non-zero on unknown `node_id`.

## Features

### `dummyindex context features-rename [--root DIR] --from ID --to ID [--name "..."] [--summary "..."]`

- Atomic feature folder rename.
- Updates: folder name, `feature.json`, every nested `flows/*.json`, `INDEX.json`, `INDEX.md`, `graph.json`.
- Used by the architect agent during the structural regrouping pre-stage.
- Idempotent. When `--from == --to`, the verb refreshes metadata alone.

### `dummyindex context features-list [--root DIR] --json`

- Read-only. Prints `.context/features/INDEX.json` as one JSON document (`schema_version` 1). `--json` is required.
- Exits 1 with an error envelope when the index is missing or its `schema_version` is unsupported. Exits 2 on a usage error.
- Contract: `docs/schemas/features-list.json`.

## Sessions and toolkit (GUI JSON facade)

These are top-level commands, not `context` subcommands. Each prints one JSON document. The contract is `docs/engine-contract.md`.

### `dummyindex sessions list [--root DIR] [--projects-root DIR] --json`

- Read-only. Lists Claude Code sessions, main and subagent, from the transcripts store. `--root` keeps sessions whose `cwd` is under DIR.
- The document reports unparseable session data inside itself. It uses state `unknown` and adds a warning. It never reports this as an error exit.

### `dummyindex toolkit list|show|add|remove|enable|disable|install`

- `list` and `show` are read-only. `add`, `remove`, `enable`, and `disable` mutate the project toolkit and print one document.
- `install` has two steps. `--preview` prints a plan hash. Then `--yes --plan-hash H` applies it. Only `github:<owner>/<repo>[/<path>][@<ref>]` sources are accepted.
- Failures print an error envelope. Exit 2 is a usage error. Exit 1 is an operational failure.

### `dummyindex context features-merge [--root DIR] --from ID --into ID [--as-section NAME] [--note "..."]`

- Absorbs a trivial feature into another as a section (architect consolidation of dangling features).
- It appends into `features/<into>/<section>.md`. It never clobbers existing content. It updates `INDEX.json` and the graph.

### `dummyindex context flow-remove [--root DIR] --feature X --flow Y`

- Drops a flow's JSON and MD files.
- Updates: `feature.json` (remove from `flow_ids`), `INDEX.json` (decrement `flow_count`), `graph.json` (remove flow node and edges).
- Used by the dev when filtering trivial or false-positive flows.

### `dummyindex context scaffold-feature [--root DIR] --id ID --name "..." [--summary "..."] --file PATH [--file PATH]...`

- It places net-new files into a **brand-new** feature. The council decided this feature should stand on its own. The command folds the source into the curated taxonomy **without** re-clustering. It is atomic and deterministic.
- It creates `features/<id>/`. The new `feature.json` derives `members` from `map/symbols.json` for the given files. `entry_points` and `flow_ids` stay empty. `confidence: EXTRACTED`. It also writes a deterministic `spec.md` stub.

  The scaffolder uses the same writer.

  It writes `docs.md` when the source-docs catalog matches.
- It appends the feature to `INDEX.json`. It regenerates `INDEX.md` and `graph.{json,html}`. It reuses the index writers. It never re-clusters. It never invents `community-N`.
- It exits 2 on these errors. The `--id` is a duplicate. The id is a reserved `community-*` id. No `--file` is given. A `--file` is not a real file under the repo.

  All validation runs before any write.
- The council reconciliation phase (Phase 3) calls this to place a net-new cluster reported as unassigned.

### `dummyindex context assign-files [--root DIR] --feature ID --file PATH [--file PATH]...`

- It places net-new files into an **existing** feature. It adds them to `files`. It recomputes `members` from `map/symbols.json`.
- Updates that feature's `INDEX.json` counts and regenerates `INDEX.md` and `graph.{json,html}`.
- **Preserves** the feature's enriched `spec.md`, `plan.md`, and `concerns.md`. These files are never touched.
- It is idempotent for files that are already assigned. It skips them silently. That case is not an error. It exits 2 on these errors. They cover a missing feature, no `--file`, and a `--file` that is missing or outside the repo.

  All validation runs before any write.

### `dummyindex context unassign-files [--root DIR] --feature ID --file PATH [--file PATH]...`

- The **subtractive inverse** of `assign-files`. It removes files from an existing feature (`files` minus the given set). It recomputes `members` from `map/symbols.json` over what remains. It refreshes INDEX counts and `INDEX.md` and `graph`. It re-drops the `.pending-enrichment` marker, because the feature's scope changed and it owes re-enrichment.
- **Does not require the files to exist on disk.** The point is that they were *deleted*, or moved to another feature. It is idempotent on a path the feature does not own.
- Preserves the enriched `spec.md`, `plan.md`, and `concerns.md`. It exits 2 on these errors. They cover a missing feature, no `--file`, a path outside the repo, or a removal that would empty the feature. An emptying removal needs `features-remove` instead. That avoids stranding the feature.
- The reconcile procedure calls this for `removed_files` when a feature loses *some* of its files.

### `dummyindex context features-remove [--root DIR] --feature ID [--force]`

- Atomically **deletes a feature whose code is gone**. It drops `features/<id>/`, which holds the folder, the enriched docs, and the flows. It drops the `INDEX.json` entry, regenerates `INDEX.md`, and decrements the top-level `flow_count`. It drops the node and edges from `graph.json`.
- **Safety guard:** it refuses with exit 2 when the feature still owns files that exist on disk. Those files are live. Unassign the dead paths, or merge the feature instead. `--force` overrides the guard.
- The reconcile procedure calls this for `removed_files` when a feature loses *all* of its files. The standalone deletion `features-merge` only does this as a side effect of merging into a target.

## Reconcile — commit-anchored update (v0.15.3)

This is the non-destructive successor to a full re-cluster. `.context/` records the commit it was last reconciled against (`meta.indexed_commit`). These commands diff against that commit. They let the council update only what changed, and they preserve the curated taxonomy and enrichment. See `skills/council/65-reconcile.md` for the procedure.

### `dummyindex context reconcile [path] [--root DIR] [--json]`

- **Read-only.** It diffs `meta.indexed_commit`..HEAD, plus the working tree including untracked files. It reports these items. **Drifted features** own a changed or removed file. **Removed files** are gone. **Unassigned new files** belong to no feature.

  **Features awaiting enrichment** carry a `.pending-enrichment` marker.
- `--json` emits the report `{indexed_commit, drifted_features, removed_files, unassigned_new_files, awaiting_enrichment, has_drift}`. The council procedure consumes this report.
- It never writes. It never decides taxonomy. It returns an empty report when there is no anchor. That happens on a non-git tree or a pre-v0.15.3 index.

### `dummyindex context mark-enriched [--root DIR] --feature ID`

- Clears a feature's `.pending-enrichment` marker after the council re-enriches it. The `scaffold-feature` and `assign-files` commands set the marker. While it is set, `reconcile-stamp` refuses to advance the anchor past that feature. A place-then-restart therefore cannot orphan an un-enriched stub.
- Idempotent. With no marker, it is a no-op and exits 0. It exits 2 only on a missing feature folder.

### `dummyindex context reconcile-stamp [path] [--root DIR] [--force] [--heal-orphaned]`

- **The write boundary.** It advances `meta.indexed_commit` to HEAD. Run it *after* the council places every unassigned file and enriches every placed or drifted feature. This is the one command, besides a fresh `ingest`, that moves the anchor.
- **Refuses with exit 1** while unassigned new files or awaiting-enrichment features remain. Advancing past them would silently forget them. It does **not** block on drifted features. Only the stamp clears drift, so blocking on drift could never advance the anchor.
- `--force` anchors anyway and prints what it skipped. It warns when uncommitted source remains outside `.context/`. That source re-surfaces as drift on the next reconcile. Off-git, it is a graceful no-op that exits 0.
- `--heal-orphaned` opts into auto-healing an orphaned anchor. An orphaned anchor comes from a history rewrite. Examples are a rebase or a squash. It can also come from a commit that was never fetched. Instead of refusing, the stamp re-baselines at HEAD with a loud warning.

  Un-reconciled blockers still refuse. Without the flag, the refusal is unchanged.

## Context maintain loop (`maintain plan|begin|next|done|stamp|status`)

This command assembles the maintenance runbook in one step. The runbook runs `rebuild --changed`, then `reconcile`, then per-feature recouncil, then `reconcile-stamp`. The CLI does only deterministic plumbing and makes no LLM calls. The host skill consumes `next` units and launches one subagent per unit. It then reports back through `done` and `stamp`.

Durable state lives in committed `.context/fleet/maintain-<ts>/` directories, which hold `RUN.md` and `state.json`.

Writes are atomic. Runs are prefix-scoped, so other proposals' runs under `.context/fleet/` are never picked up. Any killed session resumes from `state.json`.

### `dummyindex context maintain plan [--max-features N] [--json] [--root DIR]`

- Read-only assembly. It computes the reconcile report. It prints the ordered work list. Drifted features come first, then features awaiting enrichment. Each feature has `estimate:` lines.

  Stub-node counts come from a single `enrich.build_plan` walk.

  Active council stages come from `council_batch.active_stages`. The command also prints a clearly labelled `units x 90s` heuristic. That heuristic is not a wall-clock promise. It notes unassigned new files separately, as placement work and not units. Exit 0.

### `dummyindex context maintain begin [--max-features N] [--all] [--json] [--root DIR]`

- Writes the run manifest and state under `.context/fleet/maintain-<ts>/`. It requires either `--max-features N` or an explicit `--all`. An unbounded spend never starts silently. A missing bound is refused with exit 2. It refuses politely with exit 0 when the index is in sync.

### `dummyindex context maintain next [--run NAME] [--json] [--root DIR]`

- Prints the earliest incomplete unit. The order matches the stage-major frontier of `council-batch --next`. It also prints the remaining counts. The host skill launches exactly one unit, and the output carries the order. Done units are never repeated.

### `dummyindex context maintain done --feature ID [--stage N] [--run NAME] [--root DIR]`

- Marks a unit complete in state.json. Without `--stage`, the feature's earliest pending stage is taken. An unknown feature and stage pair errors out. It fails loudly.

### `dummyindex context maintain stamp --feature ID [--run NAME] [--force] [--to <sha>] [--heal-orphaned] [--root DIR]`

- Wraps `reconcile-stamp` for the finished feature. The flags pass through. It ticks the feature's units done in state only when the stamp succeeds. A refused stamp leaves the run untouched.

### `dummyindex context maintain status [--run NAME] [--json] [--root DIR]`

- Counts done, pending, and skipped units. It reports elapsed time and the labelled heuristic remaining estimate. It also reports the run's anchor and mode. It always exits 0.

## Restyle loop (`restyle plan|begin|next|done|stamp|status`)

This is an ASD-STE100 rewrite of curated `features/` and `conventions/` docs. The CLI is deterministic. It snapshots each unit, checks the rewrite, and records the ruleset. The host skill rewrites each unit between `next` and `done`. The restyle loop makes no LLM calls.

- `plan` is read-only. It lists units with their doc, strict, and advice counts. It prints `already restyled (ruleset N)` once stamped. It prints `nothing to restyle` on an index without curated docs.
- `begin --all` or `begin --max-units N` starts a run. An unbounded run needs `--all`. `begin` refuses with exit 1 while a run is unfinished. `--force` starts a new run after a stamp.
- `next` prints the next unit, its doc paths, and the rewrite brief. It prints a completion hint when all units are done.
- `done <unit>` checks the unit against its snapshot. It exits 1 and names each doc and token when a protected token is lost. Otherwise it prints the remaining strict violations and `advice:` lines. It warns about new protected tokens.
- `stamp` records the ruleset in `meta.json` once every unit is done.
- `status` reports unit counts for the run.

### `dummyindex context restyle plan [--json] [--root DIR]`

### `dummyindex context restyle begin --all | --max-units N [--force] [--json] [--root DIR]`

### `dummyindex context restyle next [--run NAME] [--json] [--root DIR]`

### `dummyindex context restyle done <unit> [--run NAME] [--json] [--root DIR]`

### `dummyindex context restyle stamp [--run NAME] [--json] [--root DIR]`

### `dummyindex context restyle status [--run NAME] [--json] [--root DIR]`

## Council (called by skill procedures)

### `dummyindex context section-write [--root DIR] --feature X --section NAME --from-file PATH`

- Atomic placement of a markdown into `features/<X>/<NAME>.md`.
- Sections: `spec`, `plan`, `concerns` (v0.14). Legacy sections are also accepted: `README`, `architecture`, `implementation`, `data-model`, `security`, and `product`. These predate v0.14. The CLI accepts them for backwards compatibility.
- It writes to a temp file and then renames it, so the write is atomic. It is idempotent.
- Used by the dev at stage 1, the architect at stage 2, and the critics at stage 3.

### `dummyindex context council-log [--root DIR] --feature X --stage N --agent NAME --status STATE [--note "..."]`

- Appends to `features/<X>/council/_council-log.json`.
- Status values: `started`, `complete`, `failed`, `skipped`.
- Used by every persona at start and end of work.
- It enables resumption. The skill reads the log to see what is already done.

### `dummyindex context council-batch [--root DIR] --next [--feature ID]... [--force] [--mode light|standard|deep] [--cap N] [--no-tree-enrich] [--json]`

- It returns the next parallel batch of council dispatch units. The batch holds the earliest incomplete stage across all non-trivial features. It holds up to `--cap` agents.
- Tree enrichment (stage 5) is appended **by default** in every mode. `--no-tree-enrich` drops it for a run. `--tree-enrich` is accepted as a no-op.
- `--feature ID` (repeatable) scopes the frontier to those features. `--force` re-councils already-complete scoped features. It requires `--feature`.
- `--json` emits `{complete, stage, mode, cap, units[]}`. Each unit carries `feature_id`, `stage`, `role`, `subagent_type`, and `framework`.
- When `complete` is `true`, all features have finished every active stage for the given mode.
- It is the council twin of `build --next-wave`. The skill fans units out to parallel Task subagents. It waits at a barrier. Then it re-runs `--next`.

### `dummyindex context conventions-write [--root DIR] --section NAME --from-file PATH`

- It places markdown atomically into `.context/conventions/<section>.md`. These agent-authored docs cover folder-organization, coding-practices, testing, and data-access.
- The Phase 1.5 convention authors place their output through this.

### `dummyindex context reality-check [--root DIR] --feature ID [--demote] [--json]`

- It runs a post-synthesis fact-check (Phase 3.5). It pulls concrete claims, such as "X calls Y" or `file.py:42`, out of a feature's docs. It verifies them against `map/symbols.json` and the symbol graph.
- `--demote` flips the feature's confidence to `AMBIGUOUS` when claims contradict the AST.

### `dummyindex context dev-pick [path] [--root DIR] --feature ID`

- It resolves which stack-specialist "dev" persona authors a feature's docs. The first match wins. The match uses the feature's file list and dependency tokens.
- It prints JSON with `persona_id`, `subagent_type`, `framework`, and `fallbacks`. The output is deterministic. It uses no LLM.

## Refresh

### `dummyindex context refresh-indexes [path] [--root DIR]`

- Rebuilds `.context/INDEX.md` from disk.
- Rebuilds `features/INDEX.md` from `features/INDEX.json`.
- Rebuilds `features/graph.json` and `features/graph.html` from the per-feature data.
- Use it after enrichment and renames. It reconciles the derived artifacts.
- **Also migrates** legacy layouts. It moves `graph/` contents under `features/`. It shrinks long CLAUDE.md blocks.
- **Preserves a curated scan.** `features/graph.json` regenerates only while it is still the deterministic seed (`confidence: EXTRACTED`). After the codebase-scan stage authors it (`INFERRED`), a rebuild leaves it alone. The rebuild re-renders `graph.html` around it. This is the same contract that protects an enriched `spec.md`.

### `dummyindex context scan-check [path] [--root DIR] [--json]`

It validates the curated codebase scan at `features/graph.json` against the schema-v2 contract. It is the feedback half of the authoring loop. The stage writes the scan. It runs this check. It fixes what the check reports.

Then it re-runs the check.

The check runs in **one pass**. Every problem surfaces in each round trip.

- caps — ≤ 60 nodes, ≤ 120 edges, ≤ 3 `topModels`, ≤ 10 `topTools` / `topIntegrations`
- closed alphabets — `kind` ∈ `entry cron agent model tool service store external`, edge `kind` ∈ `calls reads writes triggers`
- lengths — label ≤ 28, sub ≤ 40, edge label ≤ 24, detail ≤ 200, `sourceRef` ≤ 120, group ≤ 24
- referential integrity — node ids unique, every edge endpoint resolves to a node
- formats — `project.slug` lowercase-dashed, `project.date` `YYYY-MM-DD`, `domain` a bare host (`openai.com`, never `https://openai.com`)

Each violation prints as `<json.path>: <message> [<code>]`. It exits `0` when clean. It notes when the scan is still the uncurated seed. It exits `1` on violations. It exits `2` when there is no scan to check.

`--json` emits `{ok, path, confidence, violations[]}`.

The check is deterministic. It uses no LLM.

## Retrieval CLI

### `dummyindex context query "..." [--root DIR] [--top-k N] [--budget N] [--json]` ✅ shipped (v0.12)

- It runs a PageIndex-style tree search. The agent passes a natural-language question.
- Walks `features/INDEX.json` → relevant feature → relevant section.
- It returns the cited markdown and `path:range` references.
- Budget-capped (default 2000 tokens) for predictable cost in agent loops.
- It is deterministic. It uses no LLM in the loop. It is a view over the same JSON that the agent walks manually.

### `dummyindex context graph <verb> [SYMBOL] [SYMBOL2] [--limit N] [--depth N] [--hops N] [--json] [--root DIR]`

Bounded, read-only query verbs over the full extracted symbol graph. `features/symbol-graph.json` can be legacy JSON, compact JSON, or a shard manifest. The commands rebuild the same logical graph automatically:

- `graph callers-of SYMBOL` and `graph callees-of SYMBOL` list direct `calls` edges. Each row carries its call site.
- `graph impact SYMBOL [--depth N]` lists transitive dependents. It uses a reverse walk over dependency edges. The default depth is 2.
- `graph path A B` gives the shortest link chain between two symbols. Each hop shows its relation and direction.
- `graph neighbors SYMBOL [--hops N]` lists every node within N hops. It follows any relation except `rationale_for`. The default is 1 hop.
- `graph dead-code` lists code nodes with zero incoming `calls`, `uses`, `imports_from`, or `inherits` edges. The check is purely graph-driven. Dispatch-dict and function-body-import idioms can give false positives until those edges are extracted.
- `graph community ID|SLUG|NAME` lists members of one Leiden community. It ranks them by dependency degree. It accepts the raw community integer. It accepts a card slug from `features/graph-communities.json`. It also accepts any symbol, and it falls back to that symbol's own community.

Symbols resolve by node id, bare name, or `path.py:name` suffix. An ambiguous name lists cited candidates instead of guessing. Every row cites `file:line`. It attaches the extracted docstring when one exists. `--limit` bounds output.

The default is 20 rows, or 50 for `dead-code`.

The pre-truncation total is still preserved. It exits `0` when the query is answered. A valid empty answer counts. It exits `1` on an unknown or ambiguous symbol, no path, or an empty community. It exits `2` on a usage error, or when there is no `features/symbol-graph.json` to query.

`--json` emits the stable result structure. The check is deterministic. It uses no LLM.

### `dummyindex context debt [path] [--root DIR] [--write] [--json]`

- It is a technical-debt ledger for the repo's **Python** source. It lists `# TODO:`, `# FIXME:`, `# HACK:`, and `# DEBT:` markers. The list is per file, sorted by path, and repo-relative.
- Each row carries its declared upgrade trigger (`# DEBT: <ceiling>; upgrade: <trigger>`). A row without a trigger is tagged `no-trigger`. The body ends with the `N markers, M with no trigger.` tally.
- It prints to stdout by default. `--write` also persists `.context/debt.md`. `--json` emits the stable `DebtLedger` structure.
- It is deterministic and uses no LLM. Re-running it on an unchanged tree gives byte-identical output. Rows are always repo-relative. No absolute path ever leaks.

## Session memory (v0.15)

### `dummyindex context memory session-start|roll|init [path] [--root DIR]`

- `session-start` emits the SessionStart block (HANDOFF and MEMORY) into the session's `additionalContext`. It stays silent when the `remember` plugin's `.remember/` directory is present. This prevents double injection. The hook calls it. The hook is folded into the existing sentinel entry.
- `roll` moves dated entries down the tiers. The tiers are `now.md`, then `recent.md`, then `archive.md`. The command is idempotent.
- `init` creates the session-memory store stubs at `.context/session-memory/` when they are absent.
- `ingest` seeds the store. The store is never regenerated. It is invisible to drift detection.

### `dummyindex context memory nudge [path] [--root DIR]`

- It is the **Stop**-hook command. It reads the hook's stdin JSON (`transcript_path`, `session_id`). It prints a `hookSpecificOutput.additionalContext` payload when three conditions hold. The session is significant. Subagents ran, or main-thread output reached 40k tokens.

  The session was not already nudged, and it was not already saved.

  No `remember` plugin is present. The payload prompts the agent to offer a handoff call to action. Otherwise, it stays silent. It never auto-saves. It never fails the turn.

### `dummyindex context memory breadcrumb [path] [--root DIR]`

- It is the **PreCompact**-hook command. It writes a deterministic, tagged breadcrumb entry to the top of `now.md`. The entry holds the branch, `git diff --stat`, the file list, and the subagent and turn counts. It ensures a session is never lost to compaction. It stays silent when the `remember` plugin is present.

  It never stamps the commit anchor.

### `dummyindex context memory mine [path] [--root DIR]`

- It is the **SessionStart** feedback refresh. It unions the active `CLAUDE_CONFIG_DIR`, `~/.claude`, and home `.claude-*` profiles. It opens only root-level main transcript JSONLs. Those JSONLs sit in this repo's exact project folder. Every candidate must be an external human prompt row.

  Its resolved `cwd` equals the repo.

  Subagents, tool rows, meta and task events, and foreign rows are excluded. Two explicit positive corrections after the latest revocation make a skill durable.
- It writes only `.context/cache/skill-feedback.json`. The file uses schema 1. It holds at most 64 safe slugs and positive counts. It holds no prompt text or event metadata. On a first run, the empty state stays absent.

  It does not rewrite unchanged bytes.

  It stays silent and fail-open.

### `dummyindex context memory prompt-context [path] [--root DIR]`

- It is the **UserPromptSubmit** feedback command. It validates the local cache. It combines the cache with a direct correction or revocation in the current `prompt`. It emits one compact `hookSpecificOutput.additionalContext` JSON payload, or nothing. A current correction applies on that same turn.

  A current revocation suppresses the skill.
- Cache reads reject symlinks. They reject unknown fields. They reject invalid order, counts, or slugs. They reject more than 64 entries, and files over 32 KiB. The output is re-rendered fixed policy.

  It is never raw cache or transcript text.

  It is capped at eight skills and 1,600 characters. `i-have-adhd` applies its response behavior directly. Other skills are invoked only when exposed and triggered, or explicitly named.

This privacy-safe branch is derived from Headroom's deterministic mining technique. The older `failure-patterns.md` tool-signature report remains explicit and unwired because structured tool inputs are not safe automatic prompt material.

## Build loop (v0.15)

The `context equip ...` commands prepare shared project capabilities for every host. Native discovery and hook installation are optional adapters. A missing equipment manifest does not block native delegation.

### `dummyindex context propose --slug S --title "..." [--route K=V]... [--root DIR] [--force]`

- It is the build loop for grounded planning. It scaffolds `.context/proposals/<slug>/`. The scaffold holds `proposal.json`, `spec.md`, `plan.md`, and `checklist.md`.
- It runs a deterministic consistency scan. The scan reuses `query` and uses no LLM. It records related features and conventions in `proposal.json`. It also writes a `## Consistency` block in `spec.md`.
- `--route K=V` is repeatable. Keys are `implementer|auditor|decisions`. Values are a model-family alias: `current|opus|sonnet|haiku|fable`. The flag records the optional model-routing block in the scaffolded `proposal.json`. An absent route means unrouted.

  The route is never silently defaulted.
- `--force` overwrites an existing proposal.
- Why: it gives `/dummyindex-plan` a structured, index-grounded scaffold to fill, rather than drafting into the void.

### `dummyindex context equip apply [path] [--root DIR] [--dry-run] [--for-proposal S] [--specialist C] [--platform agents|claude|both] [--lesson-file F] [--source [--yes]] [--json]`

- It prepares canonical capability bodies in `.context/equipment/` from the index and preflight data. It records ownership in `.context/equipment.json` (schema v4). Every host uses these same bodies. `--platform claude` adds thin native references and supported hooks. Default preparation creates no new Claude setup.

  Existing pristine native bodies migrate to references.

  Edited or evolved files stay registered at their current paths.
- **`apply` is an explicit verb.** A bare `dummyindex context equip` is a help probe. It has no verb and no flags. It prints usage. It **exits 2 without writing**. A discovery probe never mutates the repo.

  The only verbless form is the read-only `equip --dry-run` preview.

  `apply` also **refuses** (`exit 1`) on a repo with no `.context/`. Equip renders *from* the index, so run `dummyindex ingest` first.
- It generates the implementer, tester, reviewer, and verify skill. It also generates every template-backed specialist (`db | security | performance | docs | search`). Native formatter hooks require the Claude adapter. Shared instructions use explicit changed file paths.
- **Generated vs adopted.** A template backs some capabilities (**db / security / performance / docs / search**). The template generates each one as a real, file-backed `<proj>-<cap>-specialist.md`. That file carries a marker and `version`, `origin_hash`, and `grounded_in` fields. Its lifecycle is managed like the core four. A capability with **no** template (for example, frontend → *Frontend Developer*) is adopted manifest-only.

  Its manifest entry reads `path: ""`.

  The adoption writes no file.
- `--for-proposal S` covers the capabilities that `S`'s `plan.md` and `checklist.md` demand. It adopts the ones that no template backs. RLS and tenant-isolation map to `security`. `--specialist C` forces capability `C` to lead the specialist order. Neither flag is needed to *get* a template-backed specialist.

  Every one is generated on every pass.

  Already-applied specialists are carried forward. So a plain re-apply never drops or renames one.
- Equipment-eval scaffolding and scoring are removed. Existing user-authored suites are left untouched.
- `--source [--yes]` sources each db, security, performance, docs, and search specialist. It also sources procedure specialists. Sourcing uses catalogs before templates. It checks seed marketplaces, including ECC, first. Then it checks skills.sh (`npx --no skills find`).

  Then it runs a GitHub search.

A qualified `skills/<name>/SKILL.md` becomes the body under a repo overlay. That file is pinned to a commit sha and scanned. If no candidate qualifies, the template stays. Untrusted or `warn:` candidates need `--yes`. `block:` findings never adopt.

With no `gh`, it prints `source: gh unavailable — templates kept`.

A later `apply --source` reports `needs-reverify (upstream changed)`. Re-source with `equip reset NAME`, then run `apply --source`. The sourced body lives at `.context/equipment/<name>.md`. Plain `apply` keeps it (`(sourced, kept)`). `refresh` skips it.

`reset` restores the template and clears the origin fields.

  `--source --dry-run` is a read-only query. It writes nothing. With `--json`, sourcing lines go to stderr.
- `--dry-run` writes nothing. Real runs are additive and never clobber existing files.

### `dummyindex context equip add-specialist CAPABILITY [--root DIR] [--dry-run] [--json]`

- It forces one grounded specialist (`db | security | performance | docs | search`). The result is a `<proj>-CAPABILITY-specialist` agent. A plain `apply` already generates every template-backed specialist. Use this verb to pin one explicitly. It stays idempotent and additive.

  A later plain `equip` preserves it.
- An unknown `CAPABILITY` exits `2` and prints the valid list. Capabilities with no template, such as `frontend`, count as unknown here. A `--for-proposal` run covers them instead, through manifest-only adoption.
- The flag form is `dummyindex context equip apply --specialist CAPABILITY`.

### `dummyindex context equip discover [QUERY] [--repo OWNER/NAME] [--root DIR] [--json]`

- **Plugin manager (dry-run).** It fetches the seed marketplaces' `marketplace.json`. For a `QUERY`, it also runs a GitHub code search. It prints a ranked plan. With no `QUERY`, it matches the detected stack's capabilities. With one, it ranks by query and capability overlap.
- `--repo OWNER/NAME` also accepts a full GitHub URL. It adds one extra collection repo to the search universe, beyond the seed marketplaces. Use it for a low-profile repo that the marketplaces do not list.
- Each candidate shows its **blast radius**. That covers the surfaces it declares. `hook`, `mcp`, `lsp`, and `bin` run code. `agent`, `skill`, and `command` are inert. It also shows its trust tier.

  Anthropic-official is trusted.

  It writes nothing. It requires `gh`. It warns and degrades when absent.

### `dummyindex context equip install <plugin>@<marketplace> [--yes] [--scope project|local|user] [--repo OWNER/NAME] [--usage-doc PATH|--skip-usage-doc] [--root DIR]`

- It installs one approved plugin. The install plan decides between **two mechanisms**:
  - **Native wiring** applies to a marketplace plugin. It adds the plugin to `extraKnownMarketplaces` and `enabledPlugins` in `.claude/settings.json`. The default scope is `project`. Scope `local` writes `settings.local.json`. Scope `user` writes `~/.claude/settings.json`.

    It records a `MARKETPLACE` item in the manifest.
  - **Vendor** applies to a loose-collection skill (`InstallMechanism.VENDOR`). It resolves the source repo's HEAD to a **pinned commit sha**. It fetches that skill's `SKILL.md` at the sha. It stamps the file and copies it to `.claude/skills/<name>/SKILL.md`. It adds no settings wiring.

    It records a `VENDORED` manifest item with the pinned ref.

    Writes never clobber. An absent target or a prior dummyindex-vendored copy is written again. A user file is refused with `exit 1`. So is a hand-edited vendored copy that has gone USER_MODIFIED. Run `equip uninstall` first to re-vendor.
- A code-running plugin from an **untrusted** source is refused (`exit 1`) without `--yes`. Settings writes preserve existing content or refuse, and they are atomic.
- **Usage playbook is mandatory.** Pass exactly one of two flags. `--usage-doc <path>` records the path in the item's `grounded_in`. A repo-relative path travels with the committed manifest. An out-of-repo absolute path is kept, with a warning. `--skip-usage-doc` opts out.

  Neither flag, or both, is a usage error (`exit 2`).

  The `/dummyindex-equip` council writes the playbook.
- `--repo OWNER/NAME` (or a full GitHub URL) names an extra collection repo. The command resolves the target from that repo. Use it when the repo is not in the seed marketplaces.

### `dummyindex context equip status [--root DIR] [--json]`

- It classifies every tracked item. Generated and vendored items are classified by origin hash. The classes are `pristine`, `user-modified`, and `missing`. Marketplace items are classified by whether their `enabledPlugins` key is still set. `pristine` means enabled.

  `missing` means not enabled.

  Each item also shows its version.

### `dummyindex context equip refresh [--root DIR] [--dry-run]`

- It re-renders PRISTINE-and-stale items. It re-baselines them and bumps the minor version. USER_MODIFIED items are skipped forever.

### `dummyindex context equip reset NAME [--root DIR]`

- It restores one generated item to its pristine render. This is the escape hatch. It re-baselines the item and bumps the version.
- Resetting a sourced item restores the template and clears `origin_repo`, `origin_ref` and `marketplace`.

### `dummyindex context equip uninstall [--root DIR] [--dry-run]`

- It removes PRISTINE generated files, the `DUMMYINDEX_EQUIP` hook, and the manifest. USER_MODIFIED files are kept and reported. It also disables any equip-enabled plugins. It drops their marketplaces from `settings.json`. It removes PRISTINE vendored files.

  User-edited vendored copies are kept.

### `dummyindex context equip patch --item NAME --from-file F [--lesson-file F] [--root DIR]`

- It is a sanctioned evolution step. It applies an exact-once old-to-new patch. `F` is `{"old": "...", "new": "..."}`. The patch goes to a generated item. It re-baselines the item and bumps the patch version.
- Why: it lets build-run learnings flow back into generated tooling (`dummyindex-build` calls this post-build) without stomping user edits.

### `dummyindex context equip reuse CAPABILITY_ID [--force] [--root DIR]`

- It copies a stored library specialist from `.context/equipment/library/` into the project. The copy goes to the capability's manifest path. It prints `status=ok|needs-reverify`. It refuses with exit 1 to overwrite a locally edited target. A locally edited target differs from the manifest `origin_hash`.

  Use `--force` to overwrite it anyway.

The command also requires the id to be in the manifest. A successful reuse re-baselines `origin_hash`. `equip apply` and `equip patch` accept `--lesson-file F`. The lesson JSON is validated before anything is written. An invalid file exits 2.

`apply` stores only the specialists it generated or adopted in that run.

  `patch` stores only the patched item. Without that flag, nothing is stored.

### `dummyindex context equip remove NAME [--root DIR] [--delete-file] [--keep-wiring]`

- It drops one item from the manifest. It unwires that item from `settings.json`. `--delete-file` also removes a PRISTINE generated or vendored file from disk. USER_MODIFIED files are kept. `--keep-wiring` leaves the settings entry in place.

### `dummyindex context equip verify <plugin>@<marketplace> [--root DIR]`

- It is a read-only supply-chain check. It re-resolves an installed plugin against its upstream. It reports whether the pinned commit sha still matches. It writes nothing.

### `dummyindex context build --proposal S (--next-wave | --next | --check "<item>" | --skip "<item>" --reason "<why>" | --status) [--route K=V]... [--json]`

- It is the build loop. It is a deterministic state machine over a proposal's `checklist.md`. The `/dummyindex-build` skill orchestrates dispatch. This command drives the state.
- `--route K=V` is repeatable. It uses the same alphabet as `propose`. It overrides the proposal's `"routing"` block for this invocation. Precedence runs from invocation, to proposal, to unset. `--status` reports the resolved routing.

  The `--next` and `--next-wave` payloads carry it too.
- Via tags come in two classes. Agent-named tags fan out as **pinned subagent units**. Such a tag is `— via agent:<name>`, or a bare name that matches an equipped kind-agent entry exactly. Each unit is recorded in a per-item `upgrade_note`. Unknown agent names fail safe as `main-session`, with a warning.

  Genuine tool, skill, and MCP tags stay binding main-session work.
- `checklist.md` can group items under `## Wave N — label` or `## Group N` headings. Items in one wave are mutually independent. You can dispatch them **in parallel**. Waves run strictly in order. Any other heading, such as a plain title, keeps items serial.

  Legacy flat checklists stay unchanged.
- `--next-wave` prints **every** unchecked item in the earliest incomplete wave. It also prints compatibility routing metadata and shared grounding paths. The active skill dispatches the wave through its host. Claude uses the equipment mapping. Codex maps each task to native built-ins.
- `--next` prints one item with the same metadata. Both verbs report an **`equipped`** flag with `--json`. In text mode, they warn when no manifest exists. Claude's build skill stops on that signal. Codex treats it as the expected no-equipment state.

  It continues natively.
- `--check "<item>"` flips an item to `- [x]`. It is idempotent. Use one call per verified item.
- `--skip "<item>" --reason "<why>"` closes an item as `- [~] … — skipped: <why>`. Use it for renegotiated scope. `--reason` is mandatory. The command refuses an already-closed box.
- `--status` reports `done/total` and the resolved model routing (`models:` line). When the build is complete, it prints `dummyindex context reconcile`.

## Managed doc homes — migrate strays + write-guard

Keep internal planning artifacts (plans, specs, design docs, audits) in their managed `.context/` homes (`proposals/<slug>/`, `audits/<slug>/`). They stay out of the user-facing `docs/` tree, instead of leaking into it. One shared classifier backs both a relocation command and a PreToolUse write-guard. The classifier is location-gated.

### `dummyindex context migrate-docs [--root DIR] [--yes] [--force] [--json]`

- It relocates stray planning-doc markdown. Strays leaked under `docs/` in a `plans|specs|proposals|audits` segment. That segment includes `docs/internal/*` and `docs/superpowers/{plans,specs}`. A `*-design.md` file also counts. So does a `YYYY-MM-DD-<name>.md` filename under such a directory.

  The command moves each stray into its managed home.

  The home is `.context/proposals/<slug>/` for `spec.md` or `plan.md`. It is `.context/audits/<slug>/` for `report.md`. The command mints a valid `proposal.json`. Its terminal status is `done`. It has no template checklist, so the GC will not read it as in-flight.
- It is a dry run by default. It lists every stray, grouped by slug and target home, in deterministic sorted order. It moves nothing. `--yes` performs the moves. `--force` fills only *missing* files in an existing home.

  It never clobbers a non-empty `spec.md`, `plan.md`, or `proposal.json`.

  `--json` emits the stable `{dry_run, groups, skipped}` payload.
- It preserves git history. A tracked stray moves with `git mv`, which renames it in the index. An untracked stray moves with `Path.replace` and then `git add`. A non-git tree uses `Path.replace` only. The move is transactional.

  Realpath validation covers the whole plan before any move runs.

  It rejects `..` paths and symlink escapes. No such escape reaches a move. The command never touches source code, and it moves nothing outside `docs/`. See the `playbooks/migrate-stray-docs.md` playbook. Commit the move alone, so `git log --follow` survives.

### `dummyindex context guard-doc-write [--root DIR]`

- It is the **PreToolUse `Write` guard**. It reads the hook JSON on stdin. It denies a `Write` that would create an internal planning doc in an unmanaged location. The denial carries an interpolated reason. The reason names the `.context/` home that the doc belongs in.

  It allows everything else.
- **Fail-open.** It exits 0 on every path. The one exception is an explicit JSON `deny`. The other paths also allow. They include malformed or empty stdin. They include a non-`Write` tool.

  `Edit` and `MultiEdit` can only maintain an existing file.

  They never create a fresh leak.

  They include a missing or out-of-repo `file_path`. They include any internal error, and all of these allow. It **never** returns `exit 2`, which would block the tool. It runs no git or subprocess on the hot path.
- `doc_guard_enabled` gates the guard. It defaults to on everywhere. It engages even before `.context/` exists. A `doc_guard_allow` glob exempts a legitimately published path. For example, `docs/specs/**` is such a glob.

  `hooks install` wires the guard as a managed PreToolUse hook.

## Audit — argue-and-audit panel (`/dummyindex-audit` / `$dummyindex-audit`)

This is an on-demand adversarial review. A free-text description starts a **task-dependent** panel of auditors. The auditors file findings. Then they argue them, for up to 3 rebuttal rounds. The rounds stop early on agreement.

Synthesis then writes a ranked `report.md`.

The CLI is deterministic plumbing. The active-host audit skill orchestrates Claude Task subagents or Codex native `explorer` and `default` subagents. It does **not** require a full `.context/` index.

### `dummyindex context audit start --describe "..." [--scope PATH]... [--mode light|standard|deep] [--model current|opus|sonnet|haiku|fable] [--slug S] [--force] [--root DIR] [--json]`

- It scaffolds `.context/audits/<slug>/`. The scaffold holds `audit.json`, `description.md`, `catalog.json`, and `findings/`. It emits the persona catalog as JSON (`{slug, dir, mode, model, max_rounds, scope, catalog:[...]}`).
- `--describe` is required. `--slug` defaults to a slug derived from the description. `--force` overwrites an existing audit.
- `--model` is required unless config provides one. Claude uses a configured or user-selected Claude label. Codex passes `--model current` explicitly, even when a shared config contains a Claude label. `--mode` defaults to config, else `standard`.
- `--scope PATH` (repeatable) focuses the audit on specific paths.

### `dummyindex context audit show --slug S [--root DIR] [--json]`

- Reports an audit's state: its config, which rebuttal rounds are complete, and whether `report.md` has been written.

### `dummyindex context audit-log --slug S --round N --persona P --status STATE [--note "..."] [--root DIR]`

- Appends a row to `audits/<slug>/_debate-log.json` for debate resumption. `STATE` is `started|complete|failed|skipped`. The skill logs each persona per round, so a re-run skips completed rounds.

## Context-hygiene GC (`/dummyindex-gc` / `$dummyindex-gc`)

This is deterministic plumbing for the commit-throttled hygiene sweep. The GC deletes generated docs. It never archives them. `/dummyindex-gc` on Claude, or `$dummyindex-gc` on Codex, drives the council judgment and user confirmation. These verbs supply the bounded Python.

### `dummyindex context gc status [--json] [--root DIR]`

- It is a read-only sweep. It lists every candidate generated-doc workspace under `proposals/` and `audits/`. Each one shows its deterministic signals: `status:<v>`, `orphan-empty`, `checklist-complete` or `checklist-partial`, `report-written`, `untracked`, and `age-<n>d`. It also shows the commit-throttle state: `commits_since`, `anchor`, `threshold`, `should_signal`, and `anchor_orphaned`. `--json` emits the same payload.

  It surfaces a re-baseline hint when a history rewrite orphans the recorded anchor.

  It exits 0.

### `dummyindex context gc delete --kind proposal|audit (--slug S | --path P) [--yes] [--allow-untracked] [--force-partial] [--root DIR]`

- It removes exactly one doc workspace directory. A guard ladder checks the removal. The ladder runs these checks: slug charset, sentinel rejection, realpath containment, liveness, and recoverability. Without `--yes`, the command is a dry run. It deletes nothing and exits 0.

  With `--yes`, it performs the bounded delete.

It refuses a sentinel such as `_archive` or a leading `_`. It refuses an out-of-charset slug. It refuses an escaping `--path`, and these refusals exit 2. It also refuses an untracked workspace unless `--allow-untracked` is given. An already-absent target is an exit-0 no-op.

The command never deletes source code.

### `dummyindex context gc stamp [--to <sha>] [--root DIR]`

- It advances the committed GC commit anchor in `.context/gc/state.json` to HEAD, or to `--to <sha>`. It resets the commit-throttle counter. Off git, it is a no-op.

### `dummyindex context gc signal [--json] [--root DIR]`

- It is the SessionStart throttle probe. It prints the one-line nudge `N commits since last hygiene sweep — run /dummyindex-gc`. It prints the nudge when `commits_since(anchor) >= threshold`. It also checks that the session has not already signalled. The session ID resolves from `CLAUDE_CODE_SESSION_ID`.

  It always exits 0.

  It stays silent under the threshold, off git, or when already signalled.

## Fleet runs (`dummyindex-fleet` babysitter)

It runs checkpointed, multi-proposal execution. Several proposal-sized units run in parallel, in isolated worktrees. All state is committed under `.context/fleet/run-<id>/`. `RUN-MANIFEST.md` is written first, and `state.json` is written last. Both writes are atomic.

The CLI is tracker-agnostic.

The host produces intake JSON.

### `dummyindex context fleet init --plans SLUG[,SLUG…] | --intake FILE --budget-usd N --max-parallel N [--branch-template TPL] [--ruling KEY=VALUE]... [--root DIR]`

- It scaffolds a run and goes live. Unit member paths freeze at init. They come from intake entries' `paths[]`, or from each proposal's optional `member_files`. If those are absent or empty, init prints a warning. It then schedules that unit conservatively, in serial.

  It refuses a zero-unit run.

  It refuses duplicate slugs. It refuses `--budget-usd <= 0`, `--max-parallel < 1`, and branch templates without `{id}` or `{slug}`. The default branch template is the neutral `{run}/{id}-{slug}`.

### `dummyindex context fleet next [--run DIR] [--json] [--root DIR]`

- It prints the dispatch frontier for the newest `run-*` directory. It lists up to `--max-parallel` pending units, in priority order. It never lists two units whose frozen path sets intersect. It skips gated or blocked units and gives reasons. At or over the budget cap, every response is a `BUDGET-HALT` envelope.

  That envelope carries exact resume steps.

  `--json` adds `"halt": true`. For a valid envelope, it always exits 0. An empty but valid envelope is the anti-stall guarantee. It happens when every unit is gated.

### `dummyindex context fleet checkpoint --unit ID [--status ST] [--wave N] [--gate "Q"] [--note "..."] [--run DIR] [--root DIR]`

- It advances one unit through `pending|planning|building|merging|done|blocked`. `--gate` parks the unit as `gated` on an unanswered question. `next` skips the unit until a later checkpoint answers it with `--status`. Every mutation is a lock-serialized read-modify-write. Each one bumps the state `revision`.

### `dummyindex context fleet spend --unit ID --est-usd X [--adjust] [--run DIR] [--root DIR]`

- It accumulates the budget breaker meter. Negative deltas require `--adjust`. The recorded correction is the only resume path after `BUDGET-HALT`.

### `dummyindex context fleet merge-order [--run DIR] [--json] [--root DIR]`

- It projects the landing order and gives the disjointness rationale. Done units come first. The rest follow in priority order. Each row cites the earlier unit that it must land after, because they share member paths. Otherwise the row marks itself parallel-safe.

### `dummyindex context fleet status [--run DIR] [--json] [--root DIR]`

- It is a read-only run summary. It shows, per unit, the id, slug, status, spend, and gates. It also shows the meter and halt state.
## Self-improvement loop (`/dummyindex-evolve` / `$dummyindex-evolve`)

This is deterministic plumbing for the self-improvement loop. It runs these stages in order: cited evidence, scoped guidance edit, project-test qualification, and adoption or discard. The host authors candidates. The CLI checks exact files, records receipts, and owns recoverable writes. Ordinary project tests leave model improvement unmeasured.

### `dummyindex context evolve harvest [--since YYYY-MM-DD] [--sleep] [--json] [--run NAME] [--root DIR]`

- It collects cited evidence into `<run>/harvest.json`. The evidence covers open audit findings in `audits/<slug>/report.md`. It covers session-memory correction notes. It covers reconcile deltas: drifted features, unassigned new files, and features awaiting enrichment. It covers transcript adoption misses.

  Those misses hold counts and projects-root-relative session slugs only.

  They never hold message content. It also prints flipped predictions from earlier promotes. `--sleep` is the overnight contract. When nothing is new, it exits 0 and writes nothing.

### `dummyindex context evolve diagnose --run NAME --from-file FILE [--json]`

- It validates host-authored candidates. It checks structure, the scope guard, and citation existence. It allows at most 5 candidates, with at most 5 target files each. Valid candidates go into `<run>/candidates.jsonl`. `--candidate N` elsewhere refers to its 0-based line.

  Invalid candidates are rejected with per-line errors.

  Nothing is written.

### `dummyindex context evolve apply --candidate N --run NAME [--tests PATH] [--json]`

- It reads proposed files from `<run>/staged/<N>/<repo-relative-target>`. It runs the same established pytest checks. It runs them against isolated copies of the current baseline and the exact candidate. `--tests PATH` selects an existing check. Otherwise, it uses target-matching tests.

  Missing checks are blocked.

  The receipt binds to the candidate, the baseline, the verification inputs, and the execution settings. Passing project checks does not establish measured model improvement.

### `dummyindex context evolve promote --candidate N --run NAME [--override "REASON"]`

- It adopts only the measured content. It does so while its baseline and verification identity still match. Backups and a recoverable journal protect multi-file changes. A blocked verdict needs a recorded manual-adoption override. The verdict remains unmeasured.

  Failed checks and stale receipts cannot be overridden.

### `dummyindex context evolve rollback|discard --candidate N --run NAME`

- `rollback` restores the backed-up originals of a promoted candidate. `discard` drops the staged copy without adopting anything. Each command appends exactly one transition line to `evolution.jsonl`. Every harvest, diagnosis, gate, promote, rollback, and discard gets one line. The lines form a committed, append-only decision history.

## Doc reorg (destructive, part of the normal pipeline; `/dummyindex --reorg-docs` runs it alone)

### `dummyindex context doc-reorg guard|list|backup|restore [path] [--root DIR] [--json] [--from DIR]`

- It is a safety net for the destructive in-place doc reorg. The rewrites happen in the session through `Edit`. Each file needs a confirm.
- `guard` exits 0 if the working tree is clean, else 1 (the hard gate).
- `list` shows the doc files in scope. `backup` copies them to a timestamped backup directory. It **re-asserts the clean tree itself**. It exits 1 on a dirty or non-git tree. So an always-on reorg can never snapshot a dirty tree and poison the undo path.

  `restore --from <dir>` puts a backup back.

  Restore is never gated. Restoring is the recovery path.

## Token usage

### `dummyindex usage [chat|daily|session|monthly|blocks]`

- It reads Claude Code transcripts to report token usage. It has no LLM cost.
- It is not a Codex session reporter. In Codex, use native `/status` for the current context and session. Use `/usage` for account usage.
- `chat` is the default. It reports the current session. It shows the context window now, from the main thread, and it matches `/context`. It also shows deduplicated cumulative totals. A subagents column sums any Task or subagent transcripts.

  The `/tokens` slash command runs this view.
- `daily`, `session`, and `monthly` show token totals. The totals aggregate across every project. They group by day, session, or month.
- `blocks` shows usage grouped into billing blocks across every project.

## Status — read-only overview

### `dummyindex context status [path] [--root DIR] [--json]`

- It is a single read-only glance. It composes the existing per-domain read helpers. It **never mutates** anything. The top-level alias `dummyindex status` also works. Models reach for that spelling first.
- It reports these items. It reports whether `.context/` is present and enriched. It compares the `.context` version stamp with the running CLI, and it flags skew. It shows the commit-anchored drift one-liner: drifted, unassigned, awaiting-enrichment, and removed. It shows the equipment item count and schema version.

  It shows each proposal's `done/total`.

  It also shows session-memory presence.
- It exits `0`, even on an un-indexed repo. It reports "not initialized" instead of erroring. So it is safe to run anywhere.

### `dummyindex context wire [path] [--root DIR] [--yes]`

- It is the **interactive escalation surface** for the `wired` config list. The headless reconciler, run by `install` or `ingest`, only **classifies and reports** needs-user entries. `wire` resolves them by prompting.
- It re-classifies every `config.wired` entry **read-only**. It uses the same shared helper that `status` uses. The classes are satisfied, acted, and needs-user. Then it resolves each entry that is not already satisfied. Each declared but absent wireable plugin, the *acted* class, is **prompted** before wiring.

  A `kind: skill` entry appears as a manual notice.

  It is **never** auto-wired, because no skill-enable primitive exists. A malformed plugin target is reported and skipped.
- `--yes` auto-affirms every plugin prompt. This is the automation path, and it makes no `input` call. A non-TTY stdin without `--yes` never blocks. It prints the needs-user list and exits `0`. The headless reconciler stays non-interactive.

  This is the **only** surface that prompts.

### `dummyindex context statusline [path] [--root DIR]`

- It prints the cached `.context/` freshness badge for a shell `statusLine`. The badge looks like `[ctx ✓]` or `[ctx: E edited · A anchored]`. It is the **cold-path** fallback for the per-prompt hot path. The shipped `statusline.sh` and `statusline.ps1` `cat` the same gitignored cache directly.
- It reads the pre-computed badge cache. The `plan-update` SessionStart path writes that cache. It **never recomputes drift**.
- A missing `.context/`, a missing or malformed cache, or **any** error gives empty stdout and `exit 0`. So it can never crash a user's shell.

### `dummyindex context drift-ack [path] [--root DIR] (--feature ID [--path REL] [--reason TEXT] | --list | --clear)`

- It acknowledges drift rows as false positives for this machine or workflow. It appends `{feature_id, path, acked_sha, reason?, ts}` entries to the gitignored `.context/cache/drift-acks.json`. A suppressed row returns the moment the file's bytes change. This is ack auto-expiry.
- With `--feature` alone, every currently drifting file of that feature is acked. `--path` scopes the ack to one file. `--reason` annotates the entry.
- `--list` prints recorded acks. You can filter them by `--feature`. `--clear` drops them all. The modes are mutually exclusive.
- Off-git repos use content sha256 instead of git blob shas. Suppression matching lives in the SessionStart drift scan (`plan-update`).

## What is NOT a CLI command

- "Run the council" is the **skill's** job. The CLI does not dispatch agents.
- "Enrich PROJECT.md" is a markdown procedure. The agent uses `Write`.
- "Decide if a flow is trivial" is the dev agent's call.

Rule of thumb: the CLI moves bytes around atomically. Everything that requires judgment is in markdown.

A human never runs the CLI. The CLI is the agent's deterministic backbone. The skill and council invoke it. A human's interface is slash commands inside Claude Code, or `$skill` mentions in Codex. The one exception is the one-time `install` bootstrap.
