# Session memory & drift signal — plan

`confidence: INFERRED`

## Where it lives

**Domain — the handoff store.** `dummyindex/context/domains/memory/`, split
canonical-trio-then-by-concern: `enums.py` (`MemoryTier`, `MemoryVerb`,
`AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`), `models.py` (frozen `Section` /
`RollReport` / `BreadcrumbFacts`), `store.py` (create + locate), `parse.py`
(section split/join + date extraction), `roll.py` (tier cascade), `emit.py`
(SessionStart render), `breadcrumb.py` (PreCompact entry), `nudge.py` (Stop CTA),
`transcript.py` (stdlib session-signal reader), `detect.py` (remember-plugin
stand-down), `__init__.py` (re-export surface, `memory/__init__.py:9-63`).

**Domain — the miner subpackage.** `dummyindex/context/domains/memory/miner/`,
added by the repo-adoptions pilot and extended into a wired capability at
ef038c0. Two independent pipelines share the same scanning primitives:

- *Skill-compliance feedback* (wired): `corrections.py` (the directive grammar,
  293 lines — the largest module in the feature), `feedback.py` (cache write/read
  + bounded prompt projection), `enums.py` (`SkillDirectiveKind`, thresholds),
  `models.py` (`SkillDirective`, `SkillDirectiveEvent`,
  `RecurringSkillCorrection`), plus `scan.parse_skill_directive_events`
  (`miner/scan.py:262-297`) and `pipeline.scan_skill_feedback` /
  `refresh_skill_feedback` (`miner/pipeline.py:112-152`).
- *Failure/loop patterns* (present, no non-test caller): `signatures.py`
  (canonicalize + group), `render.py` (markdown for
  `.context/session-memory/failure-patterns.md`), `scope.py` (project scoping +
  path redaction), `scan.parse_transcript` (`miner/scan.py:140-190`), and
  `pipeline.scan_transcript_store` / `mine_and_feed` (`miner/pipeline.py:40-109`).
- Shared by both: `resolve.py` (config-dir / store resolution honoring
  `CLAUDE_CONFIG_DIR`), `scan.discover_project_dirs`, `scope.project_dir_name`.
- `miner/__init__.py:1-33` carries the Apache-2.0 attribution for
  `headroomlabs-ai/headroom`, including the correction of an earlier docstring
  that overclaimed independence. The repo-root `NOTICE` is the license artifact.

**Consumers of the same staleness model.** `dummyindex/context/drift.py`
(SessionStart report engine, `compute_drift` at `drift.py:126-191`) and
`dummyindex/context/reconcile_gate.py` (Stop gate, `decide_block` at
`reconcile_gate.py:342-399`).

**Boundary.** `dummyindex/cli/memory.py` (wire-only, 180 lines) and
`dummyindex/cli/plan_update.py` (80 lines). Hook wiring lives in
`dummyindex/context/hooks.py` — UserPromptSubmit at `hooks.py:120-145`,
SessionStart at `hooks.py:147-198`.

**Shared I/O.** `dummyindex/context/domains/atomic_io.py` — every tier and cache
write goes through `write_text_atomic` (`atomic_io.py:37-47`).

**Map noise.** `dummyindex/pipeline/enums.py` is an unrelated member the feature
map sweeps in; the live `MemoryVerb` is `memory/enums.py:17-26`.

## Architecture in three sentences

Four hook-driven mechanisms — tier store, drift report, reconcile gate, and
skill-feedback miner — sit behind two wire-only CLI dispatchers that parse args,
call one domain function, print a fixed payload, and return 0 unconditionally.
The tier store and the miner are both "decide, then render a fixed string": the
store's mechanics (`roll_tiers`, `run_breadcrumb`, `render_session_start`) never
author prose, and the miner never renders quoted transcript text — it renders
policy lines keyed by a validated slug (`miner/feedback.py:25-37,203-247`) —
so the deterministic layer stays auditable and the prose stays the agent's job.
Drift and gate are two readers of one staleness model (`compute_drift` →
`render_drift_summary` advisory at SessionStart, `compute_drift` → `_gate_relevant`
→ `decide_block` authoritative at Stop), and all four mechanisms read the live
session through the single stdlib-only `read_session_signal`
(`memory/transcript.py:137-175`) or, in the miner's case, through its own
independent read-only pass over on-disk JSONL.

## Data model

No relational store. Persistence splits cleanly into two classes with different
rules, and the split is the design:

**Committed markdown, user-owned** — `.context/session-memory/`, one H1 plus
zero-or-more `## …` sections per file (`memory/parse.py:24-49`):

| File | Written by | Rolled by |
|---|---|---|
| `now.md` | agent handoffs + `(auto-breadcrumb)` entries (`breadcrumb.py:43-54`) | dated < today → `recent.md` |
| `recent.md` | roll only | dated < today−7 → `archive.md` |
| `archive.md` | roll only | terminal |
| `core-memories.md` | agent (promoted durable facts) | never rolled; emitted whole (`emit.py:42,51-52`) |
| `failure-patterns.md` | `miner/render.write_report` — full overwrite, generated marker on line 1 | never rolled; nothing reads it |

