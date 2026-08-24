# Session memory & drift signal — plan

`confidence: INFERRED`

## Where it lives

**The invariant the boundary is drawn around.** Every module here *decides* and
then *renders a fixed string*; none of them author prose. The store relocates
sections it never reads the meaning of; the miner emits policy lines it wrote
itself, keyed by a validated slug, never transcript text it read
(`miner/feedback.py:25-37,238-247`). Prose is out of the boundary by design —
it belongs to the `/dummyindex-remember` skill (`memory/__init__.py:1-5`).

Three nested contexts share the folder. They are separable, and the separation
is load-bearing.

**A — the tier store** (`dummyindex/context/domains/memory/`). Repository over
a closed set of markdown files: `store.py:11-31` locates and non-destructively
creates, `parse.py:24-49` splits/joins on `## ` headings, `roll.py:44-108`
cascades by date, `emit.py:33-61` renders the SessionStart block,
`breadcrumb.py:118-127` writes the PreCompact entry, `nudge.py:103-131` decides
the Stop CTA, `detect.py:8-15` stands the whole thing down. `enums.py:8-38`
is the closed alphabet (`MemoryTier`, `MemoryVerb`, `AUTO_BREADCRUMB_TAG`,
`TIER_HEADINGS`, `enums.py:8-39`); `models.py` the frozen carriers. `transcript.py:137-175` is
the live-session adapter.

**B — the miner subpackage** (`memory/miner/`). A second bounded context nested
in A's folder, with its own `enums.py`, `models.py`, and its own resolution port
(`resolve.py:44-67`). Its coupling to A is one import in each direction and no
more: A re-exports four miner symbols (`memory/__init__.py:18-23`); the miner
reaches back exactly twice — `atomic_io` (`feedback.py:10`, `render.py:29`) and
`store.memory_dir` (`render.py:30`). Two pipelines of the same shape
(resolve → scan → group → write) live side by side:

| Pipeline | Entry | Wired? | Modules |
|---|---|---|---|
| Skill-compliance feedback | `pipeline.scan_skill_feedback` / `refresh_skill_feedback` (`miner/pipeline.py:112-152`) | **yes** — SessionStart + UserPromptSubmit | `corrections.py` (grammar, 293 lines, largest in the feature), `feedback.py` (cache + projection), `scan.parse_skill_directive_events` (`miner/scan.py:262-297`) |
| Failure / loop patterns | `pipeline.scan_transcript_store` / `mine_and_feed` (`miner/pipeline.py:40-109`) | **no** — tests only | `signatures.py` (canonicalize + group), `render.py` (writes `failure-patterns.md`), `scan.parse_transcript` (`miner/scan.py:140-190`) |

Shared by both: `resolve.py` (config-dir/store resolution honoring
`CLAUDE_CONFIG_DIR`), `scan.discover_project_dirs`, `scope.py` (scoping +
redaction). Note the asymmetry the table encodes: the **wired** half touches
nothing in A except `atomic_io`; the single `..store` edge (`render.py:30`)
belongs entirely to the **unwired** half. Cutting the failure-pattern pipeline
would leave the miner fully decoupled from the tier store.

`miner/__init__.py:1-33` carries the Apache-2.0 attribution for
`headroomlabs-ai/headroom` and the correction of an earlier docstring that
overclaimed independence; the repo-root `NOTICE` is the license artifact.

**C — the staleness readers.** `context/drift.py` (`compute_drift` at
`drift.py:152-265`) and `context/reconcile_gate.py` (`decide_block` at
`reconcile_gate.py:342-399`). Two policies over one read model, not two models.
Since the 2026-08 train `compute_drift` classifies each row through a
**basis → manifest → mtime fallback chain**: a `cache/doc-basis.json` entry
(stamp-time blob sha, read via `_read_doc_basis` `:489-521`) decides its
(feature, file) pair — equal suppresses the row as history-moved noise, unequal
is real drift; pairs without basis fall back to the manifest sha256
(`_content_unchanged`), then legacy mtime-only; still-valid `drift-ack`
dismissals drop their rows last (`_drop_acked_rows`, `drift.py:524-555`).

**Boundary layer.** `cli/memory.py` (7-verb dispatcher over `MemoryVerb`,
`cli/memory.py:59-180`), `cli/plan_update.py:68-100`, and
`cli/drift_ack.py:42-170`. Hook wiring is generated in `context/hooks.py`; the
event→verb map *is* the downstream contract:

