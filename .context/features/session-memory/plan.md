# Session memory & drift signal — plan

`confidence: INFERRED`

## Where it lives

**Boundary invariant.** Every module here decides, then renders a fixed
string; none authors prose (`dummyindex/context/domains/memory/__init__.py:1-5`). The store relocates
sections without reading their meaning; the miner emits policy lines it wrote
itself, keyed by a validated slug, never transcript text
(`miner/feedback.py:25-37,238-247`). Prose belongs to `/dummyindex-remember`.

Three nested contexts, separable along the import graph:

**A — tier store** (`context/domains/memory/`). Repository over a closed file
set: `store.py:11-31` locates and non-destructively seeds, `parse.py:24-70`
(de)serializes on `## ` headings, `roll.py:44-108` cascades by date,
`emit.py:33-61` renders SessionStart, `breadcrumb.py:118-127` writes PreCompact,
`nudge.py:103-131` decides the Stop CTA, `detect.py:8-15` stands all three
down. `dummyindex/context/domains/memory/enums.py:8-39` is the alphabet (`MemoryTier`, `MemoryVerb`,
`AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`); `transcript.py:123-161` is the
live-session reader. A imports only stdlib and `atomic_io`.

**B — miner** (`memory/miner/`). Its own `enums`, `models`, and host-store
seam (`resolve.py:18-60`; override is exclusive, `:33-38`). Coupling to A: A
re-exports four skill-feedback symbols (`dummyindex/context/domains/memory/__init__.py:18-23`); B reaches
back only for `atomic_io` (`feedback.py:10`, `render.py:14`) and
`store.memory_dir` (`render.py:15`). Two instances of one pipeline shape,
resolve → scan → group → write (`miner/pipeline.py:1-7`):

| Pipeline | Entry | Wired? | Own modules |
|---|---|---|---|
| Skill-compliance feedback | `scan_skill_feedback` / `refresh_skill_feedback` (`pipeline.py:100-140`) | **yes** — `mine`, `prompt-context` | `corrections.py`, `feedback.py`, `scan.parse_skill_directive_events` (`scan.py:244-279`) |
| Failure / loop patterns | `scan_transcript_store` / `mine_and_feed` (`pipeline.py:35-97`) | **no** — tests only | `signatures.py`, `render.py`, `scan.parse_transcript` (`scan.py:124-172`) |

Shared: `resolve.py`, `scope.py`, `scan.discover_project_dirs`. The lone
`..store` edge sits in the unwired half; without it B touches A only through
`atomic_io`. Apache-2.0 port of `headroomlabs-ai/headroom`
(`dummyindex/context/domains/memory/miner/__init__.py:1-16`; repo-root `NOTICE`).

**C — staleness readers.** `compute_drift` (`drift.py:115-220`) and
`decide_block` (`reconcile_gate.py:307-388`): one read model, two policies.
Ownership partitioning (`reconcile_scope.py:13-98`) and the ack store
(`domains/drift_acks.py`, `cli/drift_ack.py`) are imported here but placed
under `maintenance`.

**Boundary layer.** One verb dispatcher over `MemoryVerb`
(`cli/memory.py:53-174`) plus single-verb wrappers `cli/plan_update.py:44-74`
and `dummyindex/cli/reconcile_gate.py:16-36` (placed under `cli-dispatch`). The generated
hook wiring (`context/hooks.py`, placed under `equip`/`install-surface`) is
the downstream contract:

| Hook event | Command(s) | `hooks.py` |
|---|---|---|
| SessionStart | `plan-update`, `memory session-start`, `gc signal`, `memory mine` | `104-153` |
| UserPromptSubmit | turn reminder, `memory prompt-context` | `77-102` |
| Stop | `memory nudge`, `reconcile-gate` | `155-182` |
| PreCompact | `memory breadcrumb` | `184-198` |
| PreToolUse (`Write`) | `guard-doc-write` (consumes `read_hook_stdin`) | `200-220` |

`plan-update` also caches the statusline badge (`plan_update.py:32-41,62-65`)
that `context statusline` echoes verbatim (`cli/statusline.py:23-50`); its
`--json` envelope (`plan_update.py:77-88`) serves scripts. `drift-ack` is an
operator verb with no hook.

### Dependency direction