`failure-patterns.md` is deliberately *not* a `MemoryTier` member: adding it
would make `ensure_memory_store` stub it and imply a lifecycle it does not have
(`miner/render.py:11-19`). That is why `roll_tiers` and `render_session_start`
can iterate the enum and stay correct.

**Gitignored per-machine caches** — `.context/cache/` (`.gitignore:19`):
`skill-feedback.json` (schema 1, `{"schema_version", "skills"}` exactly, entries
`{"skill", "corrections", "sessions"}`, ≤64 entries, ≤32 KiB, sorted by
`(-corrections, skill)`; `miner/feedback.py:14-19,83-98`), `nudge-state.json`
(pruned to 100 sessions, `nudge.py:56-67`), `reconcile-gate-state.json`
(`reconcile_gate.py:250-264`), `freshness-badge` (`plan_update.py:35-51`), and
`manifest.json` — the sha256 source drift cross-filters against
(`drift.py:383-414`).

**Read-only external input** — the host transcript store under
`$CLAUDE_CONFIG_DIR`/`~/.claude` `projects/`. The feature only ever reads it. Two
different readers exist on purpose: `memory/transcript.py` for the *live* session
(coarse counts, edited paths) and `miner/scan.py` for *historical* mining.

**Transactions** — none, in the DB sense. The equivalent discipline is
tmp-file + `replace` on every write. `atomic_io._replace_bytes`
(`atomic_io.py:13-34`) now names the temp file via `NamedTemporaryFile` with a
unique suffix, because hooks from two Claude profiles can update the same
repo-local cache concurrently (`atomic_io.py:15-18`) — the `.context/conventions/
data-access.md` line describing `write to path + ".tmp"` at `atomic_io.py:11-24`
is stale against this; **the code wins**. `write_skill_feedback` adds a
read-compare-then-write so an unchanged cache is not rewritten at all
(`feedback.py:126-133`), and `roll_tiers` returns before touching any file when
nothing moved (`roll.py:81-82`).

## Key decisions

1. **Markdown-first, mechanics-only.** The CLI relocates, prepends, and emits
   fixed strings; it never summarizes. `/dummyindex-remember` owns prose
   (`memory/__init__.py:1-5`). This is the boundary the whole feature is drawn
   around, and the miner honors it too — it emits policy prose it authored, never
   text it read.
2. **Stdlib-only transcript reader, twice, rather than a shared dependency.**
   `memory/transcript.py` refuses to import the `usage` domain to keep
   `cli → context → analysis → pipeline` acyclic, paying the price of no
   cross-transcript dedup (`transcript.py:5-8`). The miner's `scan.py` then
   re-reads JSONL a third time for a different question. Rejected: one unified
   reader — the live-signal reader wants coarse aggregates over one file, the
   miner wants filtered rows across many, and the layering forbids reaching into
   `usage`.
3. **Privacy is structural, not a filter.** No raw prompt text survives parsing:
   `SkillDirectiveEvent` carries a sha256 `event_key` (`corrections.py:191-209`)
   and `ToolCallRecord` carries `output_bytes`, not an output excerpt — an
   earlier cut kept a 200-char sample and rendered it into a git-tracked file
   (`miner/models.py:11-27`). The failure-pattern renderer additionally makes
   in-repo paths relative and *redacts* everything else rather than passing it
   through (`miner/scope.py:52-71`). Both guards exist because an audit found the
   first cut violating them.
4. **Scope every scan to one repo by default.** A transcript store spans every
   project the host has opened; `project_dir_name` matches the store directory
   **exactly**, not by prefix, because `-a-b-mono` and `-a-b-mono-backend` are
   different projects (`miner/scope.py:41-49`). Cross-project pooling exists but
   must be asked for by name (`all_projects=True`, `pipeline.py:83-109`).
5. **Grammar over classification for corrections.** High-precision regexes on a
   small closed set of phrasings (`corrections.py:35-101`), quoted/fenced text
   stripped first, latest-directive-per-skill wins within one prompt
   (`corrections.py:181-188`), and a revocation resets the counter for everything
   before it (`corrections.py:269-281`). Rejected: any semantic/LLM
   classification — `headroom/learn/analyzer.py` was explicitly skipped for
   exactly this reason (`miner/__init__.py:29-32`).
6. **Two events, not one.** `DEFAULT_MIN_SKILL_CORRECTIONS = 2` — a single
   request is ordinary task input, two distinct human events are a compliance
   signal worth persisting (`miner/enums.py:39-40`). The current turn's directive
   is exempt: it ranks above all history so same-turn feedback applies
   immediately (`feedback.py:227-236`).
