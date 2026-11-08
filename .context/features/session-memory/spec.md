# Session memory & drift signal — spec

`confidence: INFERRED`

## Intent

A fresh Claude Code session starts blind: it does not know what the last session
did, whether the repo's `.context/` index still describes the code, or which
instructions the user has had to repeat. This feature closes all three gaps with
deterministic, hook-driven machinery that never calls a model and never writes
prose. It maintains a four-tier markdown handoff store the agent authors and the
CLI only relocates; it computes which features' docs have fallen behind their
source, reports that at session start, and blocks session exit once when the
session itself caused the staleness — drift the session merely inherited stays a
non-blocking advisory; and it mines the host's own transcripts for recurring
human corrections about named skills, feeding a bounded policy line back into
every prompt so a correction the user has already given twice does not have to
be given a third time. Everything it persists is either editable markdown the
user owns or a gitignored per-machine cache, and every hook path exits 0 so a
broken install degrades to silence rather than a broken session.

## User-visible behavior

### CLI surface

`dummyindex context memory {session-start|roll|init|nudge|breadcrumb|mine|prompt-context}`
(`dummyindex/context/domains/memory/enums.py:17-26`, dispatched at `cli/memory.py:53-174`), plus
`dummyindex context plan-update` (`cli/plan_update.py:44-74`) and
`dummyindex context drift-ack` (`cli/drift_ack.py:29-157`). Every verb accepts
`--path`/`--root` via `parse_path_and_root` and rejects leftovers with exit 2
(`cli/memory.py:75-79`); an unknown verb is exit 2 (`cli/memory.py:69-73`). All
hook-driven verbs return 0 unconditionally.

### Tier store

- **`init`** — creates `.context/session-memory/` and one stub per `MemoryTier`
  (`now.md`, `recent.md`, `archive.md`, `core-memories.md`), each seeded with its
  `TIER_HEADINGS` H1. Idempotent and non-destructive: an existing tier file is
  never rewritten (`memory/store.py:16-31`, `dummyindex/context/domains/memory/enums.py:8-14,34-39`). The
  store has a downstream consumer beyond the hooks: the evolve domain's harvest
  reads correction sections from `now.md`/`recent.md` as evidence items
  (`dummyindex/context/domains/evolve.py:_harvest_memory`, `:300-364`) — see plan §Dependencies.
- **`roll`** — moves `now.md` sections dated before today into `recent.md`, and
  `recent.md` sections older than `recent_keep_days=7` into `archive.md`. Undated
  sections stay put; survivors re-sort newest-date-first with undated last; a
  no-move run returns early and leaves all three files byte-identical
  (`memory/roll.py:44-108`, early return at `roll.py:81-82`). Prints
  `memory roll: now→recent N, recent→archive M` (`cli/memory.py:164-174`).
- **`session-start`** — prints a `=== HANDOFF ===` + `=== MEMORY ===` block built
  from the body-below-title of `now.md`, the first 1500 chars of `recent.md`, and
  all of `core-memories.md`, capped at 4000 chars total
  (`memory/emit.py:16-17,33-61`). Silent when `<root>/.remember/` exists
  (`memory/detect.py:8-15`) or all three tiers are empty (`emit.py:40-44`).
- **`breadcrumb`** (PreCompact) — prepends a
  `## <YYYY-MM-DD HH:MM> | <branch> (auto-breadcrumb)` section to `now.md` built
  from `git diff --numstat HEAD` plus transcript turn/subagent counts, listing at
  most 8 changed files then `+k more`. If the newest section is already tagged
  `(auto-breadcrumb)` it is replaced in place rather than stacked
  (`memory/breadcrumb.py:26-54,97-127`).
- **`nudge`** (Stop) — prints a single-shot `additionalContext` JSON asking the
  agent to *offer* a handoff (never save one) when: no `.remember/`, not already
  nudged this session, no non-breadcrumb handoff dated today at the top of
  `now.md`, the transcript exists, and the session is significant — any subagent
  file, or ≥ 40 000 main-thread output tokens
  (`memory/nudge.py:23-30,70-79,103-131`).

### Drift report

