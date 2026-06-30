# Full audit — 2026-06-13 (overnight autonomous run)

**Mandate (from Ahmed):** dummyindex is a plugin manager at its core + context management system (drop into existing apps, map them, create curated `.claude` setup). Audit everything, fix everything found, commit locally (NO push). Mine the BOS-Mono (+submodule) chat transcripts for what it's struggling with. Three focus areas:
1. Installing skills/plugins/agents (+ decide on a directory & sources document)
2. Building/managing `.context` (including updates)
3. Wiring in specific plugins, installing them, using them correctly (known struggle)

**Method:** transcript mining (evidence) → live-state inspection of BOS-Mono + submodules → codebase audit grounded in evidence → prioritized fixes with tests → local commits.

---

## Log

### Phase 0 — Setup
- Located session transcripts: ~28 relevant files across `-mnt-windows-ssd-Projects-opensession-BOS-Mono{,-backend,-frontend}` (June 2–13). Heaviest usage June 8–13 in backend/frontend submodules.
- Noted immediately: **dummyindex itself has no `.context/`** even though its own `.claude/CLAUDE.md` tells every session to read `.context/HOW_TO_USE.md` — the tool isn't dogfooded on its own repo. (candidate fix)
- BOS-Mono root `.context/` contains only `docs/` and `memory/` — not the dummyindex taxonomy (INDEX.md, PROJECT.md, features/). Needs live-state inspection.

### Phase A — Evidence mining (launched)
- Workflow `wf_7327feb5-a17`: 30 transcript-mining agents (one per session with ≥11 dummyindex mentions, June 2–13) + 4 live-state inspectors (BOS-Mono root, backend submodule, frontend submodule, CLI install integrity). Structured findings schema (category × severity × verbatim evidence).
- Mapped the codebase while waiting: `dummyindex/` = analysis, cli (30+ subcommand modules), context (build/, domains/ incl. equip with plugins/{discover,marketplace,install_plan,blast_radius}, output/, reconcile_gate), export, installer, pipeline (extract/build/io), skills (7 SKILL.md), usage. 73 test files. v0.25.0.
- Read `dummyindex/skills/equip/SKILL.md` (422 lines) — the plugin-manager spec: two discovery channels (marketplaces via `equip discover/install`, skills.sh via `npx skills`), tiered trust, blast radius, usage-interview requirement, hybrid wiring (native settings.json vs vendored).

