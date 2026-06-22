# Supporting

<!-- dummyindex:merged:begin -->
### Merged from `community-8`

**Files involved:**

- `dummyindex/cli/plan_update.py`
- `dummyindex/context/domains/memory/transcript.py`
- `dummyindex/context/drift.py`
- `dummyindex/context/reconcile_gate.py`
- `tests/context/test_drift.py`
- `tests/context/test_reconcile_gate.py`

**Original notes:**

# community-8 — spec

confidence: INFERRED

## Intent

This feature is the "is the index still trustworthy?" signal for a `.context/` repo. It answers one question — has the source moved on without the docs keeping up? — and surfaces the answer at two moments: when a session starts (an advisory markdown report appended to the agent's prompt) and when a substantial session tries to end (a one-shot Stop gate that asks the agent to reconcile before leaving). It deliberately never writes or stamps the index itself; it only computes drift and renders a directive, leaving every mutation to the live agent so the commit-anchor invariant holds. A third, lightweight output — a short freshness badge string distilled from the same drift report — feeds a statusline so the index's health is visible at a glance without re-scanning on every prompt.

## User-visible behavior

**SessionStart drift report.** `dummyindex context plan-update` runs from the SessionStart hook, computes drift, and prints a markdown body to stdout that Claude Code appends to the session as `additionalContext`; exit code is always 0 because drift is a signal, not an error (`dummyindex/cli/plan_update.py:9-14`). On a clean index it prints nothing (`plan_update.py:76-78`). When there is drift the body is headed `## .context/ drift report` and renders up to three sections: stale per-feature docs (the mtime signal), net-new files owned by no feature, and features placed-but-not-enriched (`drift.py:189-205`). The mtime section names each drifted feature and its files and reminds the agent the entry clears once a feature doc is edited (`drift.py:235-256`); the two commit-anchored sections only appear when the index carries a usable anchor and point at the reconcile procedure (`drift.py:259-290`).

**Stop reconcile gate.** When a substantial session that plausibly edited source tries to end and an index is still stale in a gate-relevant way, the gate emits a single Stop `decision: block` whose `reason` is an agent-facing reconcile directive — run the council/reconcile, `reconcile-stamp`, commit the refreshed index — naming exactly the drifted features, new files, and awaiting-enrichment features (`reconcile_gate.py:79-124`). It blocks at most once per session, covers the session root and every submodule index beneath it, and is silenced by `"auto_council": false` in `.context/config.json` (`reconcile_gate.py:298-346`).

**Freshness badge string.** The same `DriftReport` distills to a one-token statusline string: `"[ctx ✓]"` when nothing is stale, otherwise `"[ctx: N drift]"` where `N` is the count of distinct drifted items (`drift.py:91-109`). `plan-update` caches this string under `.context/cache/freshness-badge` on the same run, best-effort and fully isolated from the drift report, so a separate statusline reader can show it off the hot path (`plan_update.py:39-50`, `plan_update.py:71-74`).

## Contracts

### Drift scan (`dummyindex/context/drift.py`)

- `class DriftRow` — frozen; `rel_path: str`, `feature_id: str`. One source file newer than the docs of one feature that owns it (`drift.py:56-61`).
- `class DriftReport` — frozen; `rows: tuple[DriftRow, ...]`, `unassigned_new_files: tuple[str, ...] = ()`, `awaiting_enrichment: tuple[str, ...] = ()` (`drift.py:64-88`).
  - `DriftReport.has_drift -> bool` — true when any of the three fields is non-empty (`drift.py:78-82`).
  - `DriftReport.by_feature() -> dict[str, tuple[str, ...]]` — `rows` grouped by `feature_id`, paths sorted (`drift.py:84-88`).
- `compute_drift(project_root: Path) -> DriftReport` — scan entry point. Empty `DriftReport(rows=())` when `.context/features/` is absent; otherwise mtime rows cross-filtered by the manifest sha plus the two commit-anchored signals from `compute_reconcile_report` (`drift.py:112-175`).
- `render_drift_summary(report: DriftReport) -> str` — the SessionStart markdown body; `""` when `not report.has_drift` (`drift.py:178-205`).
- `compute_badge(report: DriftReport) -> str` — pure (no I/O, no side effects); `"[ctx ✓]"` on no drift, else `"[ctx: N drift]"` with `N = distinct rel_path in rows + len(unassigned_new_files) + len(awaiting_enrichment)` (`drift.py:91-109`).

### CLI boundary (`dummyindex/cli/plan_update.py`)

- `run(args: list[str]) -> int` — `plan-update` entry; rejects unknown args with exit 2, no-ops on a non-`.context/` repo, computes drift, writes the badge cache (swallowing every error), prints the summary, returns 0 (`plan_update.py:53-79`).
- `badge_cache_path(context_dir: Path) -> Path` — `.context/cache/freshness-badge`; the single source of truth shared with the statusline reader (`plan_update.py:31-36`).
- `_write_badge(context_dir, report) -> None` — atomic write of `compute_badge(report)` to the cache (`plan_update.py:39-50`).

### Reconcile gate (`dummyindex/context/reconcile_gate.py`)

- `decide_block(*, root: Path, main_transcript: Path | None, stop_hook_active: bool, session_id: str = "") -> str | None` — the gate entry; the Stop block JSON to print, or `None` to allow the stop (`reconcile_gate.py:298-346`).
- `auto_council_enabled(root: Path) -> bool` — opt-out; `False` only on explicit `"auto_council": false` (`reconcile_gate.py:42-55`).
- `discover_context_roots(root: Path) -> tuple[Path, ...]` — the session root first, then each submodule under it carrying its own `.context/` (`reconcile_gate.py:58-76`).
- `render_block(report: DriftReport) -> str` — single-root Stop block JSON; per-category remedy only when that category has entries (`reconcile_gate.py:79-124`).
- `render_multi_block(stale: Sequence[tuple[Path, DriftReport]], *, base: Path) -> str` — multi-index Stop block, one scoped section per root (`reconcile_gate.py:160-182`).
- `_gate_relevant(report: DriftReport, ctx_root: Path) -> bool` — commit-anchored signals always count; mtime rows count only when the repo has no live anchor (`reconcile_gate.py:284-295`).
- `_has_live_anchor(root: Path) -> bool` — true when `compute_reconcile_report` returns a present, non-orphaned `indexed_commit` (`reconcile_gate.py:229-238`).
- `_session_drifted_source(signal_edited: tuple[str, ...], base: Path, *, subagent_file_count: int = 0) -> bool` — true when subagents ran, or a main-thread edit landed outside `.context/` / `.claude/` / `.claude-design` (`reconcile_gate.py:241-270`).
- `already_blocked(root, session_id) -> bool` / `mark_blocked(root, session_id) -> None` — the per-session block-once memo under `.context/cache/reconcile-gate-state.json` (`reconcile_gate.py:185-226`).

### Session signal (`dummyindex/context/domains/memory/transcript.py`)

- `read_session_signal(main_transcript: Path) -> SessionSignal` — coarse, best-effort signals (`output_tokens`, `subagent_file_count`, `main_turns`, `edited_paths`) the gate uses to decide whether the session did real work and touched source (`transcript.py:84-121`).

## Examples

**Happy-path: source edited newer than its docs → drift row → report.** A repo has `.context/features/feat-x/feature.json` listing `pkg/a.py`, and `feat-x`'s `spec.md`/`plan.md` were last touched before `pkg/a.py` was edited. `compute_drift(project_root)` builds the file→feature map (`drift.py:129`), sees `pkg/a.py`'s mtime exceed `feat-x`'s newest doc mtime, the manifest sha no longer matches (real content change), and appends `DriftRow(rel_path="pkg/a.py", feature_id="feat-x")` (`drift.py:160-168`). The returned `DriftReport(rows=(that row,))` has `has_drift == True`; `render_drift_summary` emits `## .context/ drift report` with the line `- **feat-x** — pkg/a.py` under the mtime section (`drift.py:235-256`). If instead a checkout merely rewrote `pkg/a.py`'s mtime but its bytes still match the manifest sha, `_content_unchanged` returns true and no row is produced (`drift.py:160`, `drift.py:355-369`).

**Badge render.** `compute_badge(DriftReport(rows=()))` → `"[ctx ✓]"`. For `DriftReport(rows=(DriftRow("a.py","feat-x"), DriftRow("a.py","feat-y"), DriftRow("b.py","feat-x")), unassigned_new_files=(), awaiting_enrichment=())` the distinct files are `{a.py, b.py}`, so the badge is `"[ctx: 2 drift]"` — a file owned by two features counts once, mirroring `_render_mtime_section`'s distinct-file count (`drift.py:104-108`, `drift.py:230`). Adding `unassigned_new_files=("pkg/new.py",)` and `awaiting_enrichment=("placed-feat",)` raises it to `"[ctx: 4 drift]"`.

<!-- dummyindex:merged:end -->