- **Upstream:** `build/manifest.read_manifest`; `build/reconcile`
  (`compute_reconcile_report`, `blob_sha`, `DOC_BASIS_REL`/`DOC_BASIS_VERSION`,
  `is_non_source_path`); `pipeline/io/detect.detect`; `drift_acks.read_acks`;
  `reconcile_scope`; `pipeline/io.submodule_paths` (`drift.py:19-27`,
  `reconcile_gate.py:17-29`). External, read-only: the host transcript store
  and `git` via subprocess (`breadcrumb.py:57-94`). `stamp_reconciled`
  (`dummyindex/context/build/reconcile.py:251-320`) produces both content oracles drift reads.
- **Downstream — imports, not just hooks:**
  - `build/runner.py:258-260` → `ensure_memory_store` on every build.
  - `cli/gc.py:211` → `resolve_session_id`.
  - `dummyindex/cli/reconcile_gate.py:13`, `cli/guard_doc_write.py:17` →
    `read_hook_stdin` / `resolve_transcript` (`cli/memory.py:20-50`). That makes
    `cli/memory.py` the repo's shared hook-stdin adapter, via sibling-CLI
    imports `.context/conventions/folder-organization.md:77-83` already flags against its §2.
  - `domains/evidence.py:20`, `dummyindex/context/domains/evolve.py:480` →
    `miner/scope.project_dir_name`.
  - `domains/debt/harvest.py:13` → **private** `drift._rel_or_none`.
  - `cli/drift_ack.py:87` → `compute_drift`.
  - **Coupled without an import:** `evolve._harvest_memory`
    (`dummyindex/context/domains/evolve.py:300-364`) re-splits `now.md`/`recent.md` on `## ` with its own
    loop and hardcoded filenames, not `parse.split_sections`/`MemoryTier`; a
    tier-format change breaks it silently.
  - `atomic_io` is a shared kernel hosted here (`atomic_io.py:1-5`): 34 modules
    outside this feature import it; `build/upgrade.py:21` takes the private
    `_replace_bytes` plus `is_link`.
- **Fan-in:** `read_session_signal` ← `nudge.py:124`, `breadcrumb.py:104`,
  `reconcile_gate.py:352`. Exactly three.
- **Deliberate non-edge:** `transcript.py:4-6` refuses `usage`, preserving
  `cli → context → analysis → pipeline`.
- **Cycles: none.** Nothing `reconcile_gate` imports imports it back;
  `reconcile_scope` reaches only `build.reconcile` and `drift`
  (`reconcile_scope.py:9-10`); `drift_acks` only `atomic_io`; no
  `memory/*.py` imports `miner` except the `__init__` re-export.

## Architecture in three sentences

Four hook-driven mechanisms (tier store, drift report, reconcile gate,
skill-feedback miner) sit behind thin `cli/` wrappers that parse args, call one
domain decision, print its fixed payload, and return 0, and the generated shell
command (`|| true` then `exit 0`) guards that a second time
(`cli/memory.py:81-149`, `dummyindex/context/hooks.py:77-198`). Drift and gate are two policies
over one read model: `compute_drift` feeds an advisory `render_drift_summary`
at SessionStart and an authoritative `_gate_relevant` → ownership partition →
`decide_block` at Stop (`drift.py:115-258`, `reconcile_gate.py:289-388`).
Live-session decisions all come from the stdlib-only `read_session_signal`
(`transcript.py:123-161`); the miner re-reads historical JSONL to answer a
different question (`miner/scan.py:97-121`).

## Data model

No relational store. Two persistence classes with different rules; the split
is the design.

**Committed markdown, user-owned.** `.context/session-memory/`, one H1 plus
`## …` sections per file (`parse.py:24-49`):

| File | Written by | Rolled |
|---|---|---|
| `now.md` | agent handoffs + `(auto-breadcrumb)` entries (`breadcrumb.py:43-54`) | dated < today → `recent.md` |
| `recent.md` | roll only | dated < today−7 → `archive.md` |
| `archive.md` | roll only | terminal |
| `core-memories.md` | agent | never; emitted whole (`emit.py:42,51-52`) |
| `failure-patterns.md` | `miner/render.write_report` (`:68-72`), full overwrite | never; **nothing reads it** |

`failure-patterns.md` is deliberately not a `MemoryTier`: membership would make
`ensure_memory_store`, the enum's only iterator (`store.py:25`), stub it and
imply a lifecycle it lacks (`miner/render.py:3-5`). `roll_tiers` and
`render_session_start` name their members explicitly (`roll.py:60-62`,
`emit.py:40-42`).