### Phase A — results (complete)
- 33/34 mining reports returned (1 retried separately), **325 raw issues**: 17 critical, 87 high, 145 medium, 76 low.
- Full evidence: `docs/audits/2026-06-13-evidence/raw-findings.json`; one-line digest: `…/digest.md`; per-cluster: `…/clusters/`.
- **Root-cause clusters identified:**
  - **C1 Destructive rebuild (CRITICAL):** `rebuild --changed`, full rebuild, and bare `dummyindex install` re-shatter the curated feature taxonomy into community-N stubs (5 criticals across 5 sessions; happened on frontend with 838 phantom features, COMMITTED). Docs/skills *prescribe* the destructive command as remediation. Also: `rebuild --changed` never ADDS new files (manifest-seeded discovery), meta.json version stamp never advances on the non-destructive path.
  - **C2 equip manifest integrity (CRITICAL):** `equip apply`/`add-specialist` rewrites equipment.json from scratch → silently drops plugin install records, vendored skills, specialists (confirmed in both submodules' live state). Duplicate conflicting entries; `path:""` contract violations; grounded_in pointing at nonexistent files.
  - **C3 Reconcile/drift/gate:** dummyindex's own generated files permanently pollute drift (no ignore mechanism); reconcile-stamp refuses → --force with misleading warning; Stop gate blocks planning-only/git-only sessions and violates block-once; 3 contradictory drift oracles (mtime vs commit-anchor vs content hash); rebase orphans the commit anchor; stamp can silently zero real drift.
  - **C4 Plugin manager (user priority #3):** discover ignores query/--repo (obra/superpowers never surfaced), capability tags wrong/non-deterministic; install can't resolve marketplaces Claude already knows; trust gate blocks already-enabled plugins; manifest entries near-empty (kind 'agent', capabilities [], null version) → unusable for routing; inconsistent wiring targets (settings.json vs settings.local.json); no post-install verification (canvas-to-code wired but NEVER invoked — build hand-simulated it); no duplicate-scope detection.
  - **C5 CLI help & safety:** NO subcommand supports --help (hit in 12+ sessions); bare `equip` runs a full apply and bare `install` runs the destructive install when probed for usage; help text 2 releases stale (no equip discover/install, no build --next-wave, says schema v2 while writing v3); no status verb.
  - **C6 Installer/version skew:** 4-layer version skew (CLI/skills/repo-dep/.context stamp) with no staleness detection; venv-pinned stale CLI shadows global; install rewrote settings.json and DROPPED a user Stop hook; .tmpl artifacts shipped that nothing reads.
  - **C7 Build routing/dispatch:** item→agent matcher never binds impl items to the generated implementer (everything → general-purpose); 'Frontend Developer' adopted for a pure-backend FastAPI repo; '— via' tags were hints not directives (user hand-patched the skill); skill-only plugins undispatchable; critique panel hardcodes nonexistent subagent types; enum reprs leak into JSON (SubagentType.AI).
  - **C8 Council/reality-check:** false contradictions from basename misresolution (100% FP run on record); --demote has no inverse; council-batch frontier can't re-enrich drifted-but-complete features and can't be scoped.
  - **C9 Submodules/monorepo:** preflight says 'not a git repo' inside submodules; parent-root sessions bypass all wiring; no foreign-.context ownership guard (BOS-Mono root has a foreign .context/ that dummyindex would claim).
  - **C10 Skills/docs consistency:** documented remediation commands are destructive or nonexistent (`/dummyindex --recouncil` not a verb); skills lag CLI; user hand-patched shipped SKILL.md (uncommitted divergence in ~/.claude).
  - **C11 Generated-output hygiene:** .context output trips pre-commit (trailing whitespace, no EOF newline, ~140 detect-secrets hits on sha256 hashes); ephemeral _enrich_plan.json not cleaned/ignored; giant unreviewable diffs (113k-line symbol-graph churn).

### Phase B — code investigation (launched)
- 11 investigator agents, one per cluster, confirming each symptom in code (file:line), producing fix plans + test plans. Baseline test suite run in parallel.

### Phase B — results so far
- Baseline test suite: **1122 passed** (pre-change).
- Retried miner folded in → corpus now **339 issues** (commit 46b5cec). New angles: blast-radius disclosure missing at USE time; rejected-but-already-executed MCP writes; plans prescribing uninstalled tools (Supabase CLI GATE); deploy-skew window (user hit live 500s); no skip-with-reason on checklist items; reconcile distrust (skill/CLI contradict on close-the-loop command).
- Sources catalog shipped: `docs/sources/installable-sources.md` (commit 2227ddd) — 34 sources, 18 verified native marketplaces, 2 seed-drift bugs found in SEED_MARKETPLACES itself.
- 8/11 fix plans landed (commit 0dcdcd6), **57 confirmed defects** + quick wins; 3 investigators (C1 destructive-rebuild, C3 reconcile-gate, C10 skills-docs) hit a session limit — resumed (run wf_5c8fe046-92d).
- Notable confirmations: `_apply_write` rebuilds equipment.json from scratch (reproduced at HEAD — marketplace/vendored/installed records all drop); `dummyindex install` runs a full destructive .context rebuild as a side effect AND rewrote settings.json dropping a user Stop hook; bare `equip` executes a full apply; reality-check basename misresolution reproduced.

### Phase C — implementation Wave 1 (launched, run wf_c1a77b4f-0c8)
- 5 parallel TDD agents on disjoint file sets, no commits (I review + commit per cluster after the wave):
  - **fix:equip-domain** — C2 manifest merge (P0), C4 plugin manager (2×P0: marketplace resolution from existing settings.json; post-install load verification), Frontend-Developer-adoption stack-sanity fix, SEED_MARKETPLACES drift fixes + 8 new verified seeds.
  - **fix:council** — C8 reality-check false contradictions (P0), demote inverse, council-batch scoping, enum-repr leaks, audit persona resolution.
  - **fix:submodules** — C9 foreign-.context ownership guard, .git-file submodule detection, index.lock guidance.
  - **fix:hygiene** — C11 pre-commit-clean writers, secrets-safe hashes, ephemeral cleanup, machine-layer gitignore, egg-info/build untracked, .tmpl shipping stop.
  - **fix:build-routing** — C7 item-kind-aware matcher (no more general-purpose fallback for impl items), GATE/via items not dispatchable, '— via' binding, skip-with-reason verb.
- Wave 2 planned after Wave 1 + remaining plans: C1 destructive rebuild, C3 reconcile/drift/gate, C6 installer (settings-preserving, no side-effect rebuild), then C5 CLI --help/safety (touches every parser), then C10 skills/docs alignment last.

### Phase C — Wave 1 COMMITTED (5 cluster commits)
- Full suite green after wave: **1322 passed** (+200 vs baseline). Reviewer (python-reviewer agent) ran over the diff; applied its real findings before commit: reality_check `.value` explicitness, council-batch backfill-warning scope bug (passed all_ids → scoped feature_ids), audit-roster excludes legacy v3 marketplace plugins (kind=agent seam bug, + regression test). Rejected its CRLF/atomic_io flag (artifacts are LF-only; suggested fix contradicted the documented contract) and its council backfill-marker flag (false positive — the deterministic builder never writes plan.md/concerns.md, so existence-without-spec-marker is the correct enrichment signal).
- Commits: `941de86` equip (C2+C4 manifest merge, plugin discover/install, seeds), `6441a82` council (C8 reality-check FP, scoped recouncil, enum leaks), `4cff59b` preflight (C9 submodule detection, foreign-.context guard), `efc8e84` build (C7 item-kind routing, non-dispatchable gates, binding via-tags + skip verb), `7a9b1bd` context (C11 pre-commit-clean output, no inert templates, egg-info/build removed).

### Phase D — Wave 2 (launched, run wf_6304cd50-917)
- **fix:rebuild+installer** (C1+C6, the data-loss footgun): public enriched-index guard + extend it so a shattered INDEX.json can't disarm it (scan curated feature dirs on disk); install/init/bare-rebuild refuse to clobber a curated index; install preserves user hooks in settings.json; meta version stamp advances on the non-destructive path; version-skew detection in `check`.
- **fix:reconcile-gate** (C3, 2×P0): exclude dummyindex's own files from reconcile delta + drift; rebase-orphaned anchor reports honestly instead of false all-clear; Stop gate stops blocking no-source sessions; stamp validates before advancing.

### Phase D — Wave 2 COMMITTED (2 cluster commits)
- One cross-agent seam failure caught by the full suite (reconcile-gate e2e): the gate now requires THIS session to have edited source, so the old test's edits-free 100k-token transcript correctly no longer blocks. Updated the test to represent a genuine source-drifting session + added a sibling test pinning the planning-only no-block behavior.
- Reviewer (python-reviewer) over the Wave 2 diff found 3 [BLOCK]s; 2 real, fixed before commit: (a) subagent-only sessions (`/dummyindex-build`) escaped the gate because edits live in subagent transcripts not the main one → `_session_drifted_source` now treats subagent activity as source-drift-plausible; (b) `hooks install` falsely reported "refreshed" forever once a user co-located a hook → now classified by real on-disk byte change (removed the dead `_managed_entry_body` helper). Third [BLOCK] (ruff format) rejected — repo enforces `ruff check` (passes), not `ruff format`. Regression tests added for both.
- Full suite **1406 passed**. Commits: `3b798f9` rebuild+installer (C1+C6), `205cc35` reconcile/drift/gate (C3).

### Phase E — Wave 3 (launched, run wf_d2a9e063-e85)
- **fix:cli-help-safety** (C5), run alone (touches every CLI parser): uniform `--help`/-h across all subcommands; bare `equip` no longer runs a full apply (safety); read-only `status` verb; usage pointers on mandatory-flag errors; doc-sync test so help can't drift; `/dummyindex usage chat` verb-recognition fix. Told it schema is now v4 and several quick-wins are already done in Waves 1–2.
- Wave 4 next: C10 docs/skills alignment, run AFTER C5 so docs describe the finalized CLI surface.

### Phase E — Wave 3 COMMITTED (`9183587`)
- C5 CLI help/safety: full suite **1519 passed** (+113). Verified end-to-end: `context equip --help` now prints usage (was exit 2); bare `context equip` exits 2 without creating `.context` (the probe-mutates-state bug); new read-only `context status`; ruff clean. Reviewed the central dispatch help-interception myself (read-only, value-aware, runs before any handler) — clean. Adopted `usage_error` (with `--help` pointer) across features/build/council-batch/conventions/audit/equip. Doc-sync test parametrized over every verb/flag guards against future drift.

### Phase F — Wave 4 (launched, run wf_5feeff8d-e06) — FINAL code/docs wave
- **fix:skills-docs** (C10), alone: remove destructive/nonexistent remedies from shipped skills + generated docs (`install --scope user` skew banner → `check --versions` diagnose; `/dummyindex --recouncil` → real `council-batch --feature --force`); make generated HOW_TO_USE/CLAUDE.md/PROJECT.md prescribe the correct, reassured-non-destructive update path; align build close-the-loop message with SKILL.md; fix plan critique-panel hardcoded nonexistent subagent_types; fold the `— via` anti-substitution gate into build SKILL.md; feature.json trivial-filter field names; new skills-doc-hygiene regression test. Told it the full post-Waves-1-3 CLI reality (schema v4, all new verbs, guards).
- After Wave 4: final full-diff review (HEAD vs pre-audit baseline) as a safety net, consolidated report, memory note.

### Phase F — Wave 4 COMMITTED (`e407f9e`)
- C10 docs/skills alignment: full suite **1539**. Fixed the destructive/nonexistent remedies (`install --scope user` skew banner → `check --versions`; `/dummyindex --recouncil` → real `council-batch --feature --force`), the generated-doc two-layer update contract (reconcile read-only + reassured non-destructive), build close-the-loop ↔ SKILL.md agreement, plan critique-panel hardcoded subagent_types, the `— via` anti-substitution gate, feature.json field-name doc. New `tests/test_skills_doc_hygiene.py`. I fixed a residual it flagged (help.py build --status text still said `rebuild --changed` → now `reconcile`, locked by a doc-sync test).

### Phase G — Final cumulative cross-wave review + fixes COMMITTED (`0bda8c8`)
- 4 reviewers over the entire audit diff (HEAD vs baseline `755e59b`) targeting cross-wave integration seams. Found 8 real ones; all fixed with regression tests:
  - **HIGH** — build `_dispatchable` excluded plugins by kind only; a legacy v3 plugin (kind=agent, source=marketplace) could leak into the dispatch pool → added the SOURCE guard (mirrors the audit roster).
  - **HIGH** — `output/docs.py` generated INDEX.md still described bare `rebuild` as the non-destructive full re-cluster (Wave-4 missed this template) → aligned to the guarded reality.
  - **MED** — `read_manifest` let an unknown-enum ValueError escape `except EquipError` callers → normalized to EquipError (forward-compat chokepoint).
  - **MED** — rebuild desync warning pointed at `refresh-indexes` (wrong direction) → now restore-from-git / `--full`.
  - **MED** — `_wants_help` could swallow a help request after a boolean-in-this-subcommand value-flag (`build --status --help`) → biases to help.
  - **LOW** — gate non-source prefixes missing `.claude-design` (reconcile had it) → aligned + consistency test; council-batch `--help` USAGE missing `--feature`/`--force` → added + doc-sync assertion.
  - Deferred (LOW/uncertain): GC of stale-named generated manifest records after a specialist rename — design tradeoff of the no-silently-drop merge; noted as a follow-up.
- Full suite **1545 passed**, ruff clean.

## FINAL STATE
- **13 fix commits + audit docs, all local on `main`, nothing pushed.** Baseline `755e59b` → HEAD.
- Tests **1122 → 1545**. Every wave TDD + python-reviewer'd; cross-wave seams caught by the cumulative review and fixed.
- Deliverables: this log, `docs/audits/2026-06-13-REPORT.md` (consolidated), `docs/audits/2026-06-13-evidence/` (corpus + fix plans), `docs/sources/installable-sources.md` (catalog).
- **Action required by user:** the installed CLI is a copy — reinstall to make fixes live: `uv tool install --force --editable /mnt/windows-ssd/Projects/memory/dummyindex`, then `dummyindex context check --versions`.
- **Open recommendation:** dogfood `.context` on dummyindex itself (its CLAUDE.md references a `.context/HOW_TO_USE.md` that doesn't exist) — left to the user since indexing is a large generated commit.