| Hook event | Command | `hooks.py` |
|---|---|---|
| SessionStart | `plan-update`, `memory session-start`, `gc signal`, `memory mine` | `147-198` |
| UserPromptSubmit | turn reminder, `memory prompt-context` | `120-145` |
| Stop | `memory nudge`, `reconcile-gate` | `200-227` |
| PreCompact | `memory breadcrumb` | `229-243` |
| PreToolUse (`Write`) | `guard-doc-write` (shared hook-stdin adapter consumer) | `245-267` |

`plan-update` additionally serves two non-hook surfaces: the statusline badge
cache it writes is echoed verbatim by `dummyindex context statusline`
(`cli/statusline.py:37-66`) and by the shipped `statusline.sh`/`statusline.ps1`
wrappers, and its new `--json` envelope (`plan_update.py:70-71,103-114`) is for
scripts that must act per-row instead of prose. `drift-ack` has no hook — it is
an operator verb.

### Dependency direction

- **Upstream (this feature imports):** `build/manifest.read_manifest`,
  `build/reconcile.compute_reconcile_report` + `DOC_BASIS_REL`/`DOC_BASIS_VERSION`/`blob_sha`,
  and `pipeline/io/detect.detect` (`drift.py:35-43`);
  `domains/drift_acks.read_acks` (`drift.py:42`);
  `pipeline/io.submodule_paths` (`reconcile_gate.py:36`);
  `domains/atomic_io.write_text_atomic` (every writer, incl. `drift_acks._write`
  at `drift_acks.py:107-109`). External, read-only: the host transcript store
  under `$CLAUDE_CONFIG_DIR`/`~/.claude`, and `git` via subprocess
  (`breadcrumb.py:57-95`). The doc-basis snapshot this chain reads is written by
  `rebuild`'s `stamp_reconciled` (`build/reconcile.py:318-351`) — the stamp is
  the producer; drift only consumes.
- **Downstream — the CLI is not the only consumer.** Five in-tree modules import
  this feature directly: `context/build/runner.py` calls
  `ensure_memory_store` on **every rebuild** (so the store is seeded by build,
  not only by `memory init`); `cli/gc.py` reuses `resolve_session_id`;
  `cli/guard_doc_write.py` and `cli/reconcile_gate.py` import
  `read_hook_stdin` / `resolve_transcript` from `cli/memory.py:26-56`. That last
  pair makes `cli/memory.py` the repo's shared hook-stdin adapter, not a
  private wire — changing those two signatures breaks three other CLIs. And the
  tier store now has a *reader outside the hooks*: the evolve domain's harvest
  parses correction sections out of `now.md`/`recent.md` into evidence items
  (`domains/evolve.py:_harvest_memory`, `:372-438`; `_MEMORY_TIERS` `:372`),
  so a reformat of tier headings feeds another feature's evidence pipeline.
- **Fan-in:** `read_session_signal` (`transcript.py:137-175`) has exactly three
  callers — `nudge.py:124`, `breadcrumb.py:97` (via `build_breadcrumb_facts`),
  `reconcile_gate.py:387`.
- **Deliberate non-edge:** `transcript.py:5-8` refuses to import the `usage`
  domain, preserving `cli → context → analysis → pipeline`.
- **Cycles: none.** `reconcile_gate.py:33-35` imports `memory.nudge`,
  `memory.transcript`, and `drift`; none of the three imports `reconcile_gate`.
  The miner imports the parent package only via `atomic_io` and `..store`; no
  module in `memory/*.py` imports `miner` except the `__init__` re-export.
- **Map caveat (code wins, 2026-08-23).** `.context/meta.json` is anchored at
  `f8a8a33` (= HEAD), but the deterministic backbone it stamps is **polluted**:
  `tree.json`'s root has the foreign `results/` tree as its sole top-level
  child, and `map/symbols.json` holds only ClickHouse/gtest symbols from
  `results/benchmarks/workspaces/` — zero first-party Python symbols. The
  practical consequences: `feature.json.members` still lists no miner or
  drift-engine symbols (the pre-rebuild staleness persists for a different
  reason — there is nothing to extract from), and every citation in this plan
  was checked against source at HEAD, not against the map. A scoped rebuild
  excluding `results/` closes this; see `concerns.md`.

## Architecture in three sentences

