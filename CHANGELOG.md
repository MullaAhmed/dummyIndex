# Changelog

## [Unreleased]

## 0.15.2 — non-destructive commit-anchored rebuild

**Fixed: `rebuild --changed` no longer re-clusters or re-stubs an enriched index**

- Previously any source change made `rebuild --changed` fall through to a
  full `build_all`, which re-ran deterministic community detection,
  overwrote `features/INDEX.json` with generic `community-N` stubs
  (orphaning the council's curated feature folders), regenerated
  `tree.json` (losing enriched abstracts), and re-stubbed every
  `features/<id>/spec.md`. On an enriched repo this was silent data loss.
- `rebuild --changed` now detects a curated/enriched index (any feature
  whose `feature_id` is not `community-*`, or whose `confidence` is
  `INFERRED`) and takes a **non-destructive** path: it refreshes only the
  purely-deterministic, enrichment-free artefacts (`map/files.json`,
  `map/symbols.json`, `conventions/naming.{json,md}`,
  `source-docs/INDEX.{json,md}`, `features/symbol-graph.json`) and never
  re-clusters, never regenerates `tree.json`, and never overwrites a
  per-feature `spec.md` or the council-authored `conventions/*.md`. It then
  prints a reconcile report (drifted features + unassigned new files) and a
  pointer to `/dummyindex --recouncil`.
- A fresh deterministic-only index (all `community-*` / `EXTRACTED`) has
  nothing enriched to lose, so it still full-builds on `--changed`.

**Added**

- `meta.json` records `indexed_commit` — the git HEAD SHA the index was
  built against (`null`/absent off-git). Additive and optional; no schema
  bump, so older installs still read new indexes and vice-versa.
- Git-delta foundation: `context/build/git_delta.py` (`head_commit`,
  `changed_paths` — added/modified/removed since an anchor, working tree
  and untracked files included; degrades to `None`, never raises) and
  `context/build/reconcile.py` (`compute_reconcile_report` — read-only
  mapping of changed/removed paths to owning features and net-new paths to
  unassigned). Detection only; never writes, never decides taxonomy.
- `rebuild --full` flag forces the old full re-cluster regardless,
  printing a prominent warning that it discards curated taxonomy +
  enrichment. The destructive re-cluster is now gated behind `--full` (or a
  fresh `ingest`); the non-git / missing-anchor fallback still applies the
  enriched guard.
- Atomic placement ops — `context scaffold-feature` (create a new
  `features/<id>/` for net-new files: `feature.json` with members derived
  from `map/symbols.json`, deterministic `spec.md` stub, `docs.md`, then
  appended to `INDEX.json` + regenerated `INDEX.md`/`graph.{json,html}`) and
  `context assign-files` (add files to an existing feature, recompute
  members, refresh counts/graph, preserve the enriched `spec.md`/`plan.md`).
  Both are deterministic, validate-before-write atomic, reject reserved
  `community-*` ids / files outside the repo, and **never re-cluster** — the
  foundation for council-driven incremental placement (Phase 3) that folds
  the reconcile report's unassigned files into the curated taxonomy.

## 0.15.1 — submodule/worktree `.git` support + scratch-file hygiene (2026-06-08)

**Fixed: equip's generated `{proj}-reviewer` / `{proj}-verify` carried a `{stack}-` identifier that broke dispatch-by-name**

- `catalog.py` names the manifest item, the `subagent_type`, and the file
  path with the project slug (e.g. `backend-reviewer`,
  `backend-verify/SKILL.md`), but the templates rendered their frontmatter
  `name:` + H1 from `{{stack}}` only — so a repo with stack `python` and
  project `backend` shipped `backend-reviewer.md` carrying `name:
  python-reviewer` and `backend-verify/SKILL.md` carrying `name:
  python-verify`. Claude Code resolves agents/skills by their frontmatter
  `name:`, so the manifest's `subagent_type: backend-reviewer` (emitted by
  `build --next`) did not resolve and dispatch fell back.
- `render_template` gains a `{{proj}}` slot; the reviewer agent and verify
  skill now render their `name:` + H1 from `{{proj}}` (their prose still
  describes the real `{{stack}}`). The implementer/tester keep their
  `{{stack}}-` identifiers by design. The three-way identity — manifest
  `subagent_type` == rendered frontmatter `name` == filename stem — now
  holds for the standard generated set.
- The implementer's verify hand-off cross-reference is corrected from
  `{{stack}}-verify` to `{{proj}}-verify` (was a dangling pointer to a
  skill that does not exist under that name).
- The detected format command is now baked into the implementer agent via a
  new `{{format_command}}` slot (same `(no command detected …)` fallback as
  the other toolchain slots), so the implementer runs the repo's real
  formatter after a change. No version bump.

**Fixed: build-loop task→agent matcher routed nearly every implementation task to `general-purpose`**

- The build loop mapped a checklist item to an equipment agent by *literal*
  token overlap between the item text and each item's `capabilities` +
  `name` tokens. But capabilities are single abstract words (`implement`,
  `test`, `review`), while a real implementation task describes *what* to
  build and never says "implement" — so e.g. `app/core/mcp/server.py —
  build_mcp_server constructs FastMCP(…) and registers tools + resources`
  scored 0 against a `python-implementer` (capabilities `["implement"]`) and
  fell back to `general-purpose`. On a correctly equipped repo, essentially
  every implementation task missed its tuned agent.
- The matcher now expands each capability through a keyword **lexicon**
  (keyed off the `Capability` enum, so the capability alphabet stays
  single-source) before scoring — `implement` → `build`/`construct`/
  `register`/`module`/`server`/… — and **defaults to the implement-capable
  agent when an equipped repo's task matches no specialist**. The
  `general-purpose` fallback now fires only when the manifest is empty, or
  has items but no implement-capable one. Deterministic, stdlib-only.

**Fixed: recognise submodule/worktree `.git` files as valid repos**

- dummyindex assumed `.git` is always a directory. In git submodules and
  worktrees it's a *file* containing a `gitdir: <path>` pointer, so
  `install` printed "skipped project init" for a perfectly valid submodule
  (e.g. a backend submodule whose `.git` is a 32-byte pointer file) and
  `context preflight` reported `is_git_repo: false`.