**Gitignored per-machine caches** (`.context/cache/`, `.gitignore:19`):

| File | Shape / bound | Writer → reader |
|---|---|---|
| `skill-feedback.json` | schema 1, exact keys, ≤64 entries / 32 KiB, sorted `(-corrections, skill)` (`feedback.py:14-23`) | `mine` → `prompt-context` |
| `nudge-state.json` | `{sid: {nudged_at}}`, pruned to 100 (`nudge.py:56-67`) | nudge memo |
| `reconcile-gate-state.json` | `{sid: {blocked_at}}`, pruned to 100 (`reconcile_gate.py:230-244`) | gate memo |
| `freshness-badge` | labeled text, `[ctx: 2 edited · 1 anchored]` (`drift.py:86-112`) | `plan-update` → statusline |
| `doc-basis.json` | `{basis_version, features{fid: {rel: blob_sha}}}` (`dummyindex/context/build/reconcile.py:323-361`) | stamp only → `_read_doc_basis` |
| `drift-acks.json` | append-only dismissals (`drift_acks.py:93-95`) | `drift-ack` → `_drop_acked_rows` |
| `manifest.json` | per-file sha256 | `build_all` (`runner.py:283-292`) + stamp → `_content_unchanged` |

**Read-only external input.** The host transcript store, with two readers on
purpose: `transcript.py` for the live session (coarse counts, main-thread
edited paths, a subagent edit *count*) and `miner/scan.py` for history.

**Write discipline.** Tmp-file + `replace` everywhere via
`atomic_io._replace_bytes` (`atomic_io.py:37-67`): a unique `NamedTemporaryFile`
name, because two Claude profiles' hooks can hit one cache concurrently
(`:40-41`), and up to 6 `replace` retries on a Windows `PermissionError`
(`:55-64`). Write-elision keeps no-op runs byte-free (`feedback.py:126-129`,
`roll.py:81-82`). ⚠ `.context/conventions/data-access.md:7,9` cites pre-`is_link` ranges
(`atomic_io.py:11-33`, `:14-19`, `:27-46`), as does `.context/conventions/coding-practices.md:75`
(`:11-24`). The live ranges are `write_text_atomic` `:70-79` and
`normalize_eof_newline` `:82-98`; the code wins.

## Key decisions

1. **Markdown-first, mechanics-only** (the boundary decision). Decided the CLI
   relocates, prepends, and emits fixed strings and never summarizes, because
   prose is the agent's job (`dummyindex/context/domains/memory/__init__.py:1-5`, `roll.py:5-6`). Cost:
   the store cannot compress itself, so tiers grow until an agent rewrites them.
2. **The miner is nested, not a peer domain.** Decided because it feeds the same
   store (`dummyindex/context/domains/memory/miner/__init__.py:1-2`) from the same transcript substrate. The two
   outward edges, one of them unwired, keep the choice cheap to reverse. Cost:
   `memory/` holds two contexts under one name, and `scope.project_dir_name` has
   become a cross-domain port (evidence, evolve).
