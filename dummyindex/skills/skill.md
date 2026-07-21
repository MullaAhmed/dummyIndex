---
name: dummyindex
description: "Persistent context engine for a repository. Builds and reconciles a `.context/` folder through deterministic AST extraction plus a spec-shaped sequential council in which a stack-aware developer drafts `spec.md` and `plan.md`, an architect reorganizes the plan, and critics file `concerns.md`. Gives Claude Code and Codex durable PageIndex-style tree navigation instead of broad source searches; Claude receives managed drift, memory, GC, and document-guard hooks, while Codex receives active-instruction-file guidance and native subagent mappings. Use for `/dummyindex` or `$dummyindex`, optionally with a path, `--refresh`, `--recouncil`, or `--reconfigure`, and for requests such as index this repo, set up dummyindex, create context for this project, refresh the context index, or reconcile code changes."
---

# /dummyindex / $dummyindex — The context engine orchestrator

> **Installed from dummyindex `__VERSION__`.** Run `dummyindex --version` to confirm the CLI matches. If they diverge, diagnose with `dummyindex context check --versions` (it reports which layer is stale), then run `/dummyindex-update` on Claude Code or `$dummyindex-update` on Codex to bring the CLI, skills, and this repo's wiring back into sync — the update skill is non-destructive on a curated `.context/`. Don't reach for a blunt `dummyindex install` to "fix" a version skew.

Claude Code spells installed skills as `/dummyindex...`; Codex spells them as
`$dummyindex...` (or selects them through `/skills`). Slash-form examples below
are the Claude spelling of the same skill. For CLI writes, preserve the active
host with `--platform claude` or `--platform codex`; use `both` only when the
user explicitly wants both integrations.

You are the conductor. Python is the toolbox. Subagents are the workforce.

## What you do (the high-level flow)

1. **Resolve scope + root.** The user's invocation tokens after the host's dummyindex skill invocation are the scope. Apply this rule **literally**:
   - **Rule 0 — CLI command, not a scope (check FIRST).** If the first token is a dummyindex CLI command — `usage`, `install`, `uninstall`, `context`, `ingest`, `status` (i.e. anything `dummyindex --help` lists as a top-level command) — the user wants to **run that command**, not index a path. Run `dummyindex <tokens>` verbatim (e.g. `/dummyindex usage chat` → `dummyindex usage chat`; on Claude, route a bare `usage` to the `/tokens` report), report its output, and **STOP**. On Codex, `dummyindex usage` is not a current-session reporter because it reads Claude transcripts; use native `/status` or `/usage` unless the user explicitly asked for saved Claude history. Never treat these tokens as an index scope, and never start an ingest or council from them. (Only fall through to the path rules below when the first token is NOT one of these commands.)
   - `/dummyindex` (no args) → scope = cwd.
   - `/dummyindex <token>` where `<token>` is a path that exists relative to cwd (or absolute) → **scope = that path**. Do not paraphrase, do not "interpret" it as "the application" or "the codebase". Treat as a literal path.
   - `/dummyindex index <path>` / `/dummyindex scan <path>` / similar verb forms → still resolve `<path>` as the scope; the verb is filler.
   - Multiple non-flag tokens → join with `/` if they look like a path; otherwise fail with "ambiguous scope, please pass one path".
   - Pass the resolved scope explicitly to `dummyindex ingest <path>`. Never run ingest with no args when the user gave you a token to interpret.