- New pure-filesystem helpers `is_git_repo` / `resolve_git_dir` in
  `pipeline/io/git.py` (no subprocess): a repo is a `.git/` directory *or*
  a `.git` file whose first line starts with `gitdir:`. `resolve_git_dir`
  parses the pointer, resolves relative paths against the repo root, and
  follows a worktree's `commondir` to the shared git dir (where `hooks/`
  live). Malformed `.git` files are treated as not-a-repo, never raised.
- Switched install-time auto-init (`__main__`), `context preflight`
  inventory, and the legacy `git post-commit` scrub (`context hooks`) to
  the helpers. The submodule post-commit scrub now finds the hook under the
  superproject's `.git/modules/<name>/hooks` instead of silently missing it.

**Fixed: internal scratch/log artefacts no longer leak into commits**

- The enrich-plan work-list (a ~384 KB transient) moved out of the
  `.context/` root into `.context/cache/_enrich_plan.json`, where it sits
  beside the other regenerated local artefacts instead of next to committed
  docs.
- The managed `.context/.gitignore` now covers the internal scratch/log
  artefacts as bare filenames (matched at any depth, so per-feature subdirs
  are caught): `_enrich_plan.json`, `_structural-plan.json`,
  `_council-log.json`, and `_reality-check.{json,md}` — in addition to the
  existing `cache/` and `_doc_backups/`.
- The gitignore merge logic now *upgrades* an existing `.context/.gitignore`
  on rebuild: it appends only the managed patterns that are missing
  (preserving user-added lines) instead of short-circuiting the moment it
  saw `cache/`. Repos indexed by 0.15.0 pick up the new patterns on their
  next rebuild.

**Changed: plan auto-equips; build warns instead of silently falling back**

- `/dummyindex-plan` now **auto-equips** the project-tuned toolkit for the
  new proposal as its final step (`dummyindex context equip apply
  --for-proposal <slug>`, deterministic — no Task dispatch). Because
  `equip apply` is additive, never-clobber, and origin-hash baselined,
  running it on an already-equipped repo is safe and idempotent. The toolkit
  now exists by build time without a manual `/dummyindex-equip` step.
- `dummyindex context build --proposal S --next` exposes a new **`equipped`**
  flag (true iff `.context/equipment.json` exists and parsed to a manifest
  with ≥1 item) in its `--json` payload, and prints a prominent
  not-equipped warning to **stderr** in the human `--next` output when the
  repo has no equipment manifest at all. The existing `fallback` key is
  unchanged (back-compat), and the per-item `general-purpose` fallback on an
  equipped repo stays silent — only the *not-equipped* case warns.
- `/dummyindex-build` now **halts and warns** on an unequipped repo (no
  `equipment.json`), recommending `/dummyindex-equip` (or offering to equip
  for the user), instead of silently dispatching `general-purpose` for the
  whole build. A per-item `general-purpose` fallback on an equipped repo is
  still normal and silent.
- Docs corrected to match reality: **setup** builds `.context/` + hooks (+
  the CLAUDE.md block) and no longer claims to equip; **plan** auto-equips;
  **build** drives the equipped agents and warns if unequipped;
  `/dummyindex-equip` stays documented as the standalone (re)equip/evolve
  path. (README, the plan/build skill docs, `skill.md`, and
  `docs/guide/07-cli.md` + `09-lifecycle.md`.)

## 0.15.0 — session memory + the grounded build loop (2026-06-06)

**Added: session-memory subsystem (`/dummyindex-remember`)**

- Markdown-first cross-session memory at `.context/session-memory/` (tiers
  `now.md` → `recent.md` → `archive.md`, plus `core-memories.md`). Seeded by
  `ingest`, never regenerated, invisible to drift detection (regression-tested).
- New CLI `dummyindex context memory session-start|roll|init`: the SessionStart
  hook (folded into the existing sentinel entry as a second command) injects a
  HANDOFF + MEMORY block; `roll` relocates dated entries down the tiers,
  idempotently. Capture is one agent-written summary per save — no PostToolUse,
  no background LLM. Suppresses itself when the `remember` plugin's `.remember/`
  is present, so the two never double-inject.
- Ships as its own top-level skill (`/dummyindex-remember`), installed beside
  `/dummyindex`.

**Added: the build loop — plan → equip → execute (3 sibling skills)**

- dummyindex stays the spine (it never writes production code): it plans,
  equips `.context/`-grounded tooling into `.claude/`, and orchestrates; the
  generated tooling + dispatched agents do the writing. Agent dispatch is
  always skill-layer — the CLI only emits pointers.
- `/dummyindex-plan` → `dummyindex context propose`: NL feature request →
  consistency-checked `.context/proposals/<slug>/` (`proposal.json` + `spec.md`
  / `plan.md` / `checklist.md`), with a deterministic consistency scan (reuses
  `query`) citing related features + conventions.
- `/dummyindex-build` → `dummyindex context build --proposal S
  (--next|--check|--status)`: drives the proposal's checklist (verify-before-
  tick), maps each task to equipment by capability (`general-purpose`
  fallback), emits the `subagent_type` to dispatch, and closes the loop with
  `rebuild --changed`. Post-build learning step (Hermes-style triggers:
  complex-task success / error→working-path / user correction) feeds
  improvements back via `equip patch`.

**Added: Equip v2 — codified, evolving toolkit engine (`/dummyindex-equip`)**

- `dummyindex context equip` is now a full lifecycle tool:
  `apply | status | refresh | reset NAME | uninstall | patch` (+ `--dry-run`,
  `--json`, `--for-proposal S`). All policy is deterministic Python under
  `context/domains/equip/` (detect → catalog → render | adopt → apply →
  manifest v2).
- Toolchain detection: stack, frameworks, and runnable test / lint / typecheck
  / format commands (uv- and npx-aware) baked into the generated tooling.
- Standard generated set: `<stack>-implementer`, `<stack>-tester`,
  `<proj>-reviewer` agents + `<proj>-verify` skill — versioned frontmatter,
  conventions-grounded, sentinel-marked.
