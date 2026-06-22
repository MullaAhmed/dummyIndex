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
  stale; always exit 0 (`cli/plan_update.py:1-15,53-79`). Three sections, each
  emitted only when it has entries: **mtime drift** (per-feature stale-doc list,
  decays as soon as the agent edits a feature doc), **new files in no feature**,
  and **features awaiting enrichment** (`drift.py:178-205`). A file whose
  current sha256 matches the manifest is not reported even if a git op rewrote
  its mtime (`drift.py:146-160,355-369`). Also writes a gitignored statusline
  badge cache best-effort (`plan_update.py:39-50,66-74`).

### Reconcile-gate Stop hook

- The gate emits a Stop `{"decision": "block", ...}` once per session when an
  index is stale in a *gate-relevant* way (commit-anchored signal, or mtime
  drift in an anchor-less repo) AND the session both did real work
  (`is_significant`) and plausibly edited source outside `.context/` /
  `.claude/` / `.claude-design/` (`reconcile_gate.py:284-346`). Block-once via
  `stop_hook_active` and a persisted per-session memo
  (`reconcile_gate.py:202-226,315-318`). Honours a `.context/config.json`
  `"auto_council": false` opt-out per root (`reconcile_gate.py:42-55`). Covers
  the session root and each submodule index beneath it
  (`reconcile_gate.py:58-76,322-329`).

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
  (`memory/transcript.py:84-121`).
- `split_sections(text: str) -> tuple[str, tuple[Section, ...]]` /
  `section_date(heading: str) -> str | None` /
  `render(preamble: str, sections: tuple[Section, ...]) -> str`
  (`memory/parse.py:22-64`).
- `compute_drift(project_root: Path) -> DriftReport` (`drift.py:112-175`).
- `render_drift_summary(report: DriftReport) -> str` (`drift.py:178-205`).
- `compute_badge(report: DriftReport) -> str` (`drift.py:91-109`).
- `decide_block(*, root: Path, main_transcript: Path | None, stop_hook_active: bool, session_id: str = "") -> str | None`
  (`reconcile_gate.py:298-346`).
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
`SessionSignal(output_tokens, subagent_file_count, main_turns, edited_paths=())`
(`memory/transcript.py:27-40`);
`DriftRow(rel_path, feature_id)`,
`DriftReport(rows, unassigned_new_files=(), awaiting_enrichment=())`
(`drift.py:56-88`).

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
  but `features/session-memory/plan.md` is older (`drift.py:224-256`).
- Gate at session end (substantive, source-editing, stale index):
  Stop hook receives `{"decision":"block","reason":"dummyindex reconcile gate: …"}`
  (`reconcile_gate.py:79-124,341-346`).