Four hook-driven mechanisms — tier store, drift report, reconcile gate, and
skill-feedback miner — sit behind two emit-only CLI dispatchers that parse args,
call one domain function, print a fixed payload, and return 0 unconditionally
(`cli/memory.py:87-155`). Drift and gate are two policies over one read model:
`compute_drift` feeds an advisory `render_drift_summary` at SessionStart and an
authoritative `_gate_relevant` → `decide_block` at Stop
(`drift.py:152-265`, `reconcile_gate.py:321-399`). All live-session decisions
come from the single stdlib-only `read_session_signal`
(`transcript.py:137-175`), while the miner runs an independent read-only pass
over historical on-disk JSONL (`miner/scan.py:109-137`) — a different question
over the same bytes.

## Data model

No relational store. Persistence splits into two classes with different rules,
and the split is the design.

**Committed markdown, user-owned** — `.context/session-memory/`, one H1 plus
zero-or-more `## …` sections per file (`parse.py:24-49`):

| File | Written by | Rolled by |
|---|---|---|
| `now.md` | agent handoffs + `(auto-breadcrumb)` entries (`breadcrumb.py:43-54`) | dated < today → `recent.md` |
| `recent.md` | roll only | dated < today−7 → `archive.md` |
| `archive.md` | roll only | terminal |
| `core-memories.md` | agent (promoted durable facts) | never rolled; emitted whole (`emit.py:42,51-52`) |
| `failure-patterns.md` | `miner/render.write_report:83` — full overwrite | never rolled; **nothing reads it** |

`failure-patterns.md` is deliberately *not* a `MemoryTier` member: adding it
would make `ensure_memory_store` stub it and imply a lifecycle it does not have
(`miner/render.py:11-17`). That exclusion is what lets `roll_tiers` and
`render_session_start` iterate the enum and stay correct.

**Gitignored per-machine caches** — `.context/cache/` (`.gitignore:19`):
`skill-feedback.json` (schema 1, keys `{schema_version, skills}` exactly,
entries `{skill, corrections, sessions}`, ≤64 entries, ≤32 KiB, sorted by
`(-corrections, skill)`; `feedback.py:14-23`), `nudge-state.json` (pruned to
100 sessions, `nudge.py:56-67`), `reconcile-gate-state.json` (same shape,
`reconcile_gate.py:250-264`), `freshness-badge` (labeled badge text, e.g.
`[ctx: 2 edited · 1 anchored]`, written by `plan_update.py:35-51`, echoed by
the statusline surfaces), `doc-basis.json` (`{basis_version, features{fid:
{rel_path: blob_sha}}}`, written only by `reconcile-stamp`,
`build/reconcile.py:361-399`; read corrupt-tolerantly by `drift._read_doc_basis`),
`drift-acks.json` (append-only dismissals, `domains/drift_acks.py`), and
`manifest.json` — the sha256 oracle of last fallback
(`drift.py:472-486,558-572`).

**Read-only external input** — the host transcript store. Two readers exist on
purpose: `transcript.py` for the *live* session (coarse counts, edited paths)
and `miner/scan.py` for *historical* mining.

**Transactions** — none in the DB sense; the equivalent discipline is tmp-file +
`replace` on every write. `atomic_io._replace_bytes:13-34` names the temp file
via `NamedTemporaryFile` with a unique suffix because hooks from two Claude
profiles can update the same repo-local cache concurrently
(`atomic_io.py:14-18`). ⚠ `.context/conventions/data-access.md:7` still
describes `write to path + ".tmp"` at `atomic_io.py:11-24` — stale on both the
mechanism and the range (`write_text_atomic` is now `atomic_io.py:37-47`); **the
code wins**. Two write-elision guards keep the no-op path byte-free:
`write_skill_feedback` compares before writing (`feedback.py:126-133`) and
`roll_tiers` returns before touching a file when nothing moved
(`roll.py:81-82`).

## Key decisions

1. **Markdown-first, mechanics-only** — the boundary decision. Decided the CLI
   relocates/prepends/emits fixed strings and never summarizes, because prose is
   the agent's job and a deterministic layer that authors text is unauditable
   (`memory/__init__.py:1-5`). Cost: the store cannot compress itself; tiers grow
   until an agent rewrites them.
2. **The miner is a nested subpackage, not a sibling domain.** Decided to give it
   its own `enums`/`models`/`resolve` inside `memory/` rather than a peer
   `domains/miner/`, because it feeds the same store and shares the same
   transcript substrate — but the near-zero import coupling (two edges, one of
   them only in the unwired half) means the decision is cheaply reversible.
   Cost: `memory/` is now two contexts under one folder name.
