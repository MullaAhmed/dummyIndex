# Architect notes — Session memory & drift signal

## What I changed

- Plan went from 337 lines / 2616 words to 303 lines / 2180 words. The section set and the `confidence: INFERRED` line are unchanged; `spec.md` and all source are untouched.
- **Fixed an invented claim.** The draft said keeping `failure-patterns.md` out of `MemoryTier` "lets `roll_tiers` and `render_session_start` iterate the enum". Neither one iterates it: `ensure_memory_store` is the only iterator (`store.py:25`), and roll/emit name their members explicitly (`roll.py:60-62`, `emit.py:40-42`).
- **Fixed the placement open question.** `drift_acks.py`, `cli/drift_ack.py` and `reconcile_scope.py` are already placed under `maintenance`, `cli/reconcile_gate.py` under `cli-dispatch`, and `hooks.py` under `equip` and `install-surface`. The real noise is `dummyindex/pipeline/enums.py` (only `ConfidenceLevel`) in this feature's `files`: nothing here imports it, yet its edits count as drift for this feature.
- **Fixed "two emit-only dispatchers".** There is one verb dispatcher (`cli/memory.py:59-180`) plus single-verb wrappers. "Hooks never fail" now rests on its actual two layers: the shell `|| true` + `exit 0` (`hooks.py:120-243`) and the Python `return 0`. Only `mine`, `prompt-context` and the badge write catch exceptions in-process.
- **Surfaced a doc/code conflict inside drift.** A pair covered by doc-basis whose sha differs reports regardless of doc mtime (`drift.py:217-232`). That contradicts the module docstring's decay claim (`drift.py:10-15`). Code wins; this is now part of decision 11.
- **Added an open question: slug encoding diverges.** `project_dir_name` (`scope.py:51-55`) handles only separators and the drive colon. `_encode_slug` and `usage.encode_project_slug` replace every non-alphanumeric character. evidence and evolve try both encodings; the skill-feedback miner tries only the first (`pipeline.py:122-126`). This is not confirmed against a real transcript store.
- **Added open questions:** whether to move the shared hook-stdin adapter, and the fact that `render_advisory_block` still emits `decision: block`.
- **Cut and merged:** draft decisions 8+9 are now #8, and 11+12 were folded into #10/#11, so 14 decisions became 13. The attribution paragraph is one sentence. The prose list of caches is now a writer→reader table. The paragraph on plan-update's extra surfaces is down to 3 lines.
- **Verification:**
  - Every kept `path:range` was re-read against source at HEAD `0634bfd`.
  - `map/symbols.json` is current (miner symbols are present), and every named function or class resolves in it.
  - Constants (`AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`, `DEFAULT_MIN_SKILL_CORRECTIONS`, `LONG_OUTPUT_TOKENS`, `MAX_PROMPT_*`, `_ERROR_MARKERS`, `_MEMORY_TIERS`) are absent from the map by construction, so they were checked in source.
  - Doc evidence: only the three `MEDIUM` plans are cited, and only as stale (`SessionMemoryError` has 0 source hits). The convention-range conflicts (`data-access.md:7,9`, `coding-practices.md:75`) are flagged in Data model.

## Patterns named

- **Repository over a closed file set:** `store.py:11-31` + `parse.py:24-70` + alphabet `enums.py:8-39`.
- **Verb dispatcher over a closed enum:** `cli/memory.py:59-180` over `MemoryVerb` (`enums.py:17-26`).
- **Decide → render → print hook adapter:** stated at `reconcile_gate.py:11-13` ("Mirrors `memory/nudge.py`").
- **Pipeline, two instances (resolve → scan → group → write):** `miner/pipeline.py:1-12,40-152`.
- **One read model, two policies:** `compute_drift` → `render_drift_summary` / `_gate_relevant` → `decide_block`.
- **Fallback chain basis → manifest → mtime → ack:** `drift.py:192-255`.
- **Per-session idempotency memo, LRU-pruned to 100:** `nudge.py:56-67`, `reconcile_gate.py:254-268`.
- **Fail-closed validating reader:** `feedback.py:136-200`.
- **Write-elision:** `feedback.py:126-129`, `roll.py:81-82`.
- **Feature-detect stand-down:** `detect.py:8-15`.
- **Host-store seam with an exclusive override:** `resolve.py:25-67`, `:40-45`.
- **Shared kernel:** `atomic_io.py:1-5`, imported by 34 modules outside this feature.

## Dependencies surfaced

- **New downstream edges the draft lacked:**
  - `domains/evidence.py:20` and `domains/evolve.py:501` → `miner/scope.project_dir_name`
  - `domains/debt/harvest.py:24` → private `drift._rel_or_none`
  - `cli/drift_ack.py:100` → `compute_drift`
  - `build/upgrade.py:36` → private `atomic_io._replace_bytes` and `is_link`
- **Hidden coupling with no import edge:** `evolve._harvest_memory` (`evolve.py:321-385`) re-implements the `## ` section split and hardcodes the tier filenames.
- **Convention conflict:** `cli/memory.py`'s sibling-CLI imports (`cli/reconcile_gate.py:13`, `cli/guard_doc_write.py:27`) break folder-organization §2. This is already flagged at `folder-organization.md:77-83`, but that doc cites `:12`; the live line is `:13`.
- **Duplicated host resolution:**
  - `CLAUDE_CONFIG_DIR` is read in two places: `transcript.py:57-60` and `resolve.py:25-31`.
  - `resolve_session_id` exists twice: `transcript.py:52`, `usage/transcripts.py:43`.
- **Producer of drift's oracles:** `stamp_reconciled` (`build/reconcile.py:301-394`). `manifest.json` is also written by `build_all` (`runner.py:307-316`).
- **Cycles:** none, re-verified. `memory/` imports only stdlib, `atomic_io`, and modules within its own package.

## Decisions promoted

- Decided the manifest advances only with the anchor and never on refresh, because refreshing it "would erase the very edit that triggered the rebuild" (`build/reconcile.py:365-370`).
- Decided a basis mismatch outranks doc mtime: the stamp is the "docs describe these bytes" record (`drift.py:86-88`), so only a stamp or an ack clears it.
- Decided `mine` / `prompt-context` catch in-process, because "generated feedback must never block SessionStart" (`cli/memory.py:94`). The other verbs rely on the shell guard.
- Decided against cross-transcript dedup in the live reader, because "a per-file sum is sufficient" (`transcript.py:7-8`). The cost is the duplicated resolution listed above.
- Grounded decision 4's audit provenance in `scope.py:3-22`, and decision 1's no-compression rule in `roll.py:5-6`.