`plan-update` prints a `## .context/ drift report` body, or nothing when clean;
always exit 0 (`cli/plan_update.py:44-74`). `--json` swaps the prose for a
stable machine envelope — `{"edited": [...], "anchored": {"unassigned_new_files",
"awaiting_enrichment", "drifted_features"}, "suppressed": N, "acked": N}` — with
the same exit 0 and a byte-identical plain mode (`plan_update.py:3-7,46-47`,
`_json_envelope` `:77-88`). Four markdown sections, each emitted only when
non-empty (`drift.py:223-258`): **mtime drift** per feature under an
`### Edited since docs` header (`_render_mtime_section`, `drift.py:275-318`),
**new files in no feature** (`:321-335`), **features awaiting enrichment**
(`:338-352`), and **features with committed modifications** (`:355-370`) — the
commit-anchored signals mtime structurally cannot see, de-duplicated against the
mtime `by_feature()` keys (`DriftReport.by_feature` at `drift.py:79-83`).

Per-row classification is a **basis → manifest → mtime fallback chain**
(`compute_drift`, `drift.py:115-220`). When `cache/doc-basis.json` — written by
`reconcile-stamp` alongside the manifest re-stamp
(`dummyindex/context/build/reconcile.py:293-313`, `DOC_BASIS_REL` `:327`) — has an entry for a
(feature, file) pair, the git blob sha decides: equal means the history merely
moved under the index and the row is **suppressed** (counted in
`DriftReport.suppressed_count`, rendered only as a one-line note); different is a
real edit since the docs were declared fresh. Pairs without a basis entry fall
back to the manifest sha256 cross-check (`_content_unchanged`,
`drift.py:498-510`), then to legacy mtime-only; absent/unreadable caches degrade
to empty maps so the conservative direction wins. Still-valid **acks** drop
their rows last (`_drop_acked_rows`, `drift.py:466-495`), counted in
`acked_count`. Both counters are informational — never rendered as drift
(`DriftReport`, `drift.py:52-68`). Also writes the gitignored statusline badge
best-effort (`plan_update.py:24-41`). The badge is **labeled**: `[ctx ✓]` clean,
otherwise `[ctx: E edited · A anchored]` where E is distinct edited files and A
unassigned + awaiting + extra drifted features, zero segments omitted
(`compute_badge`, `drift.py:86-112`).

### Drift acks

`dummyindex context drift-ack` records "this row is known-good" judgements as
append-only entries in the gitignored `.context/cache/drift-acks.json`
(`domains/drift_acks.py`, store at `ACKS_REL` `:20`). Three mutually exclusive
modes (`cli/drift_ack.py:3-7`): **record** (`--feature ID [--path REL]
[--reason TEXT]`; without `--path` every currently-drifting file of the feature
is acked, `_record` `:83-137`), `--list [--feature ID]` (`:59-78`), and
`--clear` (`:51-57`); mixing modes is exit 2. An entry `{feature_id, path?,
acked_sha, reason?, ts}` suppresses its drift row only while the file's current
sha still equals `acked_sha` — git blob sha on-git, content sha256 off-git — so
any edit auto-expires the dismissal. The domain is policy-free read/append/clear
(`read_acks` `:29-49`, `append_ack` `:52-77`, `clear_acks` `:80-90`);
suppression semantics live entirely in `context/drift.py`.

### Reconcile gate

The Stop hook prints a blocking `{"decision":"block","reason":…}`, a
non-blocking `{"systemMessage":…}` advisory, or nothing (`decide_block`,
`reconcile_gate.py:307-388`). Cheap gates first: `stop_hook_active`, the
persisted per-session memo (`:204-244`), and the per-root `"auto_council": false`
opt-out in `.context/config.json` (`:32-45`), over the session root plus every
submodule index (`discover_context_roots`, `:48-64`). A root is a candidate when
gate-relevant: `unassigned_new_files`, `awaiting_enrichment`, or
`drifted_features` regardless of anchor; mtime `rows` only in an anchor-less repo
(`_gate_relevant`, `:289-304`). No transcript: with a session id the memo is
marked and a `Session ownership is unavailable.` `systemMessage` returned;
headless (no session id) hard-allows (`:339-351`). Otherwise the session must be
significant and have drifted source — a subagent edit (`subagent_edit_count >
0`) or a main-thread edit outside the non-source footprint
(`_session_drifted_source`, `:257-275`).