2. **Phase 0 — Preflight (always, before any write):** run `dummyindex context preflight <root>` and show the summary. It reports git-clean status and inventories any existing `.claude/` setup (settings.json validity + user hooks, `.claude/rules/`, `.claude/agents/`, CLAUDE.md managed-block state). That Claude inventory controls Claude writes and is informational on a Codex-only run. **Honor its applicable warnings** — see **Phase 0** below.
3. **Phase 1 — Deterministic backbone:** run `dummyindex ingest <scope> --platform <resolved-platform>` (`claude`, `codex`, or the explicitly requested `both`).
4. **Phase 1.2 — Onboarding (first run only):** if `.context/config.json` is absent (fresh repo or a v0.13.x upgrade), run the platform-aware setup and persist via `dummyindex context onboard`. Claude-only asks five questions. Codex-only uses `model=current`, persists `--no-hook`, and asks only the portable preferences. A both-host run uses portable `model=current` and also asks whether to keep Claude's managed hooks (default: on). See `council/05-onboarding.md`. Also runs on `--reconfigure`.
5. **Phase 1.5 — Conventions:** dispatch agents to author folder-organization, coding-practices, testing, data-access docs into `.context/conventions/`. See `council/15-conventions.md`.
6. **Phase 2 — Structural review:** dispatch the architect to propose feature regrouping; apply via `features-rename`.
7. **Phase 3 — Per-feature pipeline:** run stages 1 → 2 → 3 (specify / plan / critique) ordered *within* each feature, but **in parallel across features** via `context council-batch --next` — see `council/22-parallel-dispatch.md`.
8. **Phase 3.5 — Reality check:** after stage 3 for each feature, fact-check concrete claims in `plan.md` + `concerns.md` against the AST. See `council/45-reality-check.md`.
9. **Phase 4 — Flow refinement:** the same dev filters + narrates flows per feature.
10. **Phase 4.5 — Tree enrichment:** fill `tree.json` node abstracts (stubs → INFERRED) so future-session retrieval over the tree reads real prose. Mode-gated. See `council/52-tree-enrich.md`.
11. **Phase 5 — Reconcile:** `dummyindex context refresh-indexes`.
12. **Phase 6 — Report:** counts, mode, where to start reading, cost.

Detailed instructions for each phase live in companion markdowns. **Read them as you reach each phase.** Do not duplicate their content here.

## Companion markdowns (read on-demand)

| When | Read |
|---|---|
| Onboarding (first run / `--reconfigure`) | `council/05-onboarding.md` |
| Council overview, modes, file layout | `council/00-overview.md` |
| Phase 1.5 (conventions fan-out) | `council/15-conventions.md` |
| Phase 2 (architect regrouping) | `council/10-structural-review.md` |
| Phase 3 stage 1 (`/specify` — dev drafts spec.md + plan.md) | `council/20-specify.md` |
| Phase 3 stage 2 (`/plan` — architect reorganises plan.md) | `council/30-plan.md` |
| Phase 3 stage 3 (`/critique` — critics write concerns.md, mode-gated) | `council/40-critique.md` |
| Phase 3.5 (reality check) | `council/45-reality-check.md` |
| Context7 lookup protocol (MCP companion) | `council/55-context7.md` |
| GitHub release-check protocol (MCP companion) | `council/56-github.md` |
| Phase 4 (flow filter + narrate) | `council/50-flow-narrative.md` |
| Phase 4.5 (tree enrichment — node abstracts) | `council/52-tree-enrich.md` |
| Skip rules for trivial features | `council/18-filter-trivial.md` |
| Resumption logic when re-running | `council/19-resume.md` |
| Reconcile a commit delta (place new files, re-enrich drift, stamp the anchor) | `council/65-reconcile.md` |
| Doc reorg (`--reorg-docs`, destructive) | `council/60-doc-reorg.md` |
| Persona prompts | `agents/dev.md`, `agents/architect.md`, `agents/critic-database.md`, `agents/critic-security.md`, `agents/critic-product.md` |

## MCP integrations (optional)

The pipeline wires three MCP servers when the runtime exposes them, and runs
**identically without them** — the `.context/` artifacts have the same shape
either way; only the quality of the prose changes. No MCP call is ever mandatory.

Tool namespaces vary by how each server was installed (a standalone server vs. a
plugin), so the prefixes below are matched **tolerantly** — the call sites look
for the server *family*, not one exact string.

