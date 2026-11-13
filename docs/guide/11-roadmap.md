# 11 — Roadmap

What we defer. In priority order.

A gate holds each item until the previous one ships.

## v0.6 — Always-on infrastructure ✅ shipped

- 3-line CLAUDE.md managed block (down from 41 lines).
- Auto-refresh hooks installed by `ingest`:
  - git `post-commit` hook → `rebuild --changed`.
  - Claude Code `PostToolUse` hook → `rebuild --changed` after Edit/Write/Bash(mv|rm|cp).
  - Claude Code `SessionStart` hook → `check --auto-refresh --quiet`.
- New CLI: `context check`, `context hooks install/uninstall/status`.
- Drift detection in `.context/cache/manifest.json`.
- Consolidation: `graph/` contents moved under `features/`. The release dropped the pyvis HTML.

## v0.7 — Multi-agent council ✅ shipped

- Five personas: architect, senior developer, database engineer, security analyst, product manager.
- Chairman synthesizer.
- Three stages: independent perspectives → cross-review → synthesis.
- Default mode: standard. Override via `/dummyindex --mode deep|light`.
- Structural review pre-stage (architect regrouping).
- The senior developer filters flows.
- `_council-log.json` for resumption.
- Per-feature content hash for cache.
- CLI helpers: `flow-remove`, `section-write`, `council-log`, `features-merge`, `conventions-write`.

## Source-docs layer ✅ shipped (between v0.7 and v0.9)

Not on the original roadmap. It surfaced when dummyindex ran on repos with real prose docs.

- `.context/source-docs/INDEX.{json,md}` catalogs every prose doc found in the repo. These docs are README, CHANGELOG, ARCHITECTURE, SECURITY, BRIEF, and any root-level `*.md`. The catalog also covers `docs/`, `doc/`, `ADR/`, and `RFC/`.
- `--docs PATH` (repeatable) for external doc roots.
- Per-doc `confidence` (high/medium/low) derived from broken backticked references and age against the newest code mtime.
- Wired into PROJECT.md, architecture/overview.md, `features/<id>/docs.md` (top-10 pointers), and the council stage-1 + stage-3 doc-evidence directive.

## v0.9 — PageIndex retrieval CLI ✅ shipped (in v0.12)

- `dummyindex context query "..."` — walks `features/INDEX.json` → scores features by token overlap with name/summary/files/symbols → returns cited markdown excerpts with `path:range`.
- Budget-capped (default 2000 tokens, `--budget N` overrides).
- Single, stable CLI surface every platform (Claude Code, Cursor, Codex CLI, OpenCode, Aider) can shell out to.
- Deterministic — no LLM in the loop. The CLI is a view over the same JSON the agent walks manually.

## v0.10 — Viewer rebuild ✅ shipped (in v0.12 + v0.13)

- v0.12: feature-grid default, D3 force toggle, search, and council excerpts in tooltips.
- v0.13 follow-on: symbol-kind nodes (class/function/method) so the detail panel can cite `path:line`. Kind-filter chips in the force view. Force layout tuned for 900+ nodes.

## v0.11 — Reality checker integration ✅ shipped (in v0.12)

- `dummyindex context reality-check --feature ID` — Phase 3.5 in the skill.
- Pulls concrete claims out of the feature's canonical docs, verifies against `map/symbols.json` + symbol-graph + source.
- Contradiction → confidence flipped to `AMBIGUOUS`. The check surfaces the contradiction for the original persona to revisit.

## v0.12 — Source-docs + retrieval + viewer + reality-check ✅ shipped

Bundles v0.9/0.10/0.11 plus the source-docs catalog (not originally on the roadmap — see "Source-docs layer" above).

## v0.13 — Structural reorg + symbol-aware viewer ✅ shipped