- Adopt-existing: project `.claude/agents/` + the dev-pick specialist registry
  recorded as `installed` manifest items with `subagent_type` for dispatch.
- Evolution mechanics (Hermes-derived): per-item **origin-hash baselines**
  (pristine / user-modified / missing — user edits are never stomped),
  **evolved-item protection** (CLI-sanctioned patches survive apply/refresh;
  only `reset` discards them), and the **patch seam** (`equip patch --item N
  --from-file F`: exact-once old/new, re-baseline, patch-version bump, artifact
  frontmatter synced to the manifest version).
- The detected formatter's PostToolUse hook is now actually wired into
  `.claude/settings.json` under a per-event sentinel
  (`DUMMYINDEX_EQUIP:<event>`), additively and preserve-or-refuse; legacy
  unsuffixed sentinels are scrubbed on upgrade. Shared settings machinery
  extracted to `context/claude_settings.py` (consumed by the drift hook too,
  behavior unchanged).
- `equipment.json` schema v2 (`subagent_type` / `version` / `origin_hash`;
  v1 manifests still load). New `Capability` enum for the persisted
  capability alphabet.

**Added: MCP wiring (Context7 + Sequential Thinking + GitHub)**

- Council procedures wire three MCP servers when the runtime exposes them —
  namespace-tolerant matching (server *family*, not one exact prefix), with
  graceful single-shot fallback so a missing server never fails a run.
  Protocols in `council/55-context7.md` + `council/56-github.md`.

**Removed: Objective-C extractor**

- The objc extractor's call-resolution pass matched tree-sitter node types
  (`selector` / `keyword_argument_list`) the installed grammar never produces, so
  it emitted **zero `calls` edges** for any Objective-C file (verified
  empirically; rust/go/julia were unaffected). Removed it wholesale rather than
  fix a language nobody relied on: the extractor is gone, `.m`/`.mm` are dropped
  from dispatch/detection/the language map, and the `tree-sitter-objc` dependency
  is removed. `.m`/`.mm` files now fall through as untracked. Tree-sitter language
  support is now 20 grammars.

**Added: skill wiring for `query` + tree enrichment**

- `dummyindex context query` is surfaced in the retrieval flow (skill markdown +
  the generated `HOW_TO_USE.md`) as a deterministic, ranked-shortlist fast-path —
  a hint for which feature(s) to open, not a replacement for the tree walk.
- `enrich-plan` / `enrich-apply` are wired into the skill as **Phase 4.5 — Tree
  enrichment**: they fill `tree.json` node abstracts (`EXTRACTED` stubs →
  `INFERRED`) so future-session retrieval reads real prose. Mode-gated; procedure
  in `council/52-tree-enrich.md`.

**Cleanup**

- Removed dead code: `pipeline/enums.py` `NodeKind` / `EdgeRelation` /
  `HIERARCHY_RELATIONS` / `INFERABLE_LEVELS` / `ConfidenceLevel.PINNED`; the unused
  `LanguageConfig.function_label_parens` / `extra_walk_fn` knobs; and
  `extract/_common.py:_resolve_name`. Fixed `_StructureIgnoreMatcher._pattern_hits`
  falling through to an implicit `None`.

**Docs**

- Standardised `docs/` + the shipped skill markdown on one `NN-topic.md` naming
  convention with uniform `# NN — Title` headers, added a `docs/README.md` index,
  and synced `reference/01-conventions.md` + the briefs with the code changes
  above. Top-level `--help` now lists every `context` subcommand.

## 0.14.1 — Python 3.10 fix + release hardening (2026-06-05)

**Fix: restore Python 3.10 support**

- `context/domains/dev_pick.py` and `context/domains/doc_reorg/enums.py` used
  `enum.StrEnum` (3.11+), so `import` crashed on Python 3.10 — the floor declared
  in `requires-python`. Switched both to the repo's `(str, Enum)` idiom (the same
  one `usage/enums.py` already documents). 0.14.0 shipped broken for 3.10
  installers; 0.14.1 is the corrected release.

**CI: only tested, release-gated artifacts reach PyPI**

- `publish.yml` now runs the full test matrix (3.10 + 3.12) before building, so a
  release that fails tests can never be published again — the root cause of the
  broken 0.14.0, whose publish step never ran the suite. Publishing now triggers
  on a GitHub Release / manual dispatch only (not every push to `main`) and passes
  `skip-existing` so a re-run never 400s on an already-published version.

**`dummyindex usage` — token reporting + bundled `/tokens` command**

- New stdlib-only `usage/` domain reads Claude Code transcripts under
  `~/.claude/projects/` and reports token counts:
  `dummyindex usage [chat|daily|session|monthly|blocks]`.
  - `chat` (default) — the current session: context window now (matches
    `/context`) with a percentage of the inferred context tier, session
    start + duration, and deduplicated cumulative totals broken down
    **per model**, with the subagent portion summarised.
  - `daily` / `session` / `monthly` / `blocks` — aggregate every project;
    `blocks` are 5-hour billing-style windows. Token-only (no USD).
- Turns are deduplicated by `(message.id|requestId)` — Claude Code rewrites
  the same assistant turn across lines, so naive summing roughly doubles the
  cumulative count. `<synthetic>` placeholder turns are excluded; subagent
  turns are attributed to their parent session.
- `install` now drops a bundled `/tokens` slash command into
  `<scope>/.claude/commands/` (removed on `uninstall`); `/tokens` runs
  `dummyindex usage`.

## 0.14.0 — Spec-kit-shaped pipeline + stack-specialist dev + onboarding (2026-05-27)

