# Session memory & drift signal — plan

`confidence: INFERRED`

## Where it lives

**The invariant the boundary is drawn around.** Every module here *decides*, then *renders a fixed string*. None authors prose. The store relocates sections whose meaning it never reads. The miner emits policy lines it wrote itself, keyed by a validated slug, never transcript text (`miner/feedback.py:25-37,238-247`). Prose stays outside the boundary by design. It belongs to the `/dummyindex-remember` skill (`memory/__init__.py:1-5`).

Three nested contexts share the folder. They are separable, and that separation is load-bearing.

**A — the tier store** (`dummyindex/context/domains/memory/`). It is a repository over a closed set of markdown files. `store.py:11-31` locates and creates them without overwriting. `parse.py:24-49` splits and joins on `## ` headings. `roll.py:44-108` cascades by date. `emit.py:33-61` renders the SessionStart block. `breadcrumb.py:118-127` writes the PreCompact entry. `nudge.py:103-131` decides the Stop CTA. `detect.py:8-15` stands the whole thing down. `enums.py:8-39` is the closed alphabet (`MemoryTier`, `MemoryVerb`, `AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`). `models.py` holds the frozen carriers. `transcript.py:137-175` is the live-session adapter.

**B — the miner subpackage** (`memory/miner/`). It is a second bounded context nested in A's folder. It has its own `enums.py`, `models.py`, and resolution port (`resolve.py:44-67`). Its coupling to A is one import in each direction, and no more. A re-exports four miner symbols (`memory/__init__.py:18-23`). The miner reaches back exactly twice: `atomic_io` (`feedback.py:10`, `render.py:29`) and `store.memory_dir` (`render.py:30`). Two pipelines of the same shape (resolve → scan → group → write) sit side by side:

| Pipeline | Entry | Wired? | Modules |
|---|---|---|---|
| Skill-compliance feedback | `pipeline.scan_skill_feedback` / `refresh_skill_feedback` (`miner/pipeline.py:112-152`) | **yes** — SessionStart + UserPromptSubmit | `corrections.py` (grammar, 293 lines, largest in the feature), `feedback.py` (cache + projection), `scan.parse_skill_directive_events` (`miner/scan.py:262-297`) |
| Failure / loop patterns | `pipeline.scan_transcript_store` / `mine_and_feed` (`miner/pipeline.py:40-109`) | **no** — tests only | `signatures.py` (canonicalize + group), `render.py` (writes `failure-patterns.md`), `scan.parse_transcript` (`miner/scan.py:140-190`) |

Shared by both: `resolve.py` (config-dir and store resolution, honoring `CLAUDE_CONFIG_DIR`), `scan.discover_project_dirs`, and `scope.py` (scoping and redaction). The **wired** half touches nothing in A except `atomic_io`. The single `..store` edge (`render.py:30`) belongs entirely to the **unwired** half. Cutting the failure-pattern pipeline would leave the miner fully decoupled from the tier store.

`miner/__init__.py:1-33` carries the Apache-2.0 attribution for `headroomlabs-ai/headroom`. It also corrects an earlier docstring that overclaimed independence. The repo-root `NOTICE` is the license artifact.

**C — the staleness readers.** `context/drift.py` (`compute_drift` at `drift.py:152-265`) and `context/reconcile_gate.py` (`decide_block` at `reconcile_gate.py:342-399`) are two policies over one read model, not two models. Since the 2026-08 train, `compute_drift` classifies each row through a **basis → manifest → mtime fallback chain**. A `cache/doc-basis.json` entry decides the (feature, file) pair. It holds the stamp-time blob sha, read via `_read_doc_basis` `:489-521`. An equal sha suppresses the row as history-moved noise. An unequal sha is real drift. Pairs without a basis entry fall back to the manifest sha256 (`_content_unchanged`), then to legacy mtime-only. Still-valid `drift-ack` dismissals drop their rows last (`_drop_acked_rows`, `drift.py:524-555`).

**Boundary layer.** `cli/memory.py` is the 7-verb dispatcher over `MemoryVerb` (`cli/memory.py:73-195`). `cli/plan_update.py:68-100` and `cli/drift_ack.py:42-166` sit beside it. Hook wiring is generated in `context/hooks.py`. The event→verb map is the downstream contract:

| Hook event | Command | `hooks.py` |
|---|---|---|
| SessionStart | `plan-update`, `memory session-start`, `gc signal`, `memory mine` | `147-198` |
| UserPromptSubmit | turn reminder, `memory prompt-context` | `120-145` |
| Stop | `memory nudge`, `reconcile-gate` | `200-227` |
| PreCompact | `memory breadcrumb` | `229-243` |
| PreToolUse (`Write`) | `guard-doc-write` (shared hook-stdin adapter consumer) | `245-267` |

`plan-update` also serves two non-hook surfaces. The statusline badge cache it writes is echoed verbatim by `dummyindex context statusline` (`cli/statusline.py:37-66`) and by the shipped `statusline.sh` and `statusline.ps1` wrappers. Its new `--json` envelope (`plan_update.py:70-71,103-114`) serves scripts that must act per row, not read prose. `drift-ack` has no hook. It is an operator verb.

### Dependency direction

- **Upstream (this feature imports):** `build/manifest.read_manifest`, `build/reconcile.compute_reconcile_report` with `DOC_BASIS_REL`, `DOC_BASIS_VERSION`, and `blob_sha`, and `pipeline/io/detect.detect` (`drift.py:35-43`). Also `domains/drift_acks.read_acks` (`drift.py:42`), `pipeline/io.submodule_paths` (`reconcile_gate.py:36`), and `domains/atomic_io.write_text_atomic`, which every writer uses, including `drift_acks._write` (`drift_acks.py:107-111`). External and read-only: the host transcript store under `$CLAUDE_CONFIG_DIR` or `~/.claude`, and `git` via subprocess (`breadcrumb.py:57-95`). The doc-basis snapshot is written by `rebuild`'s `stamp_reconciled` (`build/reconcile.py:318-351`). Also `session_block` from `dummyindex/context/domains/probation` (feature `probation`, imported at `dummyindex/cli/memory.py:59-70`). The stamp is the producer. Drift only consumes.
- **Downstream — the CLI is not the only consumer.** Five in-tree modules import this feature directly. `context/build/runner.py` calls `ensure_memory_store` on **every rebuild**, so the store is seeded by build, not only by `memory init`. `cli/gc.py` reuses `resolve_session_id`. `cli/guard_doc_write.py` and `cli/reconcile_gate.py` import `read_hook_stdin` and `resolve_transcript` from `cli/memory.py:26-56`. That makes `cli/memory.py` the repo's shared hook-stdin adapter, not a private wire. Changing those two signatures breaks three other CLIs. The tier store also has a reader outside the hooks. The evolve domain's harvest parses correction sections out of `now.md` and `recent.md` into evidence items (`domains/evolve.py:_harvest_memory`, `:372-438`; `_MEMORY_TIERS` `:372`). A reformat of tier headings therefore feeds another feature's evidence pipeline.
- **Fan-in:** `read_session_signal` (`transcript.py:137-175`) has exactly three callers: `nudge.py:124`, `breadcrumb.py:97` (via `build_breadcrumb_facts`), and `reconcile_gate.py:387`.
- **Deliberate non-edge:** `transcript.py:5-8` refuses to import the `usage` domain. That keeps `cli → context → analysis → pipeline` acyclic.
- **Cycles: none.** `reconcile_gate.py:33-35` imports `memory.nudge`, `memory.transcript`, and `drift`. None of the three imports `reconcile_gate`. The miner imports the parent package only through `atomic_io` and `..store`. No `memory/*.py` module imports `miner` except the `__init__` re-export.
- **Map caveat (code wins, 2026-08-23).** `.context/meta.json` is anchored at `f8a8a33` (= HEAD). The deterministic backbone it stamps is polluted. `tree.json`'s root has the foreign `results/` tree as its only top-level child. `map/symbols.json` holds only ClickHouse and gtest symbols from `results/benchmarks/workspaces/`, with zero first-party Python symbols. Consequences: `feature.json.members` lists no miner or drift-engine symbols. The pre-rebuild staleness persists for a different reason: there is nothing to extract from. Every citation in this plan was checked against source at HEAD, not against the map. A scoped rebuild excluding `results/` closes this. See `concerns.md`.

## Architecture in three sentences

