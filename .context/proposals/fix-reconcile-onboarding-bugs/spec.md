# Spec — Fix CLAUDE.md onboarding-dangling and Stop-gate reconcile-blindness bugs from the audit

> Source: `.context/audits/two-reconciliation-onboarding-bugs-1-an-old-claude-md-file-o/report.md`.
> Two confirmed HIGH bugs + the medium/low hardening and the zero-coverage
> test gaps the panel ranked as the reason both bugs shipped green.

## Intent

**Problem.** The audit confirmed two real defects, plus the test absences that let them reach `main`:

1. **CLAUDE.md left dangling on fresh install (HIGH).** A pre-existing root `./CLAUDE.md` is never folded into the managed setup on a fresh `install` / `init` / first build. The only code that relocates it — `migrate_claude_md_location` (`cli/migrate.py:73`) — is wired *solely* into `refresh-indexes` (`cli/refresh.py:32`); both real build paths (`installer/install.py:271`, `context/build/runner.py:263`) call `bootstrap_claude_md(.claude/CLAUDE.md)` directly and never touch the root file. Even when reached, the migrator returns early for a root file with **no** managed block, leaving hand-written user content dangling. `cli/migrate.py` has **zero tests**.

2. **Stop gate blind to committed modifications of owned files (HIGH).** On an *anchored* repo (the steady state after one `reconcile-stamp`), a session that modifies + commits a file owned by an existing feature produces **no** Stop block: the mtime `rows` signal is suppressed once an anchor is live (`reconcile_gate.py:293`), and the `drifted_features` signal that *does* detect committed modifications (`build/reconcile.py:174-179`) is dropped by `compute_drift` (`drift.py:171-175`) and never reaches the gate. The user's "no reconcile after Stop" framing is otherwise refuted — the gate exists and fires; it is *incomplete*, not absent.

**Who.** Every dummyindex user: (1) anyone installing onto a repo that already had a `CLAUDE.md`; (2) every steady-state repo whose sessions edit existing code — i.e. the common case.

**Decision taken (was an open question, now resolved):** when a fresh install/build finds a root `./CLAUDE.md`, **consolidate** — carry any user content into `.claude/CLAUDE.md` (preserved above the managed block) and **delete the root file**. This unifies the legacy-managed-block case and the plain-user-file case into one "fold → single canonical file" behavior. No two-file end state.

## Contracts

### Issue 1 — single CLAUDE.md reconciliation seam (`context/output/`)

New domain helper `reconcile_claude_md(out_root: Path) -> ClaudeMdReconcileResult` in `context/output/claude_md.py`:

- **Inputs:** the project root.
- **Behavior (idempotent):**
  - Read `<root>/CLAUDE.md` (root) and `<root>/.claude/CLAUDE.md` (canonical) if present.
  - Strip any dummyindex managed block from the root file → its residue is user content.
  - Build canonical content = `[root user residue]` + `[existing .claude/ user content with its managed block stripped]` + a single fresh managed block (reuse `generate_managed_block` / markers from `bootstrap.py`). De-duplicate so user residue is never doubled on re-run.
  - Write `.claude/CLAUDE.md` atomically (reuse `bootstrap.py:_atomic_write` / `write_text_atomic`).
  - Delete `<root>/CLAUDE.md` (only after the canonical write succeeds). If the root file is whitespace-only after stripping, still delete it.
- **Output:** a frozen `ClaudeMdReconcileResult` (action enum: `created` | `consolidated` | `updated` | `noop`, plus paths + a human message). **No `print`** — the helper returns; the CLI prints.
- **Invariants:** exactly one managed block, in `.claude/CLAUDE.md`; user content never lost; never two competing `CLAUDE.md` files after it runs; safe to run repeatedly (idempotent — a second run is `noop`/`updated`, not a re-consolidation that re-appends).
- **Errors:** an unreadable root file or a failed canonical write degrades to a non-fatal result with a warning message; it never crashes the build and never deletes root unless the canonical write succeeded.

Wiring (the seam the audit says is missing): `context/build/runner.py:build_all` and `installer/install.py:_auto_init_project` call `reconcile_claude_md` instead of `bootstrap_claude_md` directly. `cli/migrate.py:migrate_claude_md_location` becomes a thin wrapper over the same helper (restores the wire-only CLI split; `refresh-indexes` keeps working). Also fix `installer/install.py:171`'s `"dummyindex" in content` substring probe → a marker-based check.