3. **Stdlib-only transcript reader, twice, rather than one shared reader.**
   `transcript.py:5-8` refuses `usage` to keep `cli → context → analysis →
   pipeline` acyclic; the miner then re-reads JSONL a third time for a different
   question. Rejected: a unified reader — the live reader wants coarse aggregates
   over one file, the miner wants filtered rows across many, and the layering
   forbids reaching into `usage`. Cost: no cross-transcript dedup.
4. **Privacy is structural, not a filter.** No raw prompt text survives parsing:
   `SkillDirectiveEvent` carries a sha256 `event_key` (`corrections.py:191-209`)
   and `ToolCallRecord` carries `output_bytes`, not an excerpt — an earlier cut
   kept a 200-char sample and rendered it into a git-tracked file
   (`miner/models.py:11-27`). The failure-pattern renderer makes in-repo paths
   relative and *redacts* everything else rather than passing it through
   (`scope.py:52-71`). Both guards exist because an audit found the first cut
   violating them.
5. **Scope every scan to one repo by default.** `project_dir_name` matches the
   store directory **exactly**, not by prefix, because `-a-b-mono` and
   `-a-b-mono-backend` are different projects (`scope.py:41-49`). Cross-project
   pooling exists but must be named (`all_projects=True`, `pipeline.py:83-109`).
6. **Grammar over classification.** High-precision regexes on a small closed set
   of phrasings (`corrections.py:35-101`), quoted/fenced text stripped first,
   latest-directive-per-skill wins within one prompt (`corrections.py:181-188`),
   a revocation resets the counter for everything before it
   (`corrections.py:269-281`). Rejected: semantic/LLM classification —
   `headroom/learn/analyzer.py` was skipped for exactly this reason
   (`miner/__init__.py:29-32`). Cost: recall is whatever the five patterns cover.
7. **Two events, not one.** `DEFAULT_MIN_SKILL_CORRECTIONS = 2`
   (`miner/enums.py:38-40`) — one request is ordinary task input, two distinct
   human events are a compliance signal worth persisting. The current turn's
   directive is exempt and ranks above all history, so same-turn feedback applies
   immediately (`feedback.py:226-236`).
8. **Fail-closed read, fail-open run.** `read_skill_feedback` rejects the whole
   file on any anomaly — wrong schema, symlink, non-regular file, oversize,
   duplicate slug, `sessions > corrections`, wrong sort order
   (`feedback.py:136-200`) — while both new CLI verbs swallow every exception and
   exit 0 (`cli/memory.py:87-128`). Generated feedback must never block a
   session; malformed generated feedback must never reach a prompt.
9. **Prompt cost bounded twice, scan cost bounded once.** At the cache (64
   entries / 32 KiB) and again at the projection (8 skills / 1600 chars, with a
   line-by-line length check at `feedback.py:243-246`).
   `_iter_skill_json_lines` substring-rejects non-candidate rows before
   `json.loads` (`miner/scan.py:109-137`) and `_resolved_cwd_matches` skips a
   filesystem `resolve()` for the already-absolute case (`scan.py:193-206`) —
   that one matters on the mounted Windows filesystem this repo lives on.
10. **Structured field-dropping instead of string regex.** Because dummyindex
    tools pass structured JSON, the signature drops three unambiguous pagination
    fields (`offset`, `limit`, `head_limit`) and keeps every other field
    byte-for-byte; `n` and `count` were removed after an audit found them merging
    unrelated MCP calls (`signatures.py:43-50,68-99`). Bash keeps headroom's
    lossy treatment, because a shell command genuinely is opaque text.
11. **Hooks never fail; side effects fire once.** Every hook verb returns 0
    (`cli/memory.py:94,128,142,149,155`); nudge and gate each key on `session_id`
    plus an LRU-pruned JSON memo so a re-entrant Stop never double-fires
    (`nudge.py:56-67`, `reconcile_gate.py:250-264`).
12. **Four-oracle staleness, classified not boolean.** mtime is a decaying
    advisory; the doc-basis snapshot written at the stamp boundary is the
    per-(feature, file) authority for "the docs describe these bytes" — a match
    *suppresses* an mtime row as history-moved noise rather than reporting it;
    the manifest sha kills git-op false positives for basis-less pairs
    (`drift.py:192-243`); and a live `meta.indexed_commit` anchor remains the
    authoritative reconcile boundary — with an anchor the gate ignores
    mtime-only drift and lets SessionStart surface it
    (`reconcile_gate.py:267-276,321-339`). A fifth, user-supplied overlay — the
    `drift-ack` store — dismisses known-good rows until their bytes change.
    Rationale for the conservative direction: every reader returns `False`/`{}`
    on any doubt (`_content_unchanged`, `_read_doc_basis`, `read_acks`), so a
    hashing failure reports rather than hides.