Four hook-driven mechanisms (tier store, drift report, reconcile gate, and skill-feedback miner) sit behind two emit-only CLI dispatchers. Each dispatcher parses args, calls one domain function, prints a fixed payload, and returns 0 unconditionally (`cli/memory.py:73-170`). Drift and gate are two policies over one read model. `compute_drift` feeds an advisory `render_drift_summary` at SessionStart, and an authoritative `_gate_relevant` → `decide_block` at Stop (`drift.py:152-265`, `reconcile_gate.py:321-399`). All live-session decisions come from the one stdlib-only `read_session_signal` (`transcript.py:137-175`). The miner runs an independent read-only pass over historical JSONL (`miner/scan.py:109-137`). It asks a different question of the same bytes.

## Data model

No relational store. Persistence splits into two classes with different rules, and the split is the design.

**Committed markdown, user-owned** — `.context/session-memory/`, one H1 plus zero or more `## …` sections per file (`parse.py:24-49`):

| File | Written by | Rolled by |
|---|---|---|
| `now.md` | agent handoffs + `(auto-breadcrumb)` entries (`breadcrumb.py:43-54`) | dated < today → `recent.md` |
| `recent.md` | roll only | dated < today−7 → `archive.md` |
| `archive.md` | roll only | terminal |
| `core-memories.md` | agent (promoted durable facts) | never rolled; emitted whole (`emit.py:42,51-52`) |
| `failure-patterns.md` | `miner/render.write_report:83` — full overwrite | never rolled; **nothing reads it** |

`failure-patterns.md` is deliberately not a `MemoryTier` member. Adding it would make `ensure_memory_store` stub it, which implies a lifecycle it does not have (`miner/render.py:11-17`). That exclusion lets `roll_tiers` and `render_session_start` iterate the enum and stay correct.

**Gitignored per-machine caches** — `.context/cache/` (`.gitignore:19`):

- `skill-feedback.json`: schema 1, keys `{schema_version, skills}` exactly, entries `{skill, corrections, sessions}`, at most 64 entries and 32 KiB, sorted by `(-corrections, skill)` (`feedback.py:14-23`).
- `nudge-state.json`: pruned to 100 sessions (`nudge.py:56-67`).
- `reconcile-gate-state.json`: same shape (`reconcile_gate.py:250-264`).
- `freshness-badge`: labeled badge text, e.g. `[ctx: 2 edited · 1 anchored]`. Written by `plan_update.py:35-51`, echoed by the statusline surfaces.
- `doc-basis.json`: `{basis_version, features{fid: {rel_path: blob_sha}}}`. Written only by `reconcile-stamp` (`build/reconcile.py:361-399`). Read corrupt-tolerantly by `drift._read_doc_basis`.
- `drift-acks.json`: append-only dismissals (`domains/drift_acks.py`).
- `manifest.json`: the sha256 oracle of the last fallback (`drift.py:472-486,558-572`).

**Read-only external input** — the host transcript store. Two readers exist on purpose. `transcript.py` serves the *live* session with coarse counts and edited paths. `miner/scan.py` serves *historical* mining.

**Transactions** — none in the DB sense. The equivalent discipline is tmp file plus `replace` on every write. `atomic_io._replace_bytes:13-34` names the temp file with `NamedTemporaryFile` and a unique suffix. Hooks from two Claude profiles can update the same repo-local cache concurrently (`atomic_io.py:14-18`).

⚠ `.context/conventions/data-access.md:7` still describes `write to path + ".tmp"` at `atomic_io.py:11-24`. That is stale on both mechanism and range. `write_text_atomic` is now `atomic_io.py:37-47`. **The code wins.**

Two write-elision guards keep the no-op path byte-free. `write_skill_feedback` compares before writing (`feedback.py:126-133`). `roll_tiers` returns before touching a file when nothing moved (`roll.py:81-82`).

## Key decisions