### Issue 2 — gate consults committed modifications (`drift.py` + `reconcile_gate.py`)

- `DriftReport` (`context/drift.py:64-77`) gains `drifted_features: tuple[str, ...] = ()` (defaults empty → existing equality/΅callers unaffected). `compute_drift` forwards `reconcile.drifted_features` at **both** return points. `has_drift`, `compute_badge`, and `render_drift_summary` account for it.
- `_gate_relevant` (`reconcile_gate.py:284-295`) returns `True` when `report.drifted_features` is non-empty — a commit-anchored signal, so it *always* counts (like `unassigned_new_files` / `awaiting_enrichment`), independent of `_has_live_anchor`. The mtime/anchor three-oracle behavior is otherwise preserved (mtime stays a SessionStart advisory).
- `render_block` / `_render_section` / `render_multi_block` include the drifted features in the reconcile directive, merged with the existing `by_feature()` set and de-duplicated.

### Issue 2 — gate hardening (medium/low from the audit)

- **F9 (medium):** when an index is gate-relevant but the main transcript is missing/unreadable (`reconcile_gate.py:332-333`), emit a conservative advisory block instead of a hard-allow.
- **F11 (medium):** export one canonical non-source / tool-path predicate from `context/build/reconcile.py` and import it in `reconcile_gate.py` (`_NON_SOURCE_PREFIXES`, line 39), replacing the test-enforced duplication.
- **F10 (low):** `_session_drifted_source` should count subagent **edits**, not the bare presence of subagent transcript files (`reconcile_gate.py:257-258` + the `subagent_file_count` source in `context/domains/memory/transcript.py`), so a read-only research fan-out no longer trips a spurious block.

### Known limitation (explicitly out of scope, low)