Survivors are then **partitioned by ownership** (`partition_session_drift`,
`reconcile_scope.py:13-78`, owned by `maintenance`): only drift attributable to
the main-thread `edited_paths` stays blocking — each path belongs to its deepest
context root, and a drifted/awaiting feature counts only when an edited path is
in its `feature.json` `files` — then `_gate_relevant` is re-applied
(`reconcile_gate.py:359-371`). Nothing owned → `systemMessage` listing at most 8
roots (`unrelated_summary`, `reconcile_scope.py:81-98`), memo not marked
(`reconcile_gate.py:372-377`). Owned → memo marked, `render_block` (lone session
root) or `render_multi_block`, the unrelated summary appended to `reason`
(`:378-388`).

### Skill-compliance feedback

Two verbs turn "the user keeps telling me to use skill X" into a policy line
delivered on every subsequent prompt.

- **`mine`** (SessionStart, fully silent, stdout redirected to `/dev/null` by the
  hook at `dummyindex/context/hooks.py:140-151`) — scans this repo's main transcripts across
  every local Claude profile and rewrites the gitignored cache
  `.context/cache/skill-feedback.json`. Wrapped in a bare `except Exception: pass`
  and returns 0: generated feedback must never block SessionStart
  (`cli/memory.py:81-88`).
- **`prompt-context`** (UserPromptSubmit, second hook entry at
  `dummyindex/context/hooks.py:89-100`) — reads the hook JSON from stdin, extracts any
  directive in *this* prompt, merges it with the cache, and prints a
  `UserPromptSubmit` `additionalContext` payload with `suppressOutput: true`. Also
  fail-open: any exception yields silence and exit 0, and nothing is printed
  unless a non-empty policy body was rendered — so a partial JSON line is
  impossible (`cli/memory.py:90-122`).

What counts as a correction is a high-precision grammar, not classification
(`miner/corrections.py:35-101`): direct requests (`use the X skill`),
requirements (`you need to use the X skill`), and complaints (`why are you not
using the X skill`, `you never invoke the X skill`, `I have to keep telling you
to use the X skill`). Revocations (`don't use the X skill`, `stop the X skill`,
and the fixed phrases `normal mode` / `stop adhd mode` / `turn off adhd mode`)
reset the counter. Fenced code, inline code, and quoted spans are stripped first,
so telling Claude *about* the phrase does not register
(`corrections.py:103-107,126-129`). Every ADHD alias normalizes to `i-have-adhd`
(`corrections.py:111,115-123`).

Only rows that are genuine external human prompts are read: `type == "user"`,
`userType == "external"`, none of `isMeta`/`isSidechain`/`isCompactSummary`/
`isVisibleInTranscriptOnly`/`synthetic`, an `origin.kind` of `human` when present,
and a `cwd` resolving to this repo (`miner/scan.py:175-228,244-279`). Subagent
transcripts are excluded — only root-level JSONLs are read
(`iter_main_transcript_files`, `scan.py:72-77`). The transcript directory name
encodes a Windows drive colon as a dash (`project_dir_name`,
`miner/scope.py:28-40`); captured paths are sanitized lexically in their own
POSIX or Windows flavor — in-repo paths become relative, foreign or escaping
paths are redacted, with no filesystem access (`sanitize_signature`,
`scope.py:43-73`).

Thresholds and bounds a user can observe: two distinct post-revocation events
promote a skill (`DEFAULT_MIN_SKILL_CORRECTIONS = 2`, `dummyindex/context/domains/memory/miner/enums.py:33`); at most
8 skills and 1600 characters reach the prompt; at most 64 entries / 32 KiB live in
the cache (`miner/feedback.py:16-19`). A directive in the current prompt outranks
all history so same-turn feedback survives the cap before it is durable
(`feedback.py:226-236`), and a revocation in the current prompt suppresses that
skill's cached line immediately (`feedback.py:210-225`). The rendered text is
fixed policy prose keyed by slug — never quoted transcript content
(`feedback.py:25-37`).