- Package reorganised around the BOS Backend conventions (adapted for a synchronous CLI). `docs/reference/01-conventions.md` is the contract.
- `features/graph.json` carries class / function / method nodes. The detail panel becomes the surgical-update payload: pick a feature → see touched files grouped by class/method with `path:line` citations.

  > **Superseded.** Denormalization of every symbol into the viewer payload produced ~4k nodes on a mid-size repo — complete and unreadable. `graph.json` is now the curated codebase scan (schema v2, ≤ 60 nodes). Per-symbol navigation stayed where agents query it, in `map/symbols.json` and `features/symbol-graph.json`. See `docs/guide/04-data-model.md`.

- Dead-code removal: 2,185 lines of orphan exporters (`to_obsidian`, `to_canvas`, `to_cypher`, …) cut from `pipeline/export/`.
- Skill installs now stamp the SKILL.md with the package version. This makes drift between the installed skill and the CLI visible.

## v0.13.5 — SessionStart drift hook replaces shell-side rebuild ✅ shipped

A correction to the v0.6 auto-refresh model. The old design installed three hooks (`git post-commit`, Claude `PostToolUse`, Claude `SessionStart`). All of them fired `rebuild --changed` in a shell. That deterministic-only refresh re-ran feature scaffolding on every edit. It produced orphan `community-N/` folders, clobbered `features/INDEX.json`, and stamped placeholder `flow-NNN.md` files. The skill never came back to rewrite these files, because the skill never runs from a shell hook.

The fix flips the model: **hooks no longer rebuild the backbone**.

- **New CLI `dummyindex context plan-update`** — prints a markdown drift report to stdout. The report has one line for each feature whose source mtime exceeds its docs' mtime. Empty when nothing is stale. Claude's `SessionStart` hook takes plain stdout as `additionalContext`.
- **New module `dummyindex.context.drift`** — mtime-based staleness, with heuristic decay. An edit to a feature doc advances its mtime, and the signal goes quiet. No `mark-updated` command needed.
- **`hooks` install now installs only `SessionStart`** and scrubs the legacy post-commit + PostToolUse entries on upgrade. It leaves user-authored hooks without our sentinel untouched.
- The active Claude session — which knows *what* changed and *why* — updates `.context/features/<id>/*.md` in place, instead of a blind shell rebuild.

## v0.14 — Spec-kit-shaped pipeline + stack-specialist dev + onboarding ✅ shipped