A *net-new* file added in the very first session **before any** `reconcile-stamp` is caught by neither `rows` (unmapped → no row) nor `unassigned_new_files` (needs a git diff against an anchor that doesn't exist yet). This is inherent to the no-anchor state and is a low edge — documented here, not fixed in this proposal.

### NOT a code bug — audit model-enum (removed from scope)

The audit's "Note A" (audit CLI rejecting `opus-4.8`) is **not a source defect**: `ModelChoice` (`context/domains/config.py:61`) already carries `opus-4.8`, and `audit/workspace.py:resolve_model:85-106` already validates against it and falls back to `.context/config.json`. `grep opus-4.7 dummyindex/` is empty. The rejection seen during the audit came from a **stale installed CLI binary** predating the `opus-4.8` commit (051e7a9). The remedy is `/dummyindex-update` (or reinstalling the CLI), **not** a code change. No task.

### Decisions folded from the critique panel

- **Consolidation must be inode-safe.** If root `CLAUDE.md` and `.claude/CLAUDE.md` are the same file (symlink/hardlink), treat as the single-canonical case — no consolidation, no delete.
- **Never let `UnbalancedMarkersError` escape** the helper; strip *all* managed blocks (loop, not a single `.index`), and treat user prose that merely quotes the marker strings as content (anchor stripping to dummyindex-written blocks only).
- **Gate may newly block reconciled-but-unstamped sessions** (drifted_features clears only on `reconcile-stamp`). This is intended; the directive must tell such users to just `reconcile-stamp` rather than re-reconcile, and block-once keeps it to a single prompt per session.
- **F9 conservative block is scoped** to "session id present but its transcript is unreadable", NOT "no session id at all" — headless/non-Claude runs (CI, the e2e subprocess) must still hard-allow.
- **F10 changes the source-drift signal only**, never `is_significant` (which legitimately keeps its `subagent_file_count` heuristic). The subagent JSONL envelope must be verified so build-style (subagent-edit) runs still block.

## Acceptance

**Issue 1 — CLAUDE.md consolidation**
- [ ] On a fresh `install`/`init`/`build_all` over a repo with a root `./CLAUDE.md` containing **only user content** (no managed block): after the run `./CLAUDE.md` is gone and `.claude/CLAUDE.md` exists containing the user's original text **and** exactly one managed block.
- [ ] Same when the root `./CLAUDE.md` already contains a (legacy) managed block: root deleted, `.claude/CLAUDE.md` has the user residue + exactly one current managed block.
- [ ] A **re-install onto an already-enriched repo** (the `status.enriched` branch of `_auto_init_project`) with a dangling root `./CLAUDE.md` also consolidates — not only the full first-build path.
- [ ] When `.claude/CLAUDE.md` already holds user content + a managed block and a root file also exists, consolidation merges both bodies with **no duplication** and a single managed block.
- [ ] **Inode-safety:** when root `./CLAUDE.md` is a symlink/hardlink to `.claude/CLAUDE.md` (same inode), the helper performs no consolidation and no delete, returns `noop`/`updated`, and the file survives intact.
- [ ] **Marker robustness:** a root or `.claude/` file with unbalanced or duplicate managed-block markers does **not** raise / crash `build_all`; all dummyindex blocks are stripped and exactly one is re-emitted (or the helper degrades to a warning result with root untouched).
- [ ] **User-content-quotes-marker:** a user `CLAUDE.md` whose prose literally contains the marker substrings is preserved verbatim, and a second run is still idempotent.
- [ ] `reconcile_claude_md` is idempotent: a second run on unchanged input yields byte-identical `.claude/CLAUDE.md` (same package version) and returns `action == noop` (never a re-`consolidated`).
- [ ] **Write-failure invariant:** if the canonical `.claude/CLAUDE.md` write fails (injected), root `./CLAUDE.md` is left intact and the result is a non-fatal warning.
- [ ] `reconcile_claude_md` returns a structured `ClaudeMdReconcileResult` and performs **no** `print`; `cli/migrate.py` prints from the returned result; `migrate_legacy_layout`'s `graph/` migration is unchanged.
- [ ] Global skill registration (`install.py`, scope=user) is skipped only when the `_SKILL_REGISTRATION` **sentinel** is present; a `~/.claude/CLAUDE.md` containing the bare word "dummyindex" but not the sentinel gets the block appended (and is not re-appended on a second install).

**Issue 2 — Stop gate**
- [ ] `decide_block` returns a Stop **block** for a **genuinely stamped, anchored** `.context/` (assert `_has_live_anchor(root) is True` reached without monkeypatch) when the session modified + committed a file owned by an existing feature; the block `reason` names that feature. **The identical test run against the pre-fix code FAILS (no block)** — proving it captures F6.
- [ ] The pre-existing `test_silent_when_only_mtime_drift_and_anchor_present` is updated so it no longer asserts silence for a committed owned-file modification.
- [ ] `decide_block` still blocks on an anchor-less repo via the mtime path (no regression) and still allows trivial / planning-only / opted-out sessions.
- [ ] A **reconciled-but-unstamped** session is blocked at most **once** (block-once memo / `stop_hook_active` re-entry guard), and the directive tells the user to `reconcile-stamp` rather than reconcile again.
- [ ] `DriftReport.drifted_features` is appended as the **last** field (defaulted), populated by `compute_drift` on an anchored repo with committed owned-file modifications; `has_drift`, `compute_badge`, and `render_drift_summary` reflect it **de-duplicated** against `by_feature()` (no double-count of a feature already named by mtime rows).
- [ ] When a session **id is present** but its transcript is unreadable and an index is gate-relevant, `decide_block` emits a conservative advisory; a **headless / no-session-id** run still hard-allows.
- [ ] `reconcile_gate`'s non-source check is sourced from a single shared predicate in `build/reconcile.py` that covers **`.context` + tool paths** (parity with the old `_NON_SOURCE_PREFIXES`); the old sync-enforcing test is replaced by a direct test of the shared predicate.
- [ ] A read-only subagent fan-out (no subagent edits) does not by itself make `_session_drifted_source` return `True`; a **build-style** subagent transcript containing an `Edit`/`Write` tool-use still makes it return `True` (build-detection preserved); `is_significant` is unchanged.

**Whole**
- [ ] Full suite green on the 3.10/3.12 matrix (`python -m pytest tests/ -q --tb=short`), every new test carrying a `@pytest.mark.{unit,integration}` marker.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `tree-enrich`
- `audit-panel`
- `source-docs`
- `agent-instructions`
- `equip`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
