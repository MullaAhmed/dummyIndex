# Session memory & drift signal — spec

confidence: INFERRED

## Intent

Give a fresh Claude Code session continuity it would otherwise lack, and keep the
`.context/` index honest, using three deterministic, hook-driven mechanisms that
share one transcript reader:

1. A markdown-first **session-memory store** (`now/recent/archive/core` tiers)
   that an agent maintains by prose and the CLI maintains by mechanics
   (roll, breadcrumb, init) — the local equivalent of a `remember` plugin
   (`context/domains/memory/__init__.py:1-5`).
2. A **SessionStart drift report** that names features whose source has been
   edited since their `.context/features/<id>/` docs were last touched, so the
   running session can reconcile in place (`context/drift.py:1-24`).
3. A **Stop-hook reconcile gate** that blocks session exit once when a
   substantive session leaves a `.context/` index stale, directing the agent to
   the reconcile procedure (`context/reconcile_gate.py:1-19`).

The memory mechanics carry no prose: writing/compressing summaries is the
agent's job via `/dummyindex-remember`; the deterministic layer only decides
*whether* to act and renders fixed payloads (`memory/nudge.py:1-6`,
`memory/breadcrumb.py:1-6`).

## User-visible behavior

### Memory roll, breadcrumb, and nudge

- **SessionStart emit** — `dummyindex context memory session-start` prints a
  `=== HANDOFF ===` + `=== MEMORY ===` block built from the head of `now.md`,
  `recent.md`, and `core-memories.md`, capped at 4000 chars
  (`memory/emit.py:32-60`). Silent (prints nothing) when the `remember` plugin
  is present (`<root>/.remember/` exists) or the store has no content
  (`emit.py:33-43`, `memory/detect.py:7-14`).
- **Roll** — `memory roll` relocates `now.md` sections dated before today into
  `recent.md`, and `recent.md` sections older than 7 days into `archive.md`;
  undated sections stay put; idempotent (no move ⇒ files byte-unchanged)
  (`memory/roll.py:43-106`). Prints a one-line relocation count
  (`cli/memory.py:122-133`).
- **Breadcrumb** (PreCompact hook) — `memory breadcrumb` prepends a tagged,
  factual `## <ts> | <branch> (auto-breadcrumb)` entry to `now.md` from git
  diffstat + transcript turn/subagent counts, so a session is never blank even
  if the handoff CTA is ignored; updates the existing breadcrumb in place if the
  newest entry is already one (`memory/breadcrumb.py:26-54,120-131`).
- **Nudge** (Stop hook) — `memory nudge` prints a one-shot `additionalContext`
  CTA offering the user a handoff checkpoint, only when the session is
  significant (subagents ran, or ≥40 000 main-thread output tokens), no real
  handoff was saved today, and it has not already nudged this session
  (`memory/nudge.py:23-30,101-129`). Never saves automatically; always exits 0
  (`cli/memory.py:82-94`).

### SessionStart drift report

- `dummyindex context plan-update` prints a `## .context/ drift report` markdown
  body when source has drifted from feature docs; empty stdout when nothing is
  stale; always exit 0 (`cli/plan_update.py:1-15,53-79`). Four sections, each
  emitted only when it has entries: **mtime drift** (per-feature stale-doc list,
  decays as soon as the agent edits a feature doc), **new files in no feature**,
  **features awaiting enrichment**, and **features with committed modifications**
  (`drift.py:194-222`). The last is `DriftReport.drifted_features` — features
  owning files that were modified and committed since the index was last
  reconciled — the commit-anchored signal mtime structurally cannot see on an
  anchored repo (it clears only on `reconcile-stamp`); forwarded from
  `compute_reconcile_report` (`drift.py:65-81,149,190`) and rendered by
  `_render_drifted_features_section` (`drift.py:322-339`), de-duplicated against
  the mtime `by_feature()` keys so a feature already named by an mtime row isn't
  printed twice (`drift.py:208-210`). A file whose current sha256 matches the
  manifest is not reported even if a git op rewrote its mtime
  (`drift.py:146-160,355-369`). Also writes a gitignored statusline badge cache
  best-effort (`plan_update.py:39-50,66-74`).

### Reconcile-gate Stop hook