7. **Fail-closed read, fail-open run.** `read_skill_feedback` rejects the whole
   file on any anomaly — wrong schema, symlink, non-regular file, oversize,
   duplicate slug, wrong sort order (`feedback.py:136-200`) — while both new CLI
   verbs swallow every exception and exit 0 (`cli/memory.py:87-128`). Generated
   feedback must never block a session; malformed generated feedback must never
   reach a prompt.
8. **Prompt cost is bounded twice.** At the cache (64 entries / 32 KiB) and again
   at the projection (8 skills / 1600 chars, with the line-by-line length check
   at `feedback.py:243-246`). Scan cost is bounded too: `_iter_skill_json_lines`
   substring-rejects non-candidate rows before `json.loads`
   (`miner/scan.py:109-137`) and `_resolved_cwd_matches` skips a filesystem
   `resolve()` for the common already-absolute case (`scan.py:193-206`) — that
   one matters on the mounted Windows filesystem this repo lives on.
9. **Structured field-dropping instead of string regex.** headroom's pagination
   normalization is bash-only because it is regex surgery on opaque text; because
   dummyindex tools pass structured JSON, the signature drops the three
   unambiguous pagination fields (`offset`, `limit`, `head_limit`) and keeps
   every other field byte-for-byte. `n` and `count` were deliberately removed
   after an audit found them merging unrelated MCP calls
   (`miner/signatures.py:43-50,68-99`). Bash keeps the lossy treatment.
10. **Hooks never fail; the gate blocks once.** Every hook verb returns 0
    (`cli/memory.py:94,128,142,149,155`); the nudge and the gate each key on
    `session_id` plus a pruned JSON memo so a re-entrant Stop never double-fires
    (`nudge.py:38-67`, `reconcile_gate.py:223-264`).
11. **Three-oracle staleness.** mtime is a decaying advisory, the manifest sha
    kills git-op false positives (`drift.py:400-414`), and a live
    `meta.indexed_commit` anchor is authoritative — with an anchor the gate
    ignores mtime-only drift and lets SessionStart surface it
    (`reconcile_gate.py:267-276,321-339`).
12. **Stand down for `remember`.** Presence of `<root>/.remember/` short-circuits
    emit, nudge, and breadcrumb before any work (`memory/detect.py:8-15`, gated
    at `emit.py:34`, `nudge.py:115`, `breadcrumb.py:122`). Note the asymmetry:
    the two miner verbs do **not** check it — skill-compliance feedback is
    orthogonal to handoff injection, so there is no competing-block problem.

## Open questions

- **The failure-pattern half of the miner has no caller.** `mine_and_feed`,
  `scan_transcript_store`, and `miner/render.write_report` are reachable only
  from tests; `memory mine` calls `refresh_skill_feedback` instead
  (`cli/memory.py:89-91`), and `memory/__init__.py:18-23` re-exports only the four
  skill-feedback symbols. Whether it gets a verb, gets a consumer for
  `failure-patterns.md`, or gets deleted is undecided from the code alone.
- **Tuning constants stay hardcoded.** `LONG_OUTPUT_TOKENS = 40_000`
  (`nudge.py:23`), `recent_keep_days = 7` (`roll.py:48`),
  `DEFAULT_MIN_SKILL_CORRECTIONS = 2`, `MAX_PROMPT_SKILLS = 8`,
  `MAX_PROMPT_CHARS = 1600` (`miner/enums.py:40`, `miner/feedback.py:18-19`).
  `.context/config.json` already carries `auto_council`, so a surfacing path
  exists; nothing uses it for these.
- **Nothing ages skill feedback out.** `aggregate_skill_corrections` counts every
  post-revocation event in every retained transcript with no time window
  (`corrections.py:269-281`), so a correction from a year ago still promotes a
  skill until the user explicitly revokes it or the transcripts are deleted.
  Whether that is intended durability or a missing decay is not answerable from
  the code.
- **Multi-profile union is broad.** `resolve_claude_config_dirs` globs every
  `~/.claude-*` directory (`miner/resolve.py:47-56`), so an unrelated or
  abandoned profile contributes events for this repo. Deduplication is by
  `event_key`, which will not collapse the same prompt copied across profiles
  with different `uuid`s.
- **`_ERROR_MARKERS` is a hand-picked substring list** (`miner/scan.py:29-40`)
  applied to the first 1000 chars of a tool result. Its false-positive rate on
  legitimate output that merely mentions "error:" is unmeasured — currently
  harmless because nothing consumes the failure-pattern output.
- **Stale-doc flag (code wins).** Catalogued plans
  (`docs/internal/plans/01-session-memory.md`,
  `docs/plans/2026-06-08-auto-handoff-nudge.md`,
  `docs/plans/2026-06-11-auto-council-drift-hook.md`, all DocConfidence.MEDIUM
  with broken refs) reference a `SessionMemoryError` typed exception that does
  not exist. Error handling here is plain returns, `()` sentinels, and 0-exits —
  no domain exception hierarchy. Treat the doc claim as stale.