1. **Markdown-first, mechanics-only.** This is the boundary decision. The CLI relocates, prepends, and emits fixed strings. It never summarizes, because prose is the agent's job. A deterministic layer that authors text is unauditable (`memory/__init__.py:1-5`). Cost: the store cannot compress itself. Tiers grow until an agent rewrites them.
2. **The miner is a nested subpackage, not a sibling domain.** It gets its own `enums`, `models`, and `resolve` inside `memory/`, not a peer `domains/miner/`. It feeds the same store and shares the transcript substrate. Its import coupling is near zero. Two edges exist, and one sits only in the unwired half. The decision is cheap to reverse. Cost: `memory/` now holds two contexts under one folder name.
3. **Stdlib-only transcript reader, twice, rather than one shared reader.** `transcript.py:5-8` refuses `usage`, keeping `cli → context → analysis → pipeline` acyclic. The miner then re-reads JSONL a third time for a different question. Rejected: a unified reader. The live reader wants coarse aggregates over one file. The miner wants filtered rows across many. The layering forbids reaching into `usage`. Cost: no cross-transcript dedup.
4. **Privacy is structural, not a filter.** No raw prompt text survives parsing. `SkillDirectiveEvent` carries a sha256 `event_key` (`corrections.py:191-209`). `ToolCallRecord` carries `output_bytes`, not an excerpt. An earlier cut kept a 200-char sample and rendered it into a git-tracked file (`miner/models.py:11-27`). The failure-pattern renderer makes in-repo paths relative and *redacts* everything else (`scope.py:52-71`). Both guards exist because an audit found the first cut violating them.
5. **Scope every scan to one repo by default.** `project_dir_name` matches the store directory **exactly**, not by prefix. `-a-b-mono` and `-a-b-mono-backend` are different projects (`scope.py:41-49`). Cross-project pooling exists but must be named (`all_projects=True`, `pipeline.py:83-109`).
6. **Grammar over classification.** High-precision regexes match a small closed set of phrasings (`corrections.py:35-101`). Quoted and fenced text is stripped first. Within one prompt, the latest directive per skill wins (`corrections.py:181-188`). A revocation resets the counter for everything before it (`corrections.py:269-281`). Rejected: semantic or LLM classification. `headroom/learn/analyzer.py` was skipped for exactly this reason (`miner/__init__.py:29-32`). Cost: recall is whatever the five patterns cover.
7. **Two events, not one.** `DEFAULT_MIN_SKILL_CORRECTIONS = 2` (`miner/enums.py:38-40`). One request is ordinary task input. Two distinct human events are a compliance signal worth persisting. The current turn's directive is exempt and ranks above all history, so same-turn feedback applies at once (`feedback.py:226-236`).
8. **Fail-closed read, fail-open run.** `read_skill_feedback` rejects the whole file on any anomaly. Examples: wrong schema, symlink, non-regular file, oversize, duplicate slug, `sessions > corrections`, or wrong sort order (`feedback.py:136-200`). Both new CLI verbs swallow every exception and exit 0 (`cli/memory.py:101-142`). Generated feedback must never block a session. Malformed generated feedback must never reach a prompt.
9. **Prompt cost bounded twice, scan cost bounded once.** The cache caps at 64 entries and 32 KiB. The projection caps at 8 skills and 1600 chars, with a line-by-line length check (`feedback.py:243-246`). `_iter_skill_json_lines` rejects non-candidate rows by substring before `json.loads` (`miner/scan.py:109-137`). `_resolved_cwd_matches` skips a filesystem `resolve()` for an already-absolute path (`scan.py:193-206`). That matters on the mounted Windows filesystem this repo lives on.
10. **Structured field-dropping instead of string regex.** dummyindex tools pass structured JSON. The signature drops three unambiguous pagination fields (`offset`, `limit`, `head_limit`) and keeps every other field byte-for-byte. `n` and `count` were removed after an audit found them merging unrelated MCP calls (`signatures.py:43-50,68-99`). Bash keeps headroom's lossy treatment, because a shell command is opaque text.
11. **Hooks never fail; side effects fire once.** Every hook verb returns 0 (`cli/memory.py:108,142,156,163,170`). Nudge and gate key on `session_id` and an LRU-pruned JSON memo, so a re-entrant Stop never double-fires (`nudge.py:56-67`, `reconcile_gate.py:250-264`).
12. **Four-oracle staleness, classified not boolean.** mtime is a decaying advisory. The doc-basis snapshot written at the stamp boundary is the per-(feature, file) authority. A match *suppresses* an mtime row as history-moved noise rather than reporting it. The manifest sha kills git-op false positives for basis-less pairs (`drift.py:192-243`). A live `meta.indexed_commit` anchor remains the authoritative reconcile boundary. With an anchor, the gate ignores mtime-only drift, and SessionStart surfaces it (`reconcile_gate.py:267-276,321-339`). A fifth, user-supplied overlay, the `drift-ack` store, dismisses known-good rows until their bytes change. Every reader returns `False` or `{}` on doubt (`_content_unchanged`, `_read_doc_basis`, `read_acks`). A hashing failure reports rather than hides.
13. **Stand down for `remember`.** Presence of `<root>/.remember/` short-circuits emit, nudge, and breadcrumb before any work (`detect.py:8-15`, gated at `emit.py:34`, `nudge.py:115`, `breadcrumb.py:121`). The two miner verbs do **not** check it. Skill-compliance feedback is orthogonal to handoff injection, so there is no competing block to solve.