3. **Two stdlib-only transcript readers, not one.** `transcript.py:4-6` refuses
   `usage` for layering and skips cross-transcript dedup ("a per-file sum is
   sufficient"); the miner wants filtered rows across many files. Cost: the
   `CLAUDE_CONFIG_DIR` resolution exists twice (`transcript.py:48-51`,
   `resolve.py:18-24`, acknowledged at `resolve.py:5-7` (citation unverifiable)), and the project-slug
   encoding exists three times (see Open questions).
4. **Privacy is structural, not a filter.** `SkillDirectiveEvent` keeps only a
   sha256 `event_key` (`corrections.py:191-209`). `ToolCallRecord` keeps
   `output_bytes`, not an excerpt; an earlier cut rendered a 200-char sample
   into a git-tracked file (`dummyindex/context/domains/memory/miner/models.py:11-24` (citation unverifiable)). The failure renderer
   relativizes in-repo paths and redacts the rest lexically, without resolving
   them on this host (`scope.py:43-73`). Both guards exist because an audit
   caught the first cut violating them (`scope.py:3-7` (citation unverifiable)).
5. **One repo per scan by default.** `project_dir_name` matches exactly, not by
   prefix, because `-a-b-mono` ≠ `-a-b-mono-backend` (`scope.py:28-40`). A
   per-row `cwd` check (`scan.py:175-188,258`) closes residual name collisions.
   Pooling must be named (`all_projects=True`, `pipeline.py:75-97`).
6. **Grammar over classification.** Five high-precision patterns
   (`corrections.py:35-101`). Quoted and fenced text is stripped first
   (`:126-129`), the latest directive per skill wins within a prompt
   (`:181-188`), and a revocation resets the skill's count (`:269-281`).
   Rejected: LLM classification; `headroom/learn/analyzer.py` was skipped for
   exactly that reason (`dummyindex/context/domains/memory/miner/__init__.py:15` (citation unverifiable)). Cost: recall is whatever
   those five patterns cover.
7. **Two events, not one.** `DEFAULT_MIN_SKILL_CORRECTIONS = 2`, because one
   request is ordinary task input and two distinct events are a compliance
   signal (`dummyindex/context/domains/memory/miner/enums.py:31-33`). The current turn's directive is exempt from
   the threshold and outranks all history (`feedback.py:226-236`).
8. **Fail-closed read, bounded twice.** `read_skill_feedback` rejects the whole
   file on any anomaly: schema, symlink, non-regular file, size, duplicate
   slug, `sessions > corrections`, sort order (`feedback.py:136-200`). Prompt
   cost is capped at the cache (64 / 32 KiB) and again at projection (8 skills
   / 1600 chars, checked per line at `feedback.py:243-245`). Scan cost is
   capped once: substring rejection before `json.loads` (`scan.py:97-121`),
   and no `resolve()` for the already-absolute `cwd` (`scan.py:180-185`).
9. **Structured field-dropping, not string regex.** Structured inputs drop only
   `offset`/`limit`/`head_limit` and keep every other field byte-for-byte; `n`
   and `count` were removed after an audit found them merging unrelated MCP
   calls (`signatures.py:25-29,47-70`). Bash keeps the lossy treatment because
   a shell command really is opaque text.
10. **Hooks never fail; side effects fire once.** There are two layers: every
    generated command ends `|| true` then `exit 0` (`dummyindex/context/hooks.py:77-198`), and
    every verb returns 0 (`cli/memory.py:88,122,136,143,149`). Only `mine` and
    `prompt-context` also catch in-process (`cli/memory.py:81-122`), as does the
    badge write (`plan_update.py:62-65`); `nudge`, `breadcrumb`, and
    `session-start` let a domain exception reach the shell guard, with stderr
    muted. Nudge and gate key a `session_id` memo, LRU-pruned to 100, so a
    re-entrant Stop never double-fires.
11. **Staleness is a fallback chain, classified rather than boolean**
    (`drift.py:150-210`). (1) A doc-basis entry, the stamp's "docs describe
    these bytes" record, decides its (feature, file) pair: equal suppresses,
    unequal reports **regardless of doc mtime** (`drift.py:172-187`). Editing
    `plan.md` therefore does not clear a basis-covered row, contrary to the
    decay claim in `drift.py:3-4`; only a stamp or an ack does. (2) Without
    basis, a matching manifest sha256 kills git-op noise. (3) Otherwise legacy
    mtime decides. (4) Still-valid acks drop rows last. Every oracle reader
    degrades to empty/`False` on doubt (`_read_doc_basis`, `_content_unchanged`,
    `read_acks`). Decided the manifest advances only with the anchor, never on
    refresh, because refreshing it "would erase the very edit that triggered
    the rebuild" (`dummyindex/context/build/reconcile.py:296-298`). A live `meta.indexed_commit`
    stays authoritative for the gate: with an anchor, mtime-only drift is left
    to SessionStart (`reconcile_gate.py:247-254,289-304`).
12. **Stand down for `remember`.** `<root>/.remember/` short-circuits emit,
    nudge, and breadcrumb (`detect.py:8-15`; gated at `emit.py:34`,
    `nudge.py:115`, `breadcrumb.py:121`). Decided the miner verbs skip the
    check, because skill feedback does not compete with handoff injection.
13. **A session owns its edits, not inherited drift.** The gate blocks only on
    drift attributable to main-thread edited paths. The deepest context root
    wins, and a feature-level signal needs an edited path in that feature's
    `files` (`reconcile_scope.py:20-45`). The rest becomes a `systemMessage` or
    an appendix to the block reason (`reconcile_gate.py:359-388`). Subagent
    edits prove that source was touched but carry no paths, so they cannot
    claim a root (`tests/context/test_reconcile_scope.py:71-83`). Cost: a
    `/dummyindex-build` run that edits only through subagents never blocks. An
    unreadable transcript yields a memo-marked advisory
    (`reconcile_gate.py:339-351`).

## Open questions

- **The failure-pattern half has no caller.** `mine_and_feed`,
  `scan_transcript_store`, and `write_report` are reached only from
  `tests/context/domains/memory/miner/`; `memory mine` calls
  `refresh_skill_feedback` (`cli/memory.py:83-85`). Wiring it, giving
  `failure-patterns.md` a reader, or deleting it is undecided (see decision 2).
- **Project-slug encoding diverges.** `project_dir_name` replaces only path
  separators and the drive colon (`scope.py:36-40`). `transcript._encode_slug`
  (`transcript.py:54-55`) and `usage.transcripts.encode_project_slug`
  (`usage/transcripts.py:40-42`, documented as "every non-alphanumeric → '-'")
  replace every non-alphanumeric. `evidence.py:242` and `dummyindex/context/domains/evolve.py:486-487`
  hedge by trying both; `scan_skill_feedback` uses only `project_dir_name`
  (`pipeline.py:110-114`). So a repo whose path contains `_`, `.`, or a space
  probably gets no skill feedback. Unconfirmed against a real store.
- **`render_advisory_block` is dead** (`reconcile_gate.py:181-201`). It still
  emits `decision: block`, while the path it served now returns a
  `systemMessage` (`:343-350`). Is it kept for reuse or awaiting GC?
- **Should subagent edits carry paths?** `_subagent_edit_count`
  (`transcript.py:88-120`) parses the same `tool_use` blocks as
  `_edited_paths_in` but keeps only a count. Paths would let build-style runs
  own their drift; the current test pins the opposite.
- **The nothing-owned advisory is not memoized** (`reconcile_gate.py:372-377`
  skips `mark_blocked`), so it re-emits on every qualifying Stop. Intended?
- **Should the shared hook-stdin adapter move?** `read_hook_stdin` and
  `resolve_transcript` serve three CLIs from `cli/memory.py`; `cli/common.py`
  would satisfy folder-organization §2. Not decided in code.
- **Tuning constants are hardcoded:** `LONG_OUTPUT_TOKENS` (`nudge.py:23`),
  `recent_keep_days` (`roll.py:48`), `DEFAULT_MIN_SKILL_CORRECTIONS`
  (`dummyindex/context/domains/memory/miner/enums.py:33`), `MAX_PROMPT_SKILLS`/`MAX_PROMPT_CHARS`
  (`feedback.py:18-19`). `.context/config.json` is already read for
  `auto_council` (`reconcile_gate.py:32-45`); nothing here uses it.
- **Nothing ages skill feedback out.** Every post-revocation event in every
  retained transcript counts, with no time window (`corrections.py:269-281`).
- **The multi-profile union is broad.** `resolve_claude_config_dirs` globs every
  `~/.claude-*` (`resolve.py:40-49`), so an abandoned profile still
  contributes. Dedup by `event_key` misses a prompt copied across profiles
  under different `uuid`s (`corrections.py:198-209`).
- **`_ERROR_MARKERS` is an unmeasured substring list** (`miner/scan.py:23-35`).
  It is harmless only while nothing consumes failure-pattern output.
- **Placement noise.** `feature.json` lists `dummyindex/pipeline/enums.py`
  (only `ConfidenceLevel`, imported by nothing here), so its edits read as
  session-memory drift. `drift_acks.py`, `cli/drift_ack.py`, and
  `reconcile_scope.py` live under `maintenance`, and `cli/reconcile_gate.py`
  under `cli-dispatch`. A human placement pass should decide whether the drift
  engine's satellites move here.
- **Stale docs (code wins).** Three `DocConfidence.MEDIUM` plans
  (`docs/internal/plans/01-session-memory.md`,
  `docs/plans/2026-06-08-auto-handoff-nudge.md`,
  `docs/plans/2026-06-11-auto-council-drift-hook.md`) reference a
  `SessionMemoryError` that does not exist. Error handling here is plain
  returns, `()` sentinels, and 0-exits.