Privacy properties are structural, not incidental: no prompt text is retained
past parsing (`SkillDirectiveEvent` carries a sha256 `event_key`, not the text —
`dummyindex/context/domains/memory/miner/models.py:60-73`, `stable_event_key` at `corrections.py:191-209`), the
cache is under gitignored `.context/cache/` (`.gitignore:19`), and the reader is
fail-closed — wrong schema version, a symlink, a non-regular file, an oversized
payload, a duplicate slug, or an out-of-order list all return `()`
(`feedback.py:136-200`).

### Failure-pattern miner — present, still unwired

`mine_and_feed` / `scan_transcript_store` / `write_report` mine repeated tool-call
signatures into `.context/session-memory/failure-patterns.md`
(`miner/pipeline.py:35-97`, `miner/render.py:28-72`). No CLI verb, hook, or
non-test module calls them — `memory mine` calls `refresh_skill_feedback`, not
`mine_and_feed` (`cli/memory.py:83-85`), and the memory domain re-exports only the
four skill-feedback symbols (`dummyindex/context/domains/memory/__init__.py:18-23`). Nothing reads
`failure-patterns.md` either: `render_session_start` surfaces NOW/RECENT/CORE only,
`roll_tiers` touches NOW/RECENT/ARCHIVE, and `ensure_memory_store` iterates
`MemoryTier`, which this filename is deliberately not a member of
(`miner/render.py:3-5`).

## Contracts

### Tier store

- `memory_dir(context_dir: Path) -> Path` (`memory/store.py:11-13`)
- `ensure_memory_store(context_dir: Path) -> tuple[str, ...]` (`memory/store.py:16-31`)
- `roll_tiers(context_dir: Path, *, today: date | None = None, recent_keep_days: int = 7) -> RollReport` (`memory/roll.py:44-108`)
- `render_session_start(root: Path, *, max_chars: int = 4000) -> str | None` (`memory/emit.py:33-61`)
- `run_breadcrumb(*, root: Path, main_transcript: Path | None, now: datetime) -> bool` (`memory/breadcrumb.py:118-127`)
- `build_breadcrumb_facts(root: Path, main_transcript: Path | None) -> BreadcrumbFacts` (`memory/breadcrumb.py:97-115`)
- `write_breadcrumb(context_dir: Path, facts: BreadcrumbFacts, now: datetime) -> None` (`memory/breadcrumb.py:43-54`)
- `decide_nudge(*, root: Path, main_transcript: Path | None, session_id: str, now: datetime) -> str | None` (`memory/nudge.py:103-131`)
- `is_significant(output_tokens: int, subagent_file_count: int) -> bool` (`memory/nudge.py:26-30`)
- `remember_plugin_present(root: Path) -> bool` (`memory/detect.py:8-15`)
- `split_sections(text: str) -> tuple[str, tuple[Section, ...]]` / `section_date(heading: str) -> str | None` / `render(preamble: str, sections: tuple[Section, ...]) -> str` (`memory/parse.py:24-70`)

### Transcript reader

- `resolve_session_id() -> str | None` (`memory/transcript.py:43-45`)
- `find_main_transcript(*, session_id: str | None, cwd: Path) -> Path | None` (`memory/transcript.py:58-76`)
- `read_session_signal(main_transcript: Path) -> SessionSignal` — `edited_paths` from the main transcript only; subagent edits are counted, not listed (`memory/transcript.py:88-161`)

### Drift & gate