The v0.13 "five parallel personas + chairman synthesis" council is replaced
by a sequential, [spec-kit](https://github.com/github/spec-kit)-shaped pipeline
where each artifact has one author and one job. Per-feature docs collapse from
six overlapping essays to three layered docs, personas collapse from six to
three role classes, and a first-run onboarding flow captures council
preferences into a committed `.context/config.json`.

**Artifact reshape**

- Each feature now gets `spec.md` (intent / contracts / behavior — the entry
  point), `plan.md` (implementation), and `concerns.md` (risks). The old
  `README.md` / `architecture.md` / `implementation.md` / `data-model.md` /
  `security.md` / `product.md` set is retired.
- Transition-safe: drift detection, the query reader, and the source-docs
  catalog accept both the new and legacy doc names for one release; only the
  deterministic scaffold switches outright (writes `spec.md`, not `README.md`).
- Reality-check now validates `plan.md` + `concerns.md` (`spec.md` is
  intent-level and not line-checked).

**Sequential pipeline + persona collapse**

- `backbone → /specify (dev) → /plan (architect) → /critique (critics)`.
- Three role classes: a parameterised stack-specialist **dev** (FastAPI /
  Django / Spring / Node / frontend / data / AI / generic), an **architect**
  (structural-review pre-stage + per-feature `plan.md` revision), and
  concerns-only **critics** (database / security / product). The chairman and
  the standalone senior-developer persona are retired.
- New audit trail: `01-dev-draft.md`, `02-architect-notes.md`, `10-critiques.md`.
- Mode-gated critique: `light` skips it, `standard` runs one relevant critic,
  `deep` runs all relevant critics with cross-review.

**New CLI**

- `dummyindex context dev-pick --feature <id>` — deterministic, first-match
  stack-author picker; prints `{persona_id, subagent_type, framework}` JSON.
  `subagent_type` values are the exact global Claude agent names.
- `dummyindex context onboard [--defaults] --scope --mode --model
  [--hook|--no-hook] [--doc PATH]...` — persists onboarding choices. The model
  is required (never silently defaulted); `--defaults` writes the recommended
  baseline (`sonnet-4.6`).
- `dummyindex context config show` — prints the resolved `.context/config.json`.
- `dummyindex install --no-onboarding --defaults` — writes a default
  `config.json` during CI auto-init (never clobbers an existing one).

**Onboarding**

- First `/dummyindex` on a repo with no `.context/config.json` (including a
  v0.13.x upgrade) triggers a 5-question setup (scope, mode, model,
  auto-refresh hook, external docs) via the skill's `AskUserQuestion` flow,
  persisted to a committed `config.json` (choices only — never API keys).
  `/dummyindex --reconfigure` re-runs it. `config.json` carries a
  `schema_version` for forward migration.

**Skill**

- New `council/20-specify.md`, `30-plan.md`, `40-critique.md`,
  `05-onboarding.md`; new `agents/dev.md`, `critic-database.md`,
  `critic-security.md`, `critic-product.md`. Retired the stage1/2/3 markdowns
  and the chairman / senior-developer / database-engineer / security-analyst /
  product-manager persona files. `retrieval/` tree-walk and the conventions
  fan-out repointed to the new docs and personas.

## 0.13.5 — SessionStart drift hook replaces shell-side auto-refresh (2026-05-26)

The pre-0.13.5 install set up three event-driven hooks — `git post-commit`,
Claude Code `PostToolUse`, and Claude Code `SessionStart` — all of which
fired `dummyindex context rebuild --changed` in the background. That
deterministic-only refresh re-ran feature scaffolding on every edit,
producing raw `community-N/` folders next to council-enriched features,
overwriting the features `INDEX.json`, and stamping placeholder
`flow-NNN.md` files containing literal "_The `/dummyindex` skill will
rewrite this file with a plain-language narrative._" text. The skill
never runs from a shell hook, so the placeholders accumulated forever.

The fix flips the model: hooks no longer rebuild the backbone at all.
Instead, a single `SessionStart` hook surfaces drift, and the running
Claude session — which has the full context of *what* changed and *why*
— updates `.context/features/<id>/*.md` in-place.

**What changed**

- **New CLI: `dummyindex context plan-update [--root DIR]`.** Prints a
  markdown drift report to stdout: one line per feature whose source
  files have been edited since the matching `.context/features/<id>/`
  docs were last touched. Empty stdout when nothing is stale.
  Claude Code's `SessionStart` hook accepts plain stdout as
  `additionalContext`, so no JSON wrapping is needed.
- **New module: `dummyindex.context.drift`.** Implements the mtime-based
  comparison: a source file is "drifting" when its mtime is greater
  than the max mtime across that feature's prose docs
  (`architecture.md`, `data-model.md`, `implementation.md`,
  `product.md`, `security.md`, `supporting.md`). Heuristic decay: when
  the agent edits a feature doc, its mtime advances and the drift
  signal naturally goes quiet. No explicit `mark-updated` command is
  needed — file mtimes are the stamp.
- **`dummyindex.context.hooks` refactored to install only `SessionStart`.**
  The `git post-commit` template and the `PostToolUse` hook body are
  deleted. The new `SessionStart` body shells out to
  `dummyindex context plan-update`.
- **Upgrade scrub.** Running `dummyindex context hooks install` (or
  `dummyindex install` against a git repo, which calls it transitively)
  now removes any legacy `git post-commit` script we previously
  installed and any sentinel-bearing `PostToolUse` entry under
  `.claude/settings.json`. User-authored hooks (no sentinel) are left
  untouched.
- **`HookStatus` shape changed.** Only `claude_session_start` remains;
  `git_post_commit` and `claude_post_tool_use` were removed.
- **Docs:** README "Always-on auto-refresh" section retitled
  "SessionStart drift hook" with the new model explained. SKILL.md
  description, Phase 1 outputs, and final report step all updated.
  CLI usage text now lists `plan-update` and rewords the `hooks` and
  `check` entries.

**Upgrade notes**

- Run `dummyindex context hooks install` (or just `dummyindex install
  --dir <repo>`) once per project. The install will remove the legacy
  post-commit + PostToolUse entries automatically.
- If your repo's `.context/features/` has accumulated orphan
  `community-N/` folders or a clobbered `INDEX.json` from the old
  loop, the cleanest fix is `rm -rf .context && /dummyindex` — this
  PR does not auto-clean existing damage to avoid touching anything
  you may have hand-edited.
- Related bug spotted but NOT fixed in this release: `rename_feature`
  doesn't stamp `source_community_id` into the renamed `feature.json`,
  so a fresh `/dummyindex --refresh` will still produce orphan
  community folders next to renamed ones. Scheduled for its own PR.

**Tests**

19 new tests covering the drift detector and the `plan-update` CLI
(empty repo, missing `.context/`, source-newer-than-doc, doc-newer
clears drift, any-doc-suppresses-drift, one-source-two-features, decay
after a doc edit). Hook tests rewritten for the single-hook shape,
plus three legacy-scrub tests confirming the upgrade path. 373 tests
total, all passing.

## 0.13.4 — `install` auto-inits the current project (2026-05-26)

First-run friction fix: `dummyindex install` now also bootstraps the
project in one command when run from a git repo. No more separate
`install` then `ingest` then `hooks install` dance — the common case
just works.

**What changed in `install`**

After the skill copy (existing behavior, unchanged), `install` now
resolves a project candidate (`--dir PATH` if given, else CWD) and
checks for `.git/`. If present, it also runs the full project init:

- builds `.context/` (deterministic backbone via `build_all`)
- writes the managed CLAUDE.md block (`bootstrap=True`)
- installs the three auto-refresh hooks (git post-commit + Claude
  PostToolUse + Claude SessionStart)

If the candidate is not a git repo, the install prints a one-line
"skipped project init" note explaining how to run `ingest` later from
inside a project directory. Skill-only installs (e.g. `~/`) still work
silently, just without the auto-init step.

**New flag**: `--skill-only` suppresses the auto-init step when you
want to re-run the installer without touching project state (for
example, to refresh just the global skill files after upgrading).

**Why now:** the v0.13.x docs told users to run `install` then
`ingest`, but most users expected `install` to do everything. The split
existed because `install` is conceptually a global skill registration
while `ingest` is per-project — but in practice 99% of `install` runs
happen from inside the project the user wants indexed, so making
`install` notice that and do the right thing eliminates a class of
"why is `.context/` empty?" questions.

**Backwards compatibility:** the existing positional / `--dir` / `--scope`
flags are unchanged; the new auto-init behavior is purely additive. The
`_parse_install_args` return tuple grew a third element (`skill_only`);
callers that imported it directly (only `__main__.main`, plus tests)
were updated.

3 new tests added (354 total, all passing): auto-init happens when
`.git/` is present, `--skill-only` suppresses it, and the friendly
skip message fires when no `.git/` is present.

## 0.13.3 — drop legacy `dummyindex-out/` references (2026-05-26)

`.context/` is now the only output path the codebase knows about. The
`dummyindex-out/` paths were a graphify v1 carryover that no shipping
code path actually produced — the v2 runner already overrode every
default — but several modules still named it as their fallback. That
created two real problems: docs and defaults pointed at a folder that
never existed in user repos, and a leftover graphify-era directory
caused subtle skip-list behavior nobody could explain.

**Code changes**
- `pipeline/io/cache.py` — `cache_dir()` default moves from
  `<root>/dummyindex-out/cache/` to `<root>/.context/cache/`. The
  `DUMMYINDEX_CACHE_DIR` env-var override is unchanged and still wins
  over the default.
- `pipeline/io/detect.py` — `detect()`'s memory and converted-sidecar
  directories migrated from `<root>/dummyindex-out/{memory,converted}/`
  to `<root>/.context/{memory,converted}/`. Removed `"dummyindex-out"`
  from the `_SKIP_DIRS` set.
- `pipeline/io/detect.py` — deleted dead helpers `load_manifest`,
  `save_manifest`, `detect_incremental`, and the `_MANIFEST_PATH`
  constant (`dummyindex-out/manifest.json`). Zero callers anywhere in
  the package or tests; vestigial from the v1 `--update` mode that was
  retired before v2 shipped.
- `runtime/security.py` — deleted `validate_graph_path` (no callers,
  not in any `__all__`, only referenced the `dummyindex-out` path
  convention).
- `context/build/runner.py` and `pipeline/build/_common.py` — removed
  `"dummyindex-out"` from `_DOC_WALK_SKIP_DIRS` and
  `_STRUCTURE_SKIP_DIRS` respectively.
- `pipeline/extract/__init__.py` — docstring updated.

**Test changes**
- Dropped three regression guards that asserted
  `dummyindex-out/` was not created. The positive assertions that
  output lives under `.context/` (cache-dir, gitignore content, env-var
  restoration) all remain. 350 tests still pass.

**Upgrade notes**
- Callers that rely on the default cache path now write to
  `<root>/.context/cache/`. Set `DUMMYINDEX_CACHE_DIR` to opt out.
- Files previously filed into `<root>/dummyindex-out/memory/` are no
  longer picked up by `detect()`. Move them to `<root>/.context/memory/`.
- A leftover `dummyindex-out/` directory in someone's repo is no
  longer in the built-in skip lists, so `ingest` will descend into it.
  Add it to `.gitignore` or `.dummyindexignore` if you want it excluded.
- `validate_graph_path` is gone. If you were importing it from
  `dummyindex.runtime.security`, switch to a project-local equivalent
  — it was never on the public surface but the symbol was reachable.

## 0.13.2 — consolidation-pass guards (2026-05-26)

Three guards on the trivial-feature consolidation pass to stop the
failure mode where 21 parser-artifact "features" got bulk-merged into
unrelated parents under an invented `noise-absorbed` section, with no
chairman audit trail.

1. **`merge_feature` rejects unknown `--as-section` names.** A new
   `_VALID_MERGE_SECTIONS` allowlist in
   `dummyindex/context/domains/features/_constants.py` (currently
   `{"supporting"}`) is checked at the start of the merge. Ad-hoc
   section names like `noise-absorbed` are rejected before any I/O.
2. **`merge_feature` auto-appends a stage-0 chairman entry** to the
   target's `council/_council-log.json`. The audit trail can no longer
   be skipped by forgetting to run `council-log` after the merge. New
   optional `--note` flag on the CLI lets the chairman pass an explicit
   rationale; otherwise a default `merged-from:<id>` is generated.
   Backwards-compatible: existing callers that don't pass `note` keep
   working.
3. **`scaffold_features` drops empty-`__init__.py` communities** at
   ingest time. A new `_is_parser_artifact` helper in
   `builder.py` filters out Leiden communities whose only files are
   `__init__.py` and which have no entry points. Real package APIs
   that define callables in `__init__.py` are kept. This stops the
   upstream noise from ever reaching the trivial filter.

**Why:** the previous consolidation pass on an external project produced
five `noise-absorbed.md` files (a section name not in the spec), 21
features merged into 5 catch-all parents with no real call-graph
relationship to most of the source files, and no Chairman entries in
the council log for any of those decisions. The spec required Chairman
per feature, valid section names, and per-decision logging — but
nothing in the code enforced any of it. These three guards close the
gaps at the API boundary.

The procedure (`dummyindex/skills/council/filter-trivial.md`) is updated
to match: explicit "one Chairman per feature, no batching" language,
Outcome C requires recording the parent-check in the council-log note,
and the auto-log behavior of `features-merge` is documented so the
procedure and code can't drift.

5 new tests added (350 total, all passing).

## 0.13.1 — respect .gitignore by default (2026-05-26)

`dummyindex ingest` now reads `.gitignore` in addition to
`.dummyindexignore` / `.codeindexignore`. Both files are checked at the
scan root and every ancestor directory up to the git repo root, layered
together (gitignore first, dummyindex-specific last).

**Why:** running on a real repo with vendored code surfaced the bug —
364 of 405 indexed files were vendored libpostal + ad-hoc scripts
because dummyindex didn't read the project's existing `.gitignore`.
Users had to write a separate `.dummyindexignore` listing the same
patterns. With this change, the gitignore-already-knows-this case just
works; `.dummyindexignore` becomes the override for dummyindex-only
exclusions (heavy benchmark dirs you commit to git but don't want
catalogued).

Side effect: the `_load_dummyindexignore` helper now reads both files
in a single ancestor walk. Helper name kept the same to avoid public-
surface churn. Patterns are appended in load order, so a
`.dummyindexignore` near the scan root overrides a same-named pattern
in a parent `.gitignore`.

## 0.13.0 — structural reorg + symbol-aware viewer + conventions (2026-05-26)

Two big shifts in one release:

1. **Package reorganised** around an adapted form of the BOS Backend
   conventions (see "Folder layout" + "Conventions" below).
2. **Viewer rebuilt** to surface classes / functions / methods, so a
   feature's detail panel cites the exact `path:line` you need to make a
   surgical edit (see "Symbol-aware features viewer" below).

All 345 tests still pass; the public test surface is unchanged.

### Symbol-aware features viewer

The graph stopped at file-level granularity. Updates to a feature meant
"this feature touches `app/api/foo.py` somewhere" — you still had to grep
to find which class or method.

`features/graph.json` now carries the AST symbol catalog inline:

- 7 node kinds (was 4): `folder`, `file`, **`class`**, **`function`**,
  **`method`**, `feature`, `flow`. Each symbol node carries `path` +
  `range` so the viewer can deep-link.
- Edge relations gain `file → class/function` (contains),
  `class → method` (contains), `feature → symbol` (touches).
- Graphify-on-itself goes from 293 nodes / 1,767 edges → 899 / 3,215.

Viewer changes (`features/graph.html`):

- **Detail panel** is now the surgical-update payload. Click a feature →
  "Files · classes · methods" section lists each touched file with a
  grouped list of class / function / method names, each carrying a
  `:line` suffix. "Flows" block shows each flow with its file targets.
- **Force view** gains kind-filter chips (default-on: folder, file,
  feature; default-off: class, function, method, flow). Symbols would
  otherwise overwhelm the layout on large repos.
- **Force tuning**: per-kind charge, collision radii, link distances.
- **Tooltips** include `path:line` when the node has a range.

Plumbing: `_graph_view(features, flows, symbols=None)` now optional-takes
the `map/symbols.json` payload. `builder._write_all` and
`indexes.rebuild_features_graph` both call `_load_symbols_map`. Missing
symbols.json gracefully degrades to the old file-only graph.

### Skill versioning

- `dummyindex/skills/skill.md` carries a `__VERSION__` placeholder right
  under its title. `dummyindex install` substitutes the installed package
  version at copy time, so the installed `~/.claude/skills/dummyindex/SKILL.md`
  shows "Installed from dummyindex `<version>`" at the top. The
  `.dummyindex_version` sidecar file stays for machine-readable checks.

### Folder layout

### Folder layout

- **`dummyindex/cli/`** — new top-level CLI package. The old monolithic
  `dummyindex/context/cli.py` (1,354 lines) is split into one module per
  subcommand (`init.py`, `rebuild.py`, `bootstrap.py`, `enrich.py`,
  `features.py`, `refresh.py`, `check.py`, `hooks.py`, `council.py`,
  `conventions.py`, `query.py`, `reality_check.py`) plus `_common.py`,
  `_migrate.py`, and `_usage.py`. `dispatch()` and `_resolve_context_root`
  remain the public surface.
- **`dummyindex/export/`** — promoted from `dummyindex/pipeline/export/` to
  a top-level package. Was a 2,785-line monolith; now four files
  (`__init__.py`, `_common.py`, `_html_assets.py`, `graph.py`). 2,185 lines
  of orphaned exporters (`to_obsidian`, `to_canvas`, `to_cypher`,
  `push_to_neo4j`, `to_graphml`, `to_svg`, `to_structure_*`, `to_flow_*`,
  `to_feature_*`, `attach_hyperedges`, `restore_hyperedges_from_disk`,
  `prune_dangling_edges`) **removed** — zero in-repo callers, zero tests.
  `to_json` and `to_html` remain.
- **`dummyindex/pipeline/`** internals regrouped:
  - `pipeline/io/` — `cache.py` + `detect.py` (filesystem-touching).
  - `pipeline/build/` — `__init__.py` (`build_from_json`), `structure.py`,
    `validate.py`, plus new `references.py` (textual reference detection
    split out of `structure.py`) and `_common.py` (`_rel_path` shared).
  - `pipeline/extract/` — `extract.py` (3,439 lines) split into 18 modules:
    `config.py`, `_common.py`, `_imports.py`, `_helpers.py`, `_configs.py`,
    `_generic.py`, `_python_rationale.py`, `_resolve.py`, and a
    `languages/` subpackage with one file per custom-walk language
    (Julia, Go, Rust, Zig, PowerShell, Objective-C, Elixir, Verilog,
    Blade, Dart) plus `_wrappers.py` for thin generic wrappers.
- **`dummyindex/context/`** regrouped by lifecycle phase:
  - `context/build/` — `runner.py`, `incremental.py`, `meta.py`, `maps.py`,
    `tree.py`, `graph.py`, `conventions.py`, `manifest.py`.
  - `context/output/` — `bootstrap.py`, `docs.py`, `instructions.py`,
    `viewer.py`.
  - `context/domains/` — `enrich.py`, `query.py`, `reality_check.py`,
    `council.py`, plus `features/` (was `features.py`, 1,575 lines, split
    into 10 modules) and `source_docs/` (was `source_docs.py`, 850 lines,
    split into 9 modules).
  - `context/hooks.py`, `context/enums.py`, `context/schemas/` stay top-level.

### Conventions

- **`docs/CONVENTIONS.md`** — new. Adapted form of the BOS Backend
  conventions. Codifies the domain-first folder rule, 200/400/600-line
  file-size cap, "every data class is `@dataclass(frozen=True)`" (BOS §7
  adapted: no Pydantic — no HTTP boundary justifies it), per-area enums
  rule, KISS/YAGNI/no-dangling-code, and lists the BOS sections that
  explicitly do **not** apply (HTTP endpoints, async, JWT, JSONB, tenant
  scope, soft-delete, transactions, structlog observability).

### Enums

- **`dummyindex/pipeline/enums.py`** — `ConfidenceLevel`,
  `NodeKind`, `EdgeRelation` (all `(str, Enum)` for JSON round-trip).
  Closed-alphabet lookup sets exported (`HIERARCHY_RELATIONS`,
  `INFERABLE_LEVELS`).
- **`dummyindex/context/enums.py`** — `DocConfidence`, `ContextSubcommand`,
  plus the `DOC_CONFIDENCE_ORDER` lookup dict.
- ~85 literal-string sites (`"EXTRACTED"` / `"INFERRED"` / `"AMBIGUOUS"` /
  `"high"` / `"medium"` / `"low"`) replaced with enum references across 25
  files. Comparisons, allowlists, dataclass defaults, and dict orderings
  now derive from the enum.
- `dummyindex/cli/_HANDLERS` is keyed by `ContextSubcommand` enum;
  `dispatch()` validates the incoming subcommand against the enum.

### Migration notes

- Old in-repo imports like `from dummyindex.context.bootstrap import ...`
  now live at `dummyindex.context.output.bootstrap`. Same for `runner`,
  `meta`, `maps`, `tree`, `graph`, `conventions`, `incremental`,
  `manifest` → `context/build/`; `docs`, `instructions`, `viewer` →
  `context/output/`; `enrich`, `query`, `reality_check`, `council`,
  `source_docs`, `features` → `context/domains/`.
- `from dummyindex.pipeline.detect` → `from dummyindex.pipeline.io` (re-
  exported from the `io` package's `__init__.py`).
- `from dummyindex.pipeline.export` → `from dummyindex.export`.
- `from dummyindex.context.cli` → `from dummyindex.cli`.
- The lazy `__getattr__` map in `dummyindex/__init__.py` is updated;
  external callers using `dummyindex.detect` / `dummyindex.extract` /
  `dummyindex.to_json` / etc. see no change.

## 0.12.0 — source-docs + retrieval + viewer + reality-check

Pre-release tag for testing. Will be promoted to `1.0` once exercised on real repos.

Bundles four roadmap items into one milestone:

### Source-docs catalog (new, not on the original roadmap)

- **Source-docs catalog** with explicit staleness signals. `dummyindex ingest` now scans existing prose docs (`README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any `*.md` at the repo root, plus `docs/`, `doc/`, `ADR/`, `RFC/`) and writes `.context/source-docs/INDEX.{json,md}`. Each entry carries a `confidence` (`high` / `medium` / `low`) derived from:
  - `broken_refs` — backticked code identifiers in the doc that no longer appear in `map/symbols.json` or `map/files.json` (the strongest signal that a doc has rotted).
  - `age_bucket` — doc mtime vs newest code mtime.
- **`--docs PATH` flag** (repeatable) on `ingest` / `context init` / `context rebuild` / `context check`. Points at doc folders outside the scan root — useful when ADRs / design docs live in a sibling directory. External paths are stored as absolute and marked `is_external: true`.
- **Doc layer surfaced into existing artifacts**:
  - `PROJECT.md` gains an "Existing documentation" section with the confidence breakdown and the highest-confidence README/intro doc.
  - `architecture/overview.md` gains a "Documented architecture" subsection when matching docs exist.
  - `features/<id>/docs.md` (new file) — pointer list to catalog entries that mention a feature's files or symbols. Pointers, not copies: confidence/staleness stays in `source-docs/INDEX.md`. Capped at the top 10 matches per feature with an overflow pointer back to the catalog.
  - Council prompts (stage 1 + stage 3) now include explicit "treat doc claims as hypotheses; verify against AST" instructions.

### v0.9 — PageIndex retrieval CLI

- **`dummyindex context query "..."`** — walks `features/INDEX.json`, scores features by token overlap with `name` / `summary` / file basenames / member-symbol names, returns the top-K with cited markdown excerpts (`path:range`).
- Budget-capped output (default 2000 tokens via `--budget N`).
- Stopword filter + CamelCase/snake_case token splitting so `parse_body` matches `ParseBody`.
- Deterministic, no LLM — same JSON the agent walks manually.
- New module: `dummyindex/context/query.py`.

### v0.10 — Viewer rebuild

- **Feature-grid as the default view** in `features/graph.html`. One clickable card per feature, sorted by file_count; opens a detail panel with summary, files, flows, confidence. Scales cleanly to 200+ features (no force-directed hairball).
- **Force-directed** kept behind a toggle for repos where the layered structure is the clearer mental model.
- **Search box** across feature names + summaries + file paths; dims non-matching cards / nodes.
- Viewer HTML extracted into its own module: `dummyindex/context/viewer.py`. `features.py` lost ~225 lines of inline HTML.

### v0.11 — Reality checker

- **`dummyindex context reality-check --feature <id> [--demote] [--json]`** — pulls concrete claims from a feature's canonical docs and verifies each against the AST.
- Claim shapes recognized: `` `X` calls `Y` ``, `` `X` uses `Y` ``, `` `X` has method `Y` ``, `` `path/to/file.py:42` ``.
- Each claim: `verified` (AST agrees) / `contradicted` (AST disagrees) / `ambiguous` (symbols exist but no direct edge).
- Writes `features/<id>/_reality-check.{json,md}`.
- `--demote` flips the feature's `confidence` to `AMBIGUOUS` in `feature.json` + `INDEX.json` when contradictions exist.
- Skill phase 3.5 (between chairman synthesis and flow refinement): `dummyindex/skills/council/45-reality-check.md`.
- New module: `dummyindex/context/reality_check.py`.

### Changed

- `pipeline.detect.detect()` accepts `extra_doc_roots: list[Path] = ()`. External roots are scanned without `.dummyindexignore` lookups (those belong to the home repo).
- Drift manifest (`cache/manifest.json`) now tracks both code and in-repo docs, so doc edits show up in `dummyindex context check` and trigger `dummyindex context rebuild --changed`.
- `dummyindex.context.incremental.rebuild_changed` compares against the manifest (which has docs) instead of `map/files.json` (code only), so a README edit no longer falsely reports "no source files changed".
- Broken-references matcher is now much wider — checks against *all* tracked repo files (not just code), JSON schema keys harvested from `*.json` in the repo, a built-in framework whitelist (Claude Code tool names, hook event names, dummyindex's own `.context/` artifact filenames and field names), and basename matches against that whitelist.
- Confidence thresholds softened: `high` accepts ≤10% broken refs (was ≤5%), `low` requires both ≥40% broken refs *and* at least 4 broken refs. Protects tiny docs that cite one hypothetical identifier.

### Docs

- README, `docs/brief/04-data-model.md`, `docs/brief/05-council.md`, `docs/brief/07-cli.md`, `docs/brief/08-skill.md`, `docs/brief/11-roadmap.md` updated to describe source-docs, query CLI, new viewer, and reality-check phase.
- v0.8 (language-agnostic LLM extraction) moved to "Beyond v1" — needs a provider choice + design discussion that hasn't happened.

### Tests

- 345 tests pass (was 278 pre-source-docs).
- New: `tests/context/test_source_docs.py` (30), `tests/context/test_query.py` (14), `tests/context/test_reality_check.py` (16).

## 0.5.0 — Claude Code only

Major reset around the v2 `.context/` flow. The package now ships one purpose: index a repo for Claude Code via a deterministic CLI backbone plus an in-session LLM enrichment pass.

### Added

- `dummyindex ingest <path>` — primary entry point. Writes `<path>/.context/` (tree, maps, conventions, playbooks, graph) and a managed block in `<path>/CLAUDE.md`. Equivalent to `dummyindex context init <path>`.
- `dummyindex context enrich-plan <path>` — emits `.context/_enrich_plan.json`, an ordered work-list of tree.json nodes whose abstracts are still deterministic stubs, grouped into per-file batches.
- `dummyindex context enrich-apply <path> --from-json FILE` — merges a `{node_id: abstract}` JSON mapping into `tree.json` idempotently, bumping each touched node's `confidence` from `EXTRACTED` → `INFERRED`. Warns and exits non-zero on unknown node_ids.
- `dummyindex install --scope project [--dir PATH]` — install the Claude Code skill per-repo instead of user-global.
- `/dummyindex` skill rewrite — Claude now runs the CLI then enriches `PROJECT.md`, `architecture/overview.md`, `tree.json` abstracts, all five playbooks, and `graph/GRAPH_REPORT.md` from inside the session. The enrichment write-back goes through `dummyindex context enrich-apply` (no inline tree-mutation Python).

### Removed

- All non-Claude platform installers (Codex, OpenCode, Cursor, Gemini, Aider, Copilot, Claw, Droid, Trae, Hermes, Kiro, Antigravity, VSCode, Windows).
- The legacy v1 commands (`add`, `query`, `path`, `explain`, `update`, `watch`, `cluster-only`, `save-result`, `check-update`, `benchmark`, `serve`, `hook`).
- Dead modules: `dummyindex/runtime/{serve,ingest,hooks,transcribe,watch,manifest,run_log}.py` and `dummyindex/analysis/{flows,flow_naming,features,feature_naming,report,wiki,benchmark}.py`.
- Stale install fragments: `_PLATFORM_CONFIG`, per-platform skill files, `claude install`/`gemini install`/etc. subcommands.
- Optional-dependency extras with no surviving callers: `mcp`, `neo4j`, `pdf`, `watch`, `svg`, `office`, `video`. Only `leiden` and `dev` remain.
- `V0_SCOPE.md`, `BRIEF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `.opencode/`, `evals/v0/` — superseded by this README and by the running CLI.

### Fixed

- `dummyindex-out/` references purged from the (now slimmed) installer text. Every CLAUDE.md / AGENTS.md / GEMINI.md template that survives points at `.context/`.
- `.claude/`, `.cursor/`, `.aider/`, `.kiro/`, `.trae/`, `.trae-cn/`, `.github/`, `.gitlab/`, and `.context/` are now skipped by both `pipeline.detect` and `pipeline.structure` so agent config / self-output never lands in the index.
- `tree.json` no longer carries phantom file nodes for non-code files (CLAUDE.md, README.md, configs, etc.). The v2 code paths now call `build_structure(..., include_extras=False)`; the legacy "include every file in the source layout" behavior is preserved as the default for any external caller.

### Public API

- `dummyindex/__init__.py` now lazy-exposes only the v2 surface: `detect`, `extract`, `collect_files`, `build_from_json`, `build_structure`, `cluster`, `to_json`, `to_html`. Everything else accessible via the `dummyindex.context.*` subpackage or the CLI.