13. **Stand down for `remember`.** Presence of `<root>/.remember/`
    short-circuits emit, nudge, and breadcrumb before any work
    (`detect.py:8-15`, gated at `emit.py:34`, `nudge.py:115`,
    `breadcrumb.py:121`). Decided the two miner verbs do **not** check it,
    because skill-compliance feedback is orthogonal to handoff injection — there
    is no competing-block problem to solve.

## Placement (reconcile 2026-08-23)

- **Newly-owned-but-unplaced:** `dummyindex/context/domains/drift_acks.py` and
  `dummyindex/cli/drift_ack.py` — created by this train for this feature's drift
  engine (`context/drift.py` imports the domain; the CLI verb exists solely to
  serve it) but absent from `feature.json` `files`/`members`. They belong here in
  the next human-reviewed placement pass. `drift_acks._write` also reuses this
  feature's `atomic_io`, consistent with the A-boundary.
- **Foreign / unowned — do not claim:** `benchmarks/`, `tests/benchmarks/`, and
  `results/` are a separate benchmarking workstream. They sit only in raw
  `community-*` clusters; none of them may be absorbed into this feature even
  though the polluted backbone (see Map caveat) currently sweeps `results/`
  content into every deterministic artefact.
- **Adjacent but not ours:** `domains/evolve.py` consumes this feature's tier
  store as evidence (`_harvest_memory`) yet is placed under the `equip` feature —
  recorded as a downstream consumer above, not claimed as a member.

## Open questions

- **The failure-pattern half of the miner has no caller.** `mine_and_feed`,
  `scan_transcript_store`, and `render.write_report` are reachable only from
  `tests/context/domains/memory/miner/`; `memory mine` calls
  `refresh_skill_feedback` instead (`cli/memory.py:89-91`), and
  `memory/__init__.py:18-23` re-exports only the four skill-feedback symbols.
  Whether it gets a verb, gets a consumer for `failure-patterns.md`, or gets
  deleted is undecided from the code alone — see decision 2 for the cost of each.
- **Tuning constants stay hardcoded.** `LONG_OUTPUT_TOKENS = 40_000`
  (`nudge.py:23`), `recent_keep_days = 7` (`roll.py:48`),
  `DEFAULT_MIN_SKILL_CORRECTIONS = 2` (`miner/enums.py:40`),
  `MAX_PROMPT_SKILLS = 8` / `MAX_PROMPT_CHARS = 1600` (`feedback.py:18-19`).
  `.context/config.json` already carries `auto_council`
  (`reconcile_gate.py:39-45`), so a surfacing path exists; nothing uses it here.
- **Nothing ages skill feedback out.** `aggregate_skill_corrections` counts every
  post-revocation event in every retained transcript with no time window
  (`corrections.py:269-281`), so a year-old correction still promotes a skill
  until the user explicitly revokes it or the transcripts are deleted. Intended
  durability or missing decay is not answerable from the code.
- **Multi-profile union is broad.** `resolve_claude_config_dirs` globs every
  `~/.claude-*` directory (`resolve.py:47-56`), so an abandoned profile
  contributes events for this repo. Deduplication is by `event_key`, which will
  not collapse the same prompt copied across profiles with different `uuid`s
  (`corrections.py:198-209`).
- **`_ERROR_MARKERS` is a hand-picked substring list** (`miner/scan.py:29-41`)
  applied to the first 1000 chars of a tool result. Its false-positive rate on
  output that merely mentions "error:" is unmeasured — currently harmless only
  because nothing consumes the failure-pattern output.
- **Stale-doc flag (code wins).** Catalogued plans
  (`docs/internal/plans/01-session-memory.md`,
  `docs/plans/2026-06-08-auto-handoff-nudge.md`,
  `docs/plans/2026-06-11-auto-council-drift-hook.md`, all `DocConfidence.MEDIUM`
  with broken refs) reference a `SessionMemoryError` typed exception that does
  not exist. Error handling here is plain returns, `()` sentinels, and 0-exits —
  no domain exception hierarchy. Treat the doc claim as stale; see also the
  `data-access.md` conflict recorded under Data model.