- The gate emits a Stop `{"decision": "block", ...}` once per session when an
  index is stale in a *gate-relevant* way AND the session both did real work
  (`is_significant`) and plausibly edited source outside `.context/` /
  `.claude/` / `.claude-design/` (`reconcile_gate.py:341-398`). Block-once via
  `stop_hook_active` and a persisted per-session memo
  (`reconcile_gate.py:239-263,393-396`). Honours a `.context/config.json`
  `"auto_council": false` opt-out per root (`reconcile_gate.py:42-55`). Covers
  the session root and each submodule index beneath it
  (`reconcile_gate.py:58-76,341-398`).
- **Gate-relevant signals (F6).** All three commit-anchored signals —
  `unassigned_new_files`, `awaiting_enrichment`, and `drifted_features` — trap
  the stop independent of the commit anchor; mtime `rows` count only in an
  anchor-less repo (`_gate_relevant`, `reconcile_gate.py:320-338`). The
  `drifted_features` arm is new: an anchored steady-state session that edits +
  commits a feature's owned file now blocks, where previously it produced no
  Stop block at all (the index looked anchored-clean to mtime, and the gate did
  not consult the committed-modification signal). The block directive names the
  union of the mtime `by_feature()` keys and `drifted_features`, de-duplicated
  so a feature surfaced by both is listed once (`_merged_features`,
  `reconcile_gate.py:74-78,86,162`).
- **Reconcile-stamp directive (R7).** The block `reason` now tells a session
  that already reconciled this run to just `dummyindex context reconcile-stamp`
  and commit rather than redo the work — emitted in the single-root block, the
  multi-root block, and the advisory block (`reconcile_gate.py:103-104,182-184,
  206-210`).