- `compute_drift(project_root: Path) -> DriftReport` (`drift.py:115-220`; internals `_read_doc_basis` `:433-463`, `_drop_acked_rows` `:466-495`, `_content_unchanged` `:498-510`, `_manifest_shas` `:417-430`)
- `render_drift_summary(report: DriftReport) -> str` (`drift.py:223-258`; mtime section renderer `_render_mtime_section` `:275-318`)
- `compute_badge(report: DriftReport) -> str` — labeled split `[ctx: E edited · A anchored]` (`drift.py:86-112`)
- `read_acks(context_dir) -> list[dict]` / `append_ack(...) -> dict` / `clear_acks(context_dir) -> int` / `acks_path(context_dir) -> Path` (`domains/drift_acks.py:24-90`)
- `stamp_reconciled(context_dir, root, *, force=False, to_commit=None)` — on success re-stamps the manifest **and** writes `cache/doc-basis.json` (`dummyindex/context/build/reconcile.py:251-320`; `blob_sha` `:331-339`, `_write_doc_basis` `:342-361`)
- `decide_block(*, root, main_transcript, stop_hook_active, session_id="") -> str | None` — block JSON, `systemMessage` JSON, or `None` (`reconcile_gate.py:307-388`)
- `render_block(report: DriftReport) -> str` (`reconcile_gate.py:74-116`) / `render_multi_block(stale, *, base) -> str` (`156-178`)
- `discover_context_roots(root: Path) -> tuple[Path, ...]` (`reconcile_gate.py:48-64`)
- `auto_council_enabled(root: Path) -> bool` (`reconcile_gate.py:32-45`)
- Upstream, `maintenance`-owned: `partition_session_drift(stale, edited_paths, *, base, context_roots) -> (owned, unrelated)` / `unrelated_summary(stale, *, base) -> str` (`reconcile_scope.py:13-98`)

### Miner — skill feedback

- `refresh_skill_feedback(context_dir: Path, *, config_override: Path | None = None) -> tuple[RecurringSkillCorrection, ...]` (`miner/pipeline.py:128-140`)
- `scan_skill_feedback(repo_root: Path, *, config_dirs: tuple[Path, ...]) -> tuple[RecurringSkillCorrection, ...]` (`miner/pipeline.py:100-125`)
- `parse_skill_directive_events(path: Path, *, repo_root: Path, fallback_prefix: tuple[int, ...]) -> tuple[SkillDirectiveEvent, ...]` (`miner/scan.py:244-279`)
- `extract_skill_directives(text: str) -> tuple[SkillDirective, ...]` (`miner/corrections.py:132-188`)
- `directive_events(text, *, event_uuid, timestamp, session_id, occurred_at, fallback_order) -> tuple[SkillDirectiveEvent, ...]` (`miner/corrections.py:212-238`)
- `stable_event_key(*, event_uuid: str | None, timestamp: str, session_id: str, text: str) -> str` (`miner/corrections.py:191-209`)
- `aggregate_skill_corrections(events, *, min_corrections: int = 2) -> tuple[RecurringSkillCorrection, ...]` — raises `ValueError` when `min_corrections < 1` (`miner/corrections.py:251-293`)
- `normalize_skill_slug(raw: str) -> str | None` (`miner/corrections.py:115-123`)
- `write_skill_feedback(context_dir: Path, feedback) -> bool` (`miner/feedback.py:101-133`)
- `read_skill_feedback(context_dir: Path) -> tuple[RecurringSkillCorrection, ...]` (`miner/feedback.py:136-200`)
- `render_skill_feedback(cached, *, current: Iterable[SkillDirective] = ()) -> str` (`miner/feedback.py:203-247`)
- `skill_feedback_cache_path(context_dir: Path) -> Path` (`miner/feedback.py:40-42`)
- `resolve_claude_config_dir(*, override=None) -> Path` / `resolve_claude_config_dirs(*, override=None) -> tuple[Path, ...]` / `resolve_transcript_store(*, override=None) -> Path` (`miner/resolve.py:18-60`)

### Miner — failure patterns (no non-test caller)

- `scan_transcript_store(store_dir: Path, *, repo_root: Path | None = None, min_occurrences: int = 3) -> MinerReport` (`miner/pipeline.py:35-72`)
- `mine_and_feed(context_dir: Path, *, store_override=None, min_occurrences=3, all_projects=False) -> MinerReport` (`miner/pipeline.py:75-97`)
- `parse_transcript(path: Path) -> tuple[ToolCallRecord, ...]` (`miner/scan.py:124-172`)
- `canonical_signature(tool_name: str, input_data: Mapping[str, Any]) -> str` (`miner/signatures.py:47-70`)
- `detect_repeated_signatures(records_by_session, *, min_occurrences=3) -> tuple[RepeatedSignature, ...]` (`miner/signatures.py:84-134`)
- `render_report(report: MinerReport, *, repo_root: Path) -> str` / `write_report(context_dir, report, *, repo_root) -> Path` (`miner/render.py:28-72`)
- `project_dir_name(repo_root: Path) -> str` / `sanitize_signature(signature: str, *, repo_root: Path) -> str` (`miner/scope.py:28-73`)