The redesign that replaces the v0.13 parallel-essay model. Inspired by [github/spec-kit](https://github.com/github/spec-kit): layered artifacts produced by a sequential pipeline, each step with one author and one job.

**Decisions locked (2026-05-27):**

1. The project **drops** `README.md` per feature — `spec.md` is the entry point. No 10-line index file.
2. Reality-check validates `plan.md` + `concerns.md` `path:range` citations. `spec.md` is intent-level, not line-checked.
3. `standard` is the **default** mode. `--mode light|deep` overrides it.

### Artifact reshape

Each feature gets three layered docs instead of six essays that overlap:

- `spec.md` — what does this feature do? (intent, contracts, user-visible behavior)
- `plan.md` — how is it implemented? (architecture, file map, key decisions)
- `concerns.md` — risks and gaps (data integrity, security, product surface)

Retires: `README.md` (dropped entirely — `spec.md` is the entry point), `architecture.md`, `implementation.md`, `data-model.md`, `security.md`, `product.md`. `section-write` accepts both the new and legacy section names for one release. Anything that points at `<feature>/README.md` (the viewer, `features/INDEX.md`) gets repointed at `spec.md`.

### Pipeline

```
backbone → /specify (dev) → /plan (architect) → /critique (critics, mode-gated)
```

- **/specify**: one stack-specialist dev (FastAPI / Django / Spring / React / data / AI / generic, picked from `map/files.json` + manifests) drafts `spec.md` + `plan.md`.
- **/plan**: architect reorganises `plan.md` in place and writes the `02-architect-notes.md` audit.
- **/critique**: critics (DBA / security / PM) file findings into `concerns.md`. Mode-gated:
  - `light`: skip critique entirely.
  - `standard` (default): one critic, picked by feature signals.
  - `deep`: all relevant critics + cross-review.

### Persona collapse

From 6 personas to 3 role classes:

- **Dev** — one parameterised persona (`{{framework}}` slot, Context7 docs injected per dispatch when v0.15 lands).
- **Architect** — keeps the regrouping pre-stage, gains the per-feature `plan.md` revision job.
- **Critics** — DBA / security / PM as critique-only, no primary authorship.

Retired: chairman (no synthesis step needed), standalone senior-developer (folded into the dev's generic branch).

### Onboarding flow

The original Claude `/dummyindex` flow on a repo with no
`.context/config.json` triggers a five-question interactive setup. A Codex-only
run asks only the three portable preferences. It persists
`model=current, hook=false`. It does not offer Claude model labels or hook
installation. A both-host run also uses `model=current` but retains the Claude
managed-hook choice (default on). Answers persist to committed config and never
include credentials.

Questions:

1. **Scope** — whole repo / a subdir / pass paths explicitly each run.
2. **Mode** — standard (recommended) / light / deep, with a live cost + time estimate shown after the pick. The feature count is already known from the backbone.
3. **Model** — Opus 4.8 / Sonnet 4.6 (recommended) / Haiku 4.5. _Required — never silently defaulted._
4. **Managed hooks** — install dummyindex's managed Claude Code hooks (recommended) / skip.
5. **External docs** — none / collect paths.

Behavior:

- Questions 1–3 need an answer. Questions 4–5 are skippable with defaults.
- Fires on v0.13.x→v0.14 upgrade too (`.context/` present, no `config.json`) — captures model + mode and does not force a re-ingest.
- `--reconfigure` re-runs all 5. (`config get/set` for surgical edits deferred to v0.16.)
- `dummyindex install --no-onboarding --defaults` writes a default `config.json` non-interactively, for CI / scripted runs.
- `config.json` carries `schema_version` for forward migration.

### Skill changes

- `council/20-specify.md`, `council/30-plan.md`, `council/40-critique.md` (these replace the old stage1/stage2/stage3 markdowns).
- `agents/dev.md` (parameterised), `agents/critic-database.md` / `critic-security.md` / `critic-product.md`. `agents/chairman.md` retired.
- New CLI: `dummyindex context dev-pick --feature ID` returns the picked stack persona for inspection. `dummyindex onboard` / `--reconfigure` drives the question flow. `dummyindex config show` prints the resolved config.

Gate: a 14-feature FastAPI repo runs onboarding (model + mode captured). Then in standard mode it produces `spec.md` + `plan.md` + `concerns.md` per non-trivial feature. The file `02-architect-notes.md` shows concrete revisions. The run has at least one `path:range`-cited critic finding for each critic dispatched.

## v0.15 — session memory + build loop + Equip v2 + MCP wiring ✅ shipped (2026-06-06)

Original scope was MCP-only. Shipped scope expanded (owner-approved) to include the full grounded build loop and session-memory subsystem.

**MCP wiring (Context7 + Sequential Thinking + GitHub):** the council procedures wire in three MCP servers when the runtime exposes them. Matching is namespace-tolerant: it matches the server *family*, not one exact prefix. There is a graceful single-shot fallback, so an absent server never fails a run. Protocols in `council/55-context7.md` + `council/56-github.md`.

**Session-memory subsystem (`/dummyindex-remember`):** markdown-first cross-session memory at `.context/session-memory/` (tiers `now.md` → `recent.md` → `archive.md` + `core-memories.md`). Seeded by `ingest`, never regenerated. `dummyindex context memory session-start|roll|init`. Suppresses itself when the `remember` plugin is present. Ships as its own top-level skill.

**Build loop — plan → equip → execute:** the original Claude loop plans,
renders `.context/`-grounded tools into `.claude/`, and executes through it.
The Codex adapter preserves the proposal/build contracts but deliberately skips
equip discovery/install/apply and executes through native built-in subagents.

**Equip v2 — codified, evolving toolkit engine:** `dummyindex context equip apply|status|refresh|reset|uninstall|patch`. Toolchain detection (stack, frameworks, runnable commands). Standard generated set: `<stack>-implementer/tester`, `<proj>-reviewer`, `<proj>-verify`. Adopt-existing specialists.

Evolution mechanics: per-item **origin-hash baselines** (pristine / user-modified / missing). The tool never stomps user edits. **Evolved-item protection** means patches survive apply/refresh. Only `reset` discards them. The **patch seam** is `equip patch --item N --from-file F`.

Formatter PostToolUse hook wired into `settings.json` under `DUMMYINDEX_EQUIP` sentinel. The manifest has since evolved to `equipment.json` schema v4.

**Deferred from v0.15:**
- Bespoke (non-template) tool generation — template-based generation shipped. Freeform generation deferred.
- Sequential Thinking deep wiring for all council phases — wired for the architect's structural review + plan revision. Full deep wiring deferred.

## v0.15.1–0.15.3 — commit-anchored reconcile + auto-handoff hooks ✅ shipped (2026-06-08)

- **Commit-anchored, non-destructive `.context/` update** — `.context/` tracks the commit it was last reconciled against (`meta.indexed_commit`, the "Model B" anchor). The `reconcile` / `reconcile-stamp` / `mark-enriched` verbs + `council/65-reconcile.md` fold a commit delta into the curated taxonomy and do not re-cluster. Only `ingest` and `reconcile-stamp` move the anchor (no hook may stamp it).
- **Auto-handoff hooks** — the core install now wires **three** Claude hooks. This supersedes v0.13.5's single `SessionStart`. The hooks are `SessionStart` (drift report), `Stop` (`memory nudge` handoff call to action), and `PreCompact` (`memory breadcrumb`). None rebuild the index.

## v0.17 — equip generates capability specialists ✅ shipped (2026-06-10)

- **Generated specialists** — `equip` now renders first-class, file-backed specialist agents (**db / security / performance / docs / search**). The agents are keyed by capability and grounded in the matching `.context/` docs. This goes beyond the v0.15 model, which only *adopted* a manifest-only registry pointer. Each carries the `<!-- dummyindex:generated -->` marker + `version`/`origin_hash`/`grounded_in`. Each participates identically in `status`/`refresh`/`reset`/`patch`/`uninstall`. It preserves origin-hash authority and never-clobber.
- **`equip add-specialist <capability>`** verb (+ `--specialist C` flag on `apply`) forces one explicitly. A plain `apply` generates every template-backed specialist regardless (no opt-in). A re-apply carries forward every specialist already applied (reconstructed from the manifest), so it never drops one.
- **`--for-proposal` upgraded** — a demanded capability a template backs now renders a **file**. A capability with **no** template (for example frontend → *Frontend Developer*) still **adopts** manifest-only (the unchanged fallback). Coverage precedence: project agent (adopt) → template (generate) → registry (adopt) → generic.
- **Capability-gap fix** — `rls`/`tenant`/`tenancy`/`isolation`/`rbac` now map to **security**. As a result, a migration proposal with RLS / tenant-isolation criticals (no literal "security") yields a security specialist.
- **No `equipment.json` schema change** — stays v2. Current four-core repos gain every template-backed specialist on their next apply (specialists are abilities, not opt-ins). They are stable across re-applies after that. The earlier deferral of *freeform* (non-template) generation stands — this is template-backed generation only.

## Shipped since v0.17

Releases after v0.17 that this guide does not break out into their own sections
above. Item names + version. See `CHANGELOG.md` for the per-release detail.

- **v0.19 — equip as a Claude plugin manager.** `dummyindex context equip discover` searches the seed marketplaces + GitHub. `equip install <plugin>@<marketplace>` wires a packaged plugin natively (`extraKnownMarketplaces` + `enabledPlugins`), trust-gated with blast-radius disclosure. Equip vendors loose agents/skills with an origin-hash marker. `equip verify` re-resolves an installed plugin read-only. v0.31 vendors external skills from trusted collections automatically.
- **v0.20 — parallel council dispatch.**
- **v0.21–0.26 — plugin usage playbooks + plan-time annotation.** `equip install` requires a `--usage-doc` playbook (`.context/equipment/<plugin>.md`). `equip status` flags undocumented plugins. `/dummyindex-plan` tags each task with the plugin command / skill that will run it. Default plugins wired into project `settings.json` on init.
- **v0.30 — context-hygiene GC.** `dummyindex context gc status|delete|stamp|signal` — deterministic support for the `/dummyindex-gc` skill's council-driven, user-confirmed sweep. The sweep deletes generated docs and never archives them.
- **v0.31 — equip trigger-eval / benchmark + managed doc homes.** `equip eval <tool> --observations FILE` and `equip benchmark <tool>` score generated tools. Installs refresh generated tools. `context migrate-docs` relocates stray planning docs that already exist. `context guard-doc-write` (PreToolUse write-guard) blocks new ones that land outside their managed `.context/` homes.
- **v0.32 — Codex support.** `install|uninstall|ingest --platform
  claude|codex|both`, native `.agents/skills/` discovery, `$dummyindex*`
  invocation, managed active project instruction guidance, and `current` model
  selection. Codex plan creates no Claude equipment. Codex build proceeds without
  `equipment.json` through `worker`/`explorer`/`default`.
  `$dummyindex-equip` is a non-mutating native routing report. Claude equip
  lifecycle and marketplace commands remain Claude-only.
- **Technical-debt ledger** — `dummyindex context debt` builds a ledger over the repo's `DEBT` comment markers (`.context/debt.md`).
- **Freshness statusline** — `dummyindex context statusline` prints the cached `.context/` freshness badge for Claude Code's `statusLine`.
- **PyPI distribution** — the CLI ships to PyPI via a release-gated GitHub Actions workflow (`uv tool install` / `pipx` / `pip --user`). `/dummyindex-update` upgrades an installed CLI in place.

## v0.16 — Polish + portability

Still deferred.

- Additional adapters beyond Claude Code and Codex (OpenCode, Cursor, Aider).
- CLI-prompt fallback for onboarding (the v0.14 question flow runs through stdin for terminal-only / non-Claude use).
- `dummyindex config get/set <key>` for surgical config edits, with no need to re-run the full onboarding flow. (`config show` ships. The project reserves `get`/`set` for a future release.)
- Cron mode: `dummyindex council --schedule weekly` for managed re-enrichment.

## v1 — Once I'm done testing

Promoted from v0.16 once the user has exercised the full stack on real repos.

## Beyond v1

- **Language-agnostic extraction** (originally planned as v0.8): LLM fallback for languages without tree-sitter grammars. Heuristic structure detection for config/shell/SQL/YAML. Per-language confidence stamps. Deferred — needs an LLM provider choice + design discussion before code.
- **Multi-repo / workspace**: workspace-level `.context/` that aggregates multiple repos.
- **Domain-specific personas**: detect stack (for example Solidity, Unity, K8s) and load extra personas.
- **Diff mode**: `dummyindex diff` shows what changed in `.context/` between two commits (great for PR reviews).
- **Council learning**: feed back which sections the agent referenced during real tasks. Reweight what to emphasize next time.
- **Sourced retrieval API**: every retrieval result carries the chain of nodes that led to it (for explainability).

## Won't do

- Code generation *by dummyindex itself* remains out of scope. The build loop generates tools that write code (owner-approved v0.15 scope change), but dummyindex is the orchestrator — not the author.
- Hosted service. dummyindex is local-first.
- Subscription model. MIT, install once.
- Vector store. The tree IS the retrieval index.

## Open questions

- Is the council pattern the right shape, or should we use a more rigorous "RFC + adversarial review" pattern?
- Should a human confirm the architect's regrouping before the system applies it, or should it be fully autonomous?
- Should `confidence` be more than `EXTRACTED / INFERRED / AMBIGUOUS`? (Numeric scores? Per-source attribution?)
- How do we handle private/proprietary code paths the persona should not write about (compliance contexts)?
- For polyglot repos, what is the right LLM extraction fallback — one-shot per file, or a multi-step structure inference?

These get answered as we use the system, not before.