| Server | Tool prefix (any matching namespace) | Used by | What it adds |
|---|---|---|---|
| **Context7** | `*context7*` — e.g. `mcp__context7__*` or `mcp__plugin_context7_context7__*` | Phase 1.5 conventions, `/specify` dev (`{{framework_docs}}`), DBA + security critics, reality-check | Per-library, always-current API docs so personas don't invent patterns or claim APIs that no longer exist. Protocol: `council/55-context7.md`. |
| **Sequential Thinking** | `mcp__sequentialthinking_*` — e.g. `mcp__sequentialthinking_sequentialthinking__sequentialthinking` | Architect's structural review (Phase 2) + `/plan` revision (Phase 3 stage 2) | Explicit draft → cross-check → revise → emit, with an audit trail (`_structural-log.json` / `02-architect-notes.md`). |
| **GitHub** | `*github*` — e.g. `mcp__github__*` or `mcp__plugin_github_github__*` | Security critic (Phase 3 stage 3) | Real release history for a feature's pinned deps — version distance from latest + security-relevant notes since the pin. Protocol: `council/56-github.md`. |

Every wired site carries its own graceful-fallback clause, so a missing server is
never a failure — the procedure just falls back to single-shot reasoning.

## Doc layer — `.context/source-docs/`

Phase 1 catalogues every checked-in prose document (README, CHANGELOG, ARCHITECTURE, docs/, ADR/, RFC/, and any path passed via `--docs PATH`). The catalog lives at `.context/source-docs/INDEX.{json,md}` and carries **explicit staleness signals** per doc:

- `broken_refs` — backtick-wrapped identifiers / file paths in the doc that don't appear in `map/symbols.json` or `map/files.json`. **The strongest staleness signal.**
- `age_bucket` — `fresh` / `recent` / `aging` / `stale` / `old`, derived from the doc's mtime vs the newest code mtime.
- `confidence` — `high` / `medium` / `low`, derived from those two signals.

When dispatching any persona that may consult the prose layer, include this directive verbatim:

> The repo's prose docs are catalogued at `.context/source-docs/INDEX.json`. **Treat doc claims as hypotheses, not ground truth.** Quote `high` confidence docs only after cross-checking the relevant symbol/file still exists in `map/symbols.json`. For `medium` confidence, verify every quoted identifier. For `low` confidence, use only as historical context — never as fact. If you spot a contradiction between a doc and the AST, the AST wins; mention the conflict in the council audit trail.

The deterministic backbone already wires the catalog into:
- `PROJECT.md` — picks its description from the highest-confidence README and surfaces a confidence breakdown.
- `architecture/overview.md` — a "Documented architecture" section pointing at design/architecture docs with confidence labels.
- `features/<id>/docs.md` — pointer list to catalog entries that mention a feature's files or symbols (pointers, not copies — staleness stays in one place).

## Invocation flags

| Flag | Effect |
|---|---|
| (none) | Full ingest + **standard-mode** council; install dummyindex's managed hooks on Claude only. |
| `--scaffold-only` | Phase 1 only. No council. |
| `--mode light\|standard\|deep` | Override the configured/default mode for this run. See `council/00-overview.md` for cost. |
| `--reconfigure` | Re-run the host-aware onboarding and rewrite `.context/config.json`. See `council/05-onboarding.md`. |
| `--recouncil` | Re-run council on all features. Honors hash cache. |
| `--recouncil <feature_id>` | Re-run council on one feature. |
| `--recouncil --force` | Re-run, ignore hash cache. |
| `--refresh` | Equivalent to `dummyindex context refresh-indexes`. |
| `--no-trivial-filter` | Council every feature, including trivial. |
| `--no-hooks` | Skip the managed Claude Code hooks during a Claude install; no effect is needed for Codex-only guidance. |
| `--reorg-docs` | **Destructive, opt-in.** Reorganise the repo's real `README`/`docs/**` in place to a consistent house style. Gated: refuses on a dirty tree, backs up first, edits in-session with per-file confirm. Read `council/60-doc-reorg.md`. Not part of the normal pipeline. |
| `--status` | Print the read-only index, drift, version, depth, equipment, proposal, and memory overview. Exit. |