### Shared I/O

- `write_text_atomic(path: Path, text: str) -> None` — byte-faithful by contract (`atomic_io.py:70-79`)
- `normalize_eof_newline(path: Path) -> bool` (`atomic_io.py:82-98`)
- `is_link(path: Path) -> bool` — fail-closed symlink/reparse-point check via `os.lstat` (`atomic_io.py:16-34`); no caller in this feature, consumed by `build/upgrade.py`

### CLI helpers

- `read_hook_stdin() -> dict[str, object]` — `{}` at a TTY or on malformed JSON (`cli/memory.py:20-36`)
- `resolve_transcript(hook: dict[str, object], root: Path) -> tuple[str, Path | None]` (`cli/memory.py:39-50`)

### Frozen carriers

`Section(heading, body)`, `RollReport(now_to_recent, recent_to_archive, moved_dates)`,
`BreadcrumbFacts(branch, files_changed, insertions, deletions, changed_files, main_turns, subagents)`
(`dummyindex/context/domains/memory/models.py:8-35`);
`SessionSignal(output_tokens, subagent_file_count, main_turns, edited_paths=(), subagent_edit_count=0)`
(`memory/transcript.py:25-40`);
`DriftRow(rel_path, feature_id)`,
`DriftReport(rows, unassigned_new_files=(), awaiting_enrichment=(), drifted_features=(), suppressed_count=0, acked_count=0)`
(`drift.py:44-68`);
`ToolCallRecord(tool_name, signature, is_error, output_bytes)`,
`RepeatedSignature(tool_name, signature, kind, occurrences, estimated_wasted_tokens)`,
`MinerReport(signatures=(), scanned_sessions=0, unreadable_sessions=0)`,
`SkillDirective(skill, kind)`,
`SkillDirectiveEvent(skill, kind, event_key, session_id, occurred_at, fallback_order)`,
`RecurringSkillCorrection(skill, corrections, sessions)` (`dummyindex/context/domains/memory/miner/models.py:11-82`).
Enums: `MemoryTier`, `MemoryVerb`, `AUTO_BREADCRUMB_TAG`, `TIER_HEADINGS`
(`dummyindex/context/domains/memory/enums.py:8-39`); `LoopKind`, `SkillDirectiveKind` (`dummyindex/context/domains/memory/miner/enums.py:8-24`).

### On-disk formats

`.context/cache/skill-feedback.json` — `{"schema_version": 1, "skills": [{"skill",
"corrections", "sessions"}]}`, keys exact, list sorted by `(-corrections, skill)`,
any deviation rejected wholesale (`miner/feedback.py:83-98,155-200`).
`.context/cache/nudge-state.json` — `{session_id: {"nudged_at": iso}}`, pruned to
100 (`memory/nudge.py:38-67`). `.context/cache/reconcile-gate-state.json` —
`{session_id: {"blocked_at": iso}}`, same pruning (`reconcile_gate.py:204-244`).
`.context/cache/doc-basis.json` —
`{"basis_version": 1, "features": {<fid>: {<rel_path>: <blob_sha>}}}`, written
only at the stamp boundary, corrupt-tolerant on read (wrong `basis_version` →
basis tier off) (`dummyindex/context/build/reconcile.py:323-361`, `drift.py:433-463`).
`.context/cache/drift-acks.json` — `{"schema_version": 1, "acks":
[{feature_id, path?, acked_sha, reason?, ts}]}`, append-only; missing/malformed
reads back as `[]` (`domains/drift_acks.py:20-21,29-49,93-95`).

## Examples

**Happy path: a repeated correction becomes a standing instruction.**

1. On 2026-08-04 the user types `you keep forgetting to use the i-have-adhd
   skill`. It lands in `~/.claude/projects/D--Projects-dummyindex/<session>.jsonl`
   as a `type: "user"`, `userType: "external"` row with this repo's `cwd`.
2. On 2026-08-06 a new session starts. The SessionStart hook runs
   `dummyindex context memory mine --root "$CLAUDE_PROJECT_DIR"`
   (`dummyindex/context/hooks.py:140-151`) → `refresh_skill_feedback(root/".context")`
   (`cli/memory.py:83-85`).