- **Advisory block on unreadable transcript (F9).** When a session id is
  present but its transcript is missing/unreadable, the gate cannot confirm the
  session edited source, so instead of hard-allowing it emits a conservative
  `render_advisory_block` ("reconcile *if* this session changed code, otherwise
  just stamp") and records the per-session memo so it still fires at most once
  (`reconcile_gate.py:195-219,374-384`). A headless / no-session-id run (CI, the
  e2e subprocess) still hard-allows (`reconcile_gate.py:385`).
- **Source-drift keyed on subagent edits (F10).** A session counts as
  source-drifting either when a dispatched subagent actually *edited* a file
  (`subagent_edit_count > 0`) or when the main thread edited a file outside the
  non-source footprint (`_session_drifted_source`,
  `reconcile_gate.py:278-306`). Keying on the count of subagent Edit/Write/
  NotebookEdit tool-uses — parsed from `subagents/agent-*.jsonl`
  (`transcript.py:97-134`) — rather than the bare presence of subagent
  transcript files means a read-only research fan-out no longer trips a spurious
  block, while a `/dummyindex-build`-style run whose edits land inside subagents
  still blocks. The `is_significant` `subagent_file_count` heuristic is
  unchanged (`nudge.py:26-30`).
- **Shared non-source predicate (F11).** The main-thread source check uses the
  shared `is_non_source_path` predicate imported from `build/reconcile.py`
  (covering `.context` + `.claude` / `.claude-design`), replacing the gate's old
  duplicated `_NON_SOURCE_PREFIXES` tuple so the reconcile delta, drift report,
  and gate agree on what "not feature-ownable work" means
  (`reconcile.py:371-381`, `reconcile_gate.py:304`).

## Contracts

Public functions (signatures + `path:range`):

- `ensure_memory_store(context_dir: Path) -> tuple[str, ...]` — idempotent,
  non-destructive tier creation (`memory/store.py:15-30`).
- `memory_dir(context_dir: Path) -> Path` (`memory/store.py:10-12`).
- `roll_tiers(context_dir: Path, *, today: date | None = None, recent_keep_days: int = 7) -> RollReport`
  (`memory/roll.py:43-106`).
- `render_session_start(root: Path, *, max_chars: int = 4000) -> str | None`
  (`memory/emit.py:32-60`).
- `decide_nudge(*, root: Path, main_transcript: Optional[Path], session_id: str, now: datetime) -> Optional[str]`
  (`memory/nudge.py:101-129`).
- `is_significant(output_tokens: int, subagent_file_count: int) -> bool`
  (`memory/nudge.py:26-30`).
- `run_breadcrumb(*, root: Path, main_transcript: Optional[Path], now: datetime) -> bool`
  (`memory/breadcrumb.py:120-131`).
- `build_breadcrumb_facts(root: Path, main_transcript: Optional[Path]) -> BreadcrumbFacts`
  (`memory/breadcrumb.py:97-117`).
- `remember_plugin_present(root: Path) -> bool` (`memory/detect.py:7-14`).
- `resolve_session_id() -> Optional[str]` (`memory/transcript.py:43-45`).
- `find_main_transcript(*, session_id: Optional[str], cwd: Path) -> Optional[Path]`
  (`memory/transcript.py:58-76`).
- `read_session_signal(main_transcript: Path) -> SessionSignal`
  (`memory/transcript.py:137-176`).
- `split_sections(text: str) -> tuple[str, tuple[Section, ...]]` /
  `section_date(heading: str) -> str | None` /
  `render(preamble: str, sections: tuple[Section, ...]) -> str`
  (`memory/parse.py:22-64`).
- `compute_drift(project_root: Path) -> DriftReport` (`drift.py:126-190`).
- `render_drift_summary(report: DriftReport) -> str` (`drift.py:194-222`).
- `compute_badge(report: DriftReport) -> str` (`drift.py:99-119`).
- `is_non_source_path(path: str) -> bool` (`build/reconcile.py:371-381`).
- `decide_block(*, root: Path, main_transcript: Path | None, stop_hook_active: bool, session_id: str = "") -> str | None`
  (`reconcile_gate.py:341-398`).
- `render_advisory_block(stale: Sequence[tuple[Path, DriftReport]], *, base: Path) -> str`
  (`reconcile_gate.py:195-219`).
- `discover_context_roots(root: Path) -> tuple[Path, ...]`
  (`reconcile_gate.py:58-76`).
- `auto_council_enabled(root: Path) -> bool` (`reconcile_gate.py:42-55`).
- `write_text_atomic(path: Path, text: str) -> None` /
  `normalize_eof_newline(path: Path) -> bool` (`atomic_io.py:11-46`).

CLI surface: `dummyindex context memory {session-start|roll|init|nudge|breadcrumb}`
(`memory/enums.py:16-24`, `cli/memory.py:54-134`); `dummyindex context plan-update`
(`cli/plan_update.py:53-79`).

Frozen data carriers: `Section(heading, body)`,
`RollReport(now_to_recent, recent_to_archive, moved_dates)`,
`BreadcrumbFacts(...)` (`memory/models.py:7-34`);
`SessionSignal(output_tokens, subagent_file_count, main_turns, edited_paths=(), subagent_edit_count=0)`
(`memory/transcript.py:28-49`) — `subagent_file_count` feeds the nudge
significance heuristic; `subagent_edit_count` (count of subagent
Edit/Write/NotebookEdit tool-uses) is the gate's source-drift signal;
`DriftRow(rel_path, feature_id)`,
`DriftReport(rows, unassigned_new_files=(), awaiting_enrichment=(), drifted_features=())`
(`drift.py:56-97`) — `drifted_features` is the committed-modification signal
(features owning files modified + committed since the last reconcile).

## Examples

- Emit memory at session start:
  `dummyindex context memory session-start` → prints handoff+memory block, or
  nothing if `.remember/` exists or store empty (`emit.py:32-43`).
- Roll then save:
  `dummyindex context memory roll` → `memory roll: now→recent 1, recent→archive 0`
  (`cli/memory.py:126-133`).
- Drift on SessionStart:
  `dummyindex context plan-update` → `## .context/ drift report` listing
  `- **session-memory** — dummyindex/context/drift.py` when `drift.py` is edited
  but `features/session-memory/plan.md` is older (`drift.py:253-294`).
- Committed-modification drift on an anchored repo:
  after editing + committing `drift.py` (owned by `session-memory`) without
  reconcile-stamping, the report adds a **Features with committed modifications**
  section naming `- **session-memory**` (`drift.py:322-339`).
- Gate at session end (substantive, source-editing, stale index):
  Stop hook receives `{"decision":"block","reason":"dummyindex reconcile gate: …"}`
  (`reconcile_gate.py:81-165,341-398`).
- Gate on an anchored steady-state session that edited + committed an owned file
  (F6): same Stop block now fires via the `drifted_features` arm, where it
  previously hard-allowed (`reconcile_gate.py:320-338`).
- Advisory gate when the transcript is unreadable but a session id is present
  (F9): Stop hook receives `{"decision":"block","reason":"dummyindex reconcile
  gate (advisory): …"}` (`reconcile_gate.py:195-219,374-384`).