## Phase 0 — Preflight (always, before any write)

Run this **before** `ingest`, on every invocation, so you never write into a
repo whose existing setup you haven't read:

```bash
dummyindex context preflight <root>
```

It touches nothing. It prints a "what I'll write / manage" vs "what I'll leave
untouched" summary plus warnings. Surface the summary to the user, then act on
the signals:

- **`settings.json` unparseable** → the hook step will refuse to touch it (it
  won't be clobbered). Tell the user to fix the JSON by hand, and continue with
  the rest of the build; the SessionStart hook just won't install this run.
- **Working tree dirty** → mention it. The ingest/council pipeline's writes are
  confined to `.context/` plus the selected host guidance: Claude's managed
  CLAUDE.md block and additive settings hook, or Codex's managed active project
  instruction-file block. Only Claude's `/dummyindex-equip`, run separately,
  may write more toolkit state into `.claude/`; Codex's `$dummyindex-equip` is
  a read-only native-routing pass. This is advisory for a normal run. (It
  becomes a hard gate for any in-place doc edit — out of scope for the standard
  pipeline.)
- **`.claude/rules/` present** → those are the team's own conventions. Phase 1.5
  must reconcile against them rather than re-derive from scratch (see
  `council/15-conventions.md`).
- **Project agents present** → prefer the user's available agents when
  dispatching; the dev-picker already degrades to a generic agent when a
  specialist isn't installed.

Preflight is read-only and additive to the flow — it never blocks a normal
ingest. Skip it only under `--scaffold-only` if the user is in a hurry, but
prefer to always show it.

## Phase 1 — Deterministic backbone

```bash
dummyindex ingest <path> --platform <claude|codex|both>
```

What you get:
- `.context/` folder with backbone + scaffolded features.
- Host guidance: Claude gets a managed block in `<root>/.claude/CLAUDE.md`
  (legacy `<root>/CLAUDE.md` is auto-migrated); Codex gets a managed block in
  its active project instruction file (`AGENTS.override.md`, `AGENTS.md`, or a
  configured fallback). With `--platform both`, both hosts are written.
- On Claude only, managed hooks installed at `.claude/settings.json`:
  - **SessionStart** runs `dummyindex context plan-update` (drift report + freshness badge cache), `dummyindex context memory session-start` (memory block), and `dummyindex context gc signal` (commit-throttled `/dummyindex-gc` nudge). The drift report carries **mtime drift** plus commit-anchored **new files owned by no feature** and **features awaiting enrichment**; those nudge the session toward `council/65-reconcile.md`.
  - **Stop** runs `dummyindex context memory nudge` and `dummyindex context reconcile-gate`. The gate blocks session exit **once** when a substantial session left `.context/` stale, directing the session to reconcile + `reconcile-stamp`; it never stamps the anchor itself (opt out with `"auto_council": false`).
  - **PreCompact** runs `dummyindex context memory breadcrumb`.
  - **PreToolUse** (matcher `Write`) runs `dummyindex context guard-doc-write`, which denies creating internal planning docs in unmanaged locations and points at `.context/proposals/` or `.context/audits/`.
  No shell-side rebuild loop runs on commit or the legacy dummyindex `PostToolUse`, and no hook advances the anchor.
- On a Codex-only integration, dummyindex does not install or translate those Claude hook bodies.
  Codex has its own hook surface, but this integration relies on its active
  project instruction file and explicit `$dummyindex*` workflows; onboarding
  persists `--no-hook`. A both-host integration keeps the Claude hook choice.
- A drift manifest at `.context/cache/manifest.json`.
- On Claude only, the **`superpowers` plugin** enabled in `.claude/settings.json`
  (`enabledPlugins["superpowers@claude-plugins-official"]`) — a sane default
  wired on first init. Opt out with `--no-superpowers` or
  `"wire_superpowers": false` in `.context/config.json`. An existing per-repo
  decision (the key already present, enabled or disabled) is left as-is.

Verify `features/INDEX.json` exists before proceeding. If `ingest` failed, surface the error and stop.

If `--scaffold-only`: stop here. Print report.

## Phase 1.2 — Onboarding (first run only)

Read `council/05-onboarding.md`. Check for a persisted config:

```bash
dummyindex context config show
```

- Prints a config → already onboarded. Skip to Phase 1.5.
- Reports "no config.json" (exit 1) → run the setup through the host's normal
  user-question mechanism. Claude-only asks scope, mode, model, managed hooks,
  and external docs. Codex-only asks scope, mode, and external docs and uses
  `--model current --no-hook`. A both-host run asks the portable preferences
  plus the Claude managed-hook choice and persists `--model current` with
  `--hook` by default.
- `/dummyindex --reconfigure` → always re-run the questions.

On Claude-only, scope/mode/model are required and hooks/docs are skippable. On
Codex-only, `current` is the explicit active-session model selector and
`--no-hook` is the only supported dummyindex hook preference; neither needs a
false choice among Claude-only options. With `both`, use `current` and retain or
ask for the applicable Claude hook preference. The mode chosen here is the
run's default; an explicit `--mode` on the invocation still overrides it.

Skip this phase entirely under `--scaffold-only`.

## Phase 1.5 — Conventions (agent-derived)

Read `council/15-conventions.md`. Fan four dispatches out in **parallel**:

- architect → `conventions/folder-organization.md`
- dev → `conventions/coding-practices.md`
- dev → `conventions/testing.md`
- critic-database → `conventions/data-access.md`

Each subagent places its output atomically via
`dummyindex context conventions-write --section <name> --from-file <tmp>`.
`naming.md` is already on disk from Phase 1 (statistical, not authored).

Skip in mode `light`.

## Phase 2 — Structural review

Read `council/10-structural-review.md`. Dispatch the architect via Task subagent. Apply the regrouping plan via `dummyindex context features-rename` calls.

Skip if `features/INDEX.json` has ≤ 2 features.

## Phase 3 — Per-feature pipeline

For each feature in `features/INDEX.json`:

1. Check the trivial-filter (`council/18-filter-trivial.md`). If trivial: dispatch the architect consolidation pass, skip the rest of phase 3 for this feature.
2. Check resumption (`council/19-resume.md`). Skip stages already complete.
3. Stage 1 — `/specify` — read `council/20-specify.md`. Run `dev-pick`, dispatch one dev. Writes `spec.md` + `plan.md`; snapshot the draft to `council/01-dev-draft.md`.
4. Stage 2 — `/plan` — read `council/30-plan.md`. Dispatch the architect to reorganise `plan.md` in place; writes `council/02-architect-notes.md`. Skip in mode `light`.
5. Stage 3 — `/critique` — read `council/40-critique.md`. Mode-gated:
   - **light:** skip.
   - **standard:** one relevant critic, no cross-review.
   - **deep:** all relevant critics + cross-review.

Stages run **in order within a feature** (plan needs the dev's draft; critics need the finalised plan), but **different features are dispatched in parallel** — `council-batch --next` returns the earliest incomplete stage's units for up to `--cap` agents at once.

## Phase 4 — Flow refinement

For each enriched feature, dispatch the **same dev** (resolve via `dev-pick`) with the flow-narrative procedure (`council/50-flow-narrative.md`).

The dev decides keep/discard per flow:
- Discard: `dummyindex context flow-remove --feature <id> --flow <flow_id>`
- Keep: `Write` a one-paragraph narrative to `features/<id>/flows/<flow_id>.md` (using the structure in `agents/dev.md`).

Skip in mode `light`.

## Phase 4.5 — Tree enrichment (node abstracts)

Read `council/52-tree-enrich.md`. The deterministic backbone leaves every
`tree.json` node with a stub `abstract` (`confidence: EXTRACTED`). This phase
fills them in so a future session's PageIndex walk over `tree.json` reads real
prose. It's **retrieval-facing, not council input** — the personas never read
node abstracts — so it runs here, after the per-feature work and before reconcile.

```bash
dummyindex context enrich-plan <root>          # → .context/cache/_enrich_plan.json
# dispatch subagent(s) to author one-line abstracts per batch (scope by mode)
dummyindex context enrich-apply <root> --from-json <tmp.json>
```

Scope by mode: **light** skips; **standard** enriches the `structure` batch
(project + dirs + files) via one architect; **deep** also fans a dev out per
`file_subtree` batch for symbol-level abstracts. Subagents author; you dispatch
and apply. Full procedure + cost rationale in `council/52-tree-enrich.md`.

Skip in mode `light`.

## Phase 5 — Reconcile

```bash
dummyindex context refresh-indexes
```

Regenerates `INDEX.md`, `features/INDEX.md`, `features/graph.json`, `features/graph.html` from disk.

## Phase 6 — Report

Tell the user, in this order:

1. Mode used.
2. Counts: features enriched, flows kept, flows dropped, agent invocations.
3. Top open questions surfaced in `plan.md` "Open questions" + unresolved `concerns.md` items (top 3 across all features).
4. Cost estimate (rough — based on agent invocation count).
5. Where to start reading: `.context/HOW_TO_USE.md`.
6. Host-specific next steps:
   - **Claude Code:** "Open Claude Code in this repo — the managed hooks are live. Every new session sees stale feature docs, new files not yet in any feature, features awaiting enrichment, memory, and GC nudges. Update stale docs in-session; for new/changed code run the reconcile procedure — invoke `/dummyindex --recouncil` (a skill invocation, **not** a `dummyindex` CLI verb), then follow `council/65-reconcile.md`."
   - **Codex:** "Open Codex in this repo — the active project instruction file points at the durable index and the `$dummyindex*` skill family is available. For new or changed code invoke `$dummyindex --recouncil` (a skill invocation, **not** a `dummyindex` CLI verb), then follow the installed skill's `council/65-reconcile.md`. Do not claim Claude session hooks are active on a Codex-only install."
   - For both hosts, the reconcile procedure places and re-enriches changed content, then runs `reconcile-stamp`. The anchor only moves on `ingest` or `reconcile-stamp`, never from a hook.

## Subagent dispatch rule

When dispatching any persona, read its markdown and inline its mandate. On
Claude, use the `Task` tool and the persona's `subagent_type`; for the dev,
resolve it first with `dummyindex context dev-pick --feature <id>`. On Codex,
map read-only review/exploration to built-in `explorer`, artifact-authoring or
implementation to `worker`, and coordination/synthesis to `default`. Do not try
to dispatch Claude type names from Codex.

**Honor agent availability (don't dispatch to an agent that isn't installed).**
On Claude,
`dev-pick`'s JSON now carries a `fallbacks` array — the ordered alternatives to
try when the primary `subagent_type` isn't available in this environment (e.g.
`["Senior Developer", "general-purpose"]`). Cross-reference against the agents
the **Phase 0 preflight** found (and the agent registry you can see): dispatch
the first of `[subagent_type, *fallbacks]` that actually exists. The chain always
ends at `general-purpose`, which is always available, so dispatch never dead-ends.
Apply the same "first available" rule to the architect/critic types below —
fall back to `general-purpose` if a specialist (e.g. Security Engineer) isn't
installed, rather than failing the stage.

Defaults bundled with the current dummyindex package:

```
agents/dev.md               subagent_type: resolved via dev-pick
                            (Backend Architect / Frontend Developer /
                             Data Engineer / AI Engineer / Senior Developer);
                            fallbacks: Senior Developer → general-purpose
agents/architect.md         subagent_type: Backend Architect   (→ general-purpose)
agents/critic-database.md   subagent_type: Data Engineer        (→ general-purpose)
agents/critic-security.md   subagent_type: Security Engineer    (→ general-purpose)
agents/critic-product.md    subagent_type: general-purpose   (no PM specialist available)
```

Claude specialist subagents come with domain reflexes baked in. On Codex, the
inlined persona supplies those domain instructions while the native built-in
supplies the execution shape. In both cases, the persona markdown owns the
`.context/` output contract.

## What NOT to do

- ❌ Don't write more than what each procedure markdown specifies.
- ❌ Don't run a *single feature's* stages out of order — specify → plan → critique is ordered. (Across features, parallel is expected.)
- ❌ Don't skip the logging calls — they're how resumption works.
- ❌ Don't edit the persona markdowns inline — read them, adapt the prompt, dispatch.
- ❌ On Claude, don't default every dispatch to `general-purpose` — read
  `subagent_type:` from each persona (and run `dev-pick` for the dev). On Codex,
  use the `explorer` / `worker` / `default` mapping above.
- ❌ Don't run the council on a repo without first running `dummyindex ingest` — the backbone is required.

## Failure handling at the orchestrator level

- A persona subagent fails → log, continue with the others.
- The structural-review architect fails → log, skip phase 2, proceed.
- The CLI itself errors → halt, surface the error.
- The user Ctrl-C's mid-run → `_council-log.json` records partial state; next run resumes (see `council/19-resume.md`).

## Session memory (sibling skill)

dummyindex ships a markdown-first session-memory store at `.context/session-memory/`
(tiers `now.md` → `recent.md` → `archive.md`, plus `core-memories.md`). It is
**not** part of the generated index and is never regenerated — `ingest` only
seeds empty stubs; `refresh`/`rebuild` leave it untouched. On Claude, the
SessionStart hook injects a memory block (suppressed automatically if the
`remember` plugin is also installed). Codex installs no dummyindex memory hook;
its durable store is still available explicitly. To save a handoff, invoke **`/dummyindex-remember`** on Claude or
**`$dummyindex-remember`** on Codex: it appends a
first-person summary to `now.md`, runs `dummyindex context memory roll`, and
promotes durable facts to `core-memories.md`.

## Build loop (sibling skills) — plan → equip → execute

Beyond understanding + documenting, dummyindex can drive a **grounded build loop** for *new* features. It stays the spine (it never writes production code itself) — it plans and orchestrates, while dispatched agents write production code. Claude can additionally render `.context/`-grounded agents, skills, and a formatter hook into `.claude/`. Codex never needs that equipment: it uses the same proposal/build contracts with native subagents. Three sibling skills, each leaning on `.context/` (shown in Claude/Codex spelling):

- **`/dummyindex-plan` / `$dummyindex-plan "<feature>"`** — scaffolds a consistency-checked `.context/proposals/<slug>/` (`spec.md`/`plan.md`/`checklist.md`) via `dummyindex context propose`; reuses `query` to avoid duplicating an existing feature and to cite conventions + reusable symbols. Claude then auto-equips with `equip apply --for-proposal <slug>`. Codex performs no equip discovery, install, or apply and leaves native execution untagged.
- **`/dummyindex-equip` / `$dummyindex-equip`** — on Claude, builds and lifecycle-manages an evolving `.claude/` toolkit with an origin-hash baseline. On Codex, performs a **read-only** capability-routing report over already available native skills/custom agents and the built-in `explorer` / `worker` / `default`; it writes neither `.claude/**` nor `.context/equipment.json`.
- **`/dummyindex-build` / `$dummyindex-build`** — drives the proposal's `checklist.md` one dependency wave at a time with verify-before-tick, then reconciles new code into `.context/`. Claude uses its manifest and stops if it is absent. Codex treats a missing manifest as normal and proceeds directly with built-in native subagents. The post-build `equip patch` learning step is Claude-only.

## Final word

Your job as the orchestrator is **dispatch + reconcile**, not authorship. Every word in `.context/` should come from a persona subagent or from Python. You are the conductor. Trust the procedures.