3. `scan_skill_feedback` resolves every local profile (`~/.claude`,
   `$CLAUDE_CONFIG_DIR`, any `~/.claude-*`) (`miner/resolve.py:27-49`), computes
   this repo's transcript dir name — `D:\Projects\dummyindex` becomes
   `D--Projects-dummyindex` (`miner/scope.py:28-40`) — and reads only the
   root-level `*.jsonl` there (`pipeline.py:100-125`).
4. `_iter_skill_json_lines` rejects every line lacking `"type":"user"` and one of
   `skill`/`normal mode`/`adhd mode` before parsing JSON, so a 40 MB transcript
   costs a substring scan, not 40 MB of `json.loads` (`scan.py:97-121`).
5. The surviving prompt matches the fourth positive pattern
   (`corrections.py:62-72`); `normalize_skill_slug` folds `i-have-adhd` through
   the alias set (`corrections.py:111,115-123`); `directive_events` attaches a
   sha256 `event_key` derived from the row's `uuid` and drops the text
   (`corrections.py:191-238`).
6. With the 2026-08-04 event plus one earlier one and no later revocation,
   `aggregate_skill_corrections` emits
   `RecurringSkillCorrection(skill="i-have-adhd", corrections=2, sessions=2)`
   (`corrections.py:251-293`).
7. `write_skill_feedback` renders it, compares against the file's current bytes,
   and rewrites `.context/cache/skill-feedback.json` atomically only if changed
   (`feedback.py:101-133`, `atomic_io.py:70-79`). Hook stdout was redirected to
   `/dev/null`, so the user sees nothing.
8. The user's next prompt fires UserPromptSubmit →
   `dummyindex context memory prompt-context`. `read_skill_feedback` validates the
   cache fail-closed; `extract_skill_directives` finds no directive in this
   prompt; `render_skill_feedback` emits the header plus the `i-have-adhd` ADHD
   rule (`feedback.py:25-33,203-247`). The CLI prints
   `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"…"},"suppressOutput":true}`
   (`cli/memory.py:103-119`) and the model receives the policy as a system
   reminder beside the prompt.
9. If that same prompt had said `normal mode`, step 8's `current` directive would
   be a `REVOCATION` and the cached `i-have-adhd` line would be dropped from the
   render on that very turn (`feedback.py:210-225`).

**Other traces.**

- `dummyindex context memory roll` on a store whose `now.md` holds one
  2026-08-05 section on 2026-08-06 → `memory roll: now→recent 1, recent→archive 0
  (dates: 2026-08-05)` (`cli/memory.py:168-173`).
- `dummyindex context plan-update` after editing `drift.py` without touching
  `features/session-memory/` → `## .context/ drift report` opening with the
  `### Edited since docs` header and
  `- **session-memory** — dummyindex/context/drift.py` (`drift.py:275-318`);
  `plan-update --json` instead prints
  `{"edited": ["dummyindex/context/drift.py"], "anchored": {…}, "suppressed": 0, "acked": 0}`
  (`plan_update.py:77-88`). The freshness badge cache now reads
  `[ctx: 1 edited]` (`drift.py:86-112`).
- A row that is checkout noise — mtime newer than the docs but bytes identical
  to the stamped doc-basis — is counted in `suppressed_count` and rendered only
  as `_1 mtime-touched file matched their doc-basis and were suppressed._`
  (`drift.py:303-308`); `context drift-ack --feature session-memory
  --reason "regenerated on every build"` then dismisses a real row until its
  bytes change (`cli/drift_ack.py:83-137`, expiry in `drift.py:466-495`).
- A significant session whose main thread edited `app/x.py`, on an anchor-less
  root with mtime rows for `app/x.py` (feature `owned`) and `old.py`, plus a
  stale `backend/` submodule → one `{"decision":"block",…}` naming `owned`, with
  `Unrelated context drift remains advisory; …` appended. Had every edit happened
  inside subagents, nothing is owned → `systemMessage` only
  (`reconcile_gate.py:359-388`, `tests/context/test_reconcile_scope.py:37-83`).