## Placement (reconcile 2026-08-23)

- **Newly owned but unplaced:** `dummyindex/context/domains/drift_acks.py` and `dummyindex/cli/drift_ack.py`. This train created them for this feature's drift engine. `context/drift.py` imports the domain, and the CLI verb exists only to serve it. Both are absent from `feature.json` `files` and `members`. They belong here at the next placement pass. `drift_acks._write` reuses this feature's `atomic_io`, consistent with the A-boundary.
- **Foreign or unowned — do not claim:** `benchmarks/`, `tests/benchmarks/`, and `results/` belong to a separate benchmarking workstream. They sit only in raw `community-*` clusters. None may be absorbed into this feature. The polluted backbone (see Map caveat) sweeps `results/` into every deterministic artefact anyway.
- **Adjacent but not ours:** `domains/evolve.py` consumes this feature's tier store as evidence (`_harvest_memory`). It is placed under the `equip` feature. It is recorded as a downstream consumer above, not claimed as a member.

## Open questions

- **The failure-pattern half of the miner has no caller.** `mine_and_feed`, `scan_transcript_store`, and `render.write_report` are reachable only from `tests/context/domains/memory/miner/`. `memory mine` calls `refresh_skill_feedback` instead (`cli/memory.py:103-105`). `memory/__init__.py:18-23` re-exports only the four skill-feedback symbols. Whether it gets a verb, a consumer for `failure-patterns.md`, or deletion is undecided from the code alone. See decision 2.
- **Tuning constants stay hardcoded.** `LONG_OUTPUT_TOKENS = 40_000` (`nudge.py:23`), `recent_keep_days = 7` (`roll.py:48`), `DEFAULT_MIN_SKILL_CORRECTIONS = 2` (`miner/enums.py:40`), and `MAX_PROMPT_SKILLS = 8` / `MAX_PROMPT_CHARS = 1600` (`feedback.py:18-19`). `.context/config.json` already carries `auto_council` (`reconcile_gate.py:39-45`), so a surfacing path exists. Nothing uses it here.
- **Nothing ages skill feedback out.** `aggregate_skill_corrections` counts every post-revocation event in every retained transcript, with no time window (`corrections.py:269-281`). A year-old correction still promotes a skill until the user revokes it or the transcripts are deleted. Whether that durability is intended, or decay is missing, is not answerable from the code.
- **Multi-profile union is broad.** `resolve_claude_config_dirs` globs every `~/.claude-*` directory (`resolve.py:47-56`). An abandoned profile contributes events for this repo. Dedup is by `event_key`, which does not collapse the same prompt copied across profiles with different `uuid`s (`corrections.py:198-209`).
- **`_ERROR_MARKERS` is a hand-picked substring list** (`miner/scan.py:29-41`), applied to the first 1000 chars of a tool result. Its false-positive rate on output that merely mentions "error:" is unmeasured. It is harmless only because nothing consumes the failure-pattern output.
- **Stale-doc flag (code wins).** Catalogued plans (`docs/internal/plans/01-session-memory.md`, `docs/plans/2026-06-08-auto-handoff-nudge.md`, `docs/plans/2026-06-11-auto-council-drift-hook.md`, all `DocConfidence.MEDIUM` with broken refs) reference a `SessionMemoryError` typed exception. That exception does not exist. Error handling here is plain returns, `()` sentinels, and 0-exits, with no domain exception hierarchy. Treat the doc claim as stale. See also the `data-access.md` conflict under Data model.
