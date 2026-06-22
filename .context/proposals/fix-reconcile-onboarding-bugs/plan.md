# Plan — Fix CLAUDE.md onboarding-dangling and Stop-gate reconcile-blindness bugs from the audit

> Ordered tasks; file paths explicit; reused symbols cited from real source.
> Revised after the critique panel (BLOCK/HIGH findings folded — see the
> `proposal.json` notes and the spec's "Decisions folded" + "Acceptance").
> Conventions: `context/output/` owns renderers and is the right home for the
> CLAUDE.md helper (logic must leave wire-only `cli/migrate.py`); tests use
> `tmp_path`/`SAMPLE_REPO`, require a `@pytest.mark.{unit,integration}` marker,
> prefer real filesystem shapes over mocking (`conventions/testing.md`).
>
> Implementation tasks run `— via python-implementer`; test tasks `— via
> python-tester` (the build keyword-router would pick these anyway; tagged for
> clarity). The `audit Note A` model-enum item was **dropped**: the source is
> already correct (`ModelChoice = opus-4.8`, `resolve_model` reuses config); the
> rejection seen was a stale installed CLI → `/dummyindex-update`, not code.

## Issue 1 — single CLAUDE.md reconciliation seam

1. **Create the domain helper** `dummyindex/context/output/claude_md.py` (NEW) — via python-implementer.
   - Frozen `ClaudeMdReconcileResult` dataclass + a `(str, Enum)` action member (`created|consolidated|updated|noop`) + `root_path`, `canonical_path`, `message` (`tuple` fields; mirror `context/domains/features/models.py`; matches the `*Result` family e.g. `reconcile.py`'s result dataclasses).
   - `reconcile_claude_md(out_root: Path) -> ClaudeMdReconcileResult`: fold root `CLAUDE.md` (managed-block or plain) + any existing `.claude/CLAUDE.md` user content into one canonical `.claude/CLAUDE.md` with a single managed block, then delete root. **Reuse** `BEGIN_MARKER`, `END_MARKER`, `generate_managed_block` from `context/output/bootstrap.py`; use the public `write_text_atomic` (`context/domains/atomic_io.py`) as the **single** atomic writer (do not also call bootstrap's private `_atomic_write`). Port + correct the residue logic from `cli/migrate.py:94-138`.
   - **Folded BLOCK/HIGH safety requirements:**
     - **Inode-safety (R1):** `Path.resolve()` + `os.path.samefile` on root vs canonical *before* any read/write; if same inode → return `noop`/`updated`, no consolidation, no delete.
     - **Marker robustness (R2):** strip **all** managed blocks via a loop (not a single `.index`); wrap marker handling so `bootstrap.UnbalancedMarkersError` never escapes → return a warning result, root untouched.
     - **User-content-quotes-marker (R3):** anchor stripping to dummyindex-written blocks (full begin→end pairs); never mistake quoted marker substrings in prose for a block; keep idempotency.
     - **Idempotent merge (R4):** before merging root residue into canonical, skip residue already present in canonical, so a failed-delete + rerun never doubles user content.
     - **Write-then-delete ordering:** delete root only after the canonical write succeeds; OSError on read/write/delete → non-fatal warning result.

2. **Reduce `cli/migrate.py` to a wire-only wrapper** (`dummyindex/cli/migrate.py`) — via python-implementer.
   - Rewrite `migrate_claude_md_location` to call `reconcile_claude_md` (task 1) and `print` from the returned `ClaudeMdReconcileResult`. Keep `migrate_legacy_layout` and its `graph/` migration **and its existing prints** intact (out of scope — `refresh-indexes` unchanged). Depends on task 1.

3. **Wire first-build to the helper** (`dummyindex/context/build/runner.py:19,262-263`) — via python-implementer.
   - Replace the direct `bootstrap_claude_md(out_root / ".claude" / "CLAUDE.md")` in `build_all` with `reconcile_claude_md(out_root)`; update the import at `:19`. Depends on task 1.

4. **Wire install to the helper — both branches** (`dummyindex/installer/install.py:236,~263,271`) — via python-implementer.
   - In `_auto_init_project`, replace **every** `bootstrap_claude_md(project_root/".claude"/"CLAUDE.md")` call with `reconcile_claude_md(project_root)` — the full-build branch **and** the enriched-preserved (`status.enriched`) branch (HIGH: the panel flagged the enriched branch was missed) — and drop the now-unused `bootstrap_claude_md` import. Behavior identical when no root `CLAUDE.md` exists. Depends on task 1.

5. **Fix the skill-registration idempotency probe** (`dummyindex/installer/install.py:167-181`) — via python-implementer.
   - Replace `"dummyindex" in content` (line 171) with a check for a stable substring of the **`_SKILL_REGISTRATION`** sentinel (NOT `bootstrap.BEGIN_MARKER` — different marker; probing the wrong one would re-append on every install — R6). Same file as task 4 → must be a **different wave** from task 4.

## Issue 2 — gate consults committed modifications

6. **Plumb `drifted_features` through the drift report** (`dummyindex/context/drift.py`) — via python-implementer.
   - Append `drifted_features: tuple[str, ...] = ()` as the **LAST** field of `DriftReport` (`:64-77`) — last + defaulted so positional constructions (`drift.py:123`) don't shift (R8). Forward `reconcile.drifted_features` at **both** `compute_drift` returns (`:131-135`, `:171-175`). Extend `has_drift` (`:78-82`), `compute_badge` (`:91-109`), `render_drift_summary` (`:178-205`) — **de-duplicating** drifted_features against `by_feature()` keys so one edited file isn't counted/printed twice (R9). Reuse `ReconcileReport.drifted_features` (`build/reconcile.py:174-179`).

7. **Export a canonical non-source predicate** (`dummyindex/context/build/reconcile.py`) — via python-implementer.
   - Add a public predicate (e.g. `is_non_source_path(path) -> bool`) composing the existing `_is_context_path` (`:350`) **OR** `_is_tool_path` (`:363`) — i.e. the existing `_hidden` logic (`:165-172`). Must cover `.context` **and** `.claude`/`.claude-design` (parity with the gate's `_NON_SOURCE_PREFIXES`; dropping `.context` would make index-only edits count as source — R14). Sole owner of this file.

8. **Harden the Stop gate** (`dummyindex/context/reconcile_gate.py` + `dummyindex/context/domains/memory/transcript.py`) — via python-implementer. Single owner of `reconcile_gate.py`; sub-fixes verified independently in task 13.
   - **F6 (behavior change):** `_gate_relevant` (`:284-295`) returns `True` when `report.drifted_features` is non-empty (commit-anchored → always counts; depends on task 6). Merge drifted features into `render_block` (`:79-124`), `_render_section` (`:137-157`), `render_multi_block` (`:160-182`), de-duplicated with `by_feature()`. **Directive wording (R7):** acknowledge "if you already reconciled, just run `reconcile-stamp` and commit" so a reconciled-but-unstamped session isn't told to redo work.
   - **F11:** replace `_NON_SOURCE_PREFIXES` (`:39`) + its prefix-matching (`:265-268`) with the shared predicate from task 7, preserving exact match semantics. Depends on task 7.
   - **F9 (scoped — R10):** in `decide_block` (`:332-333`), emit a conservative advisory block **only** when a `session_id` is present but its transcript is unreadable; keep the hard-allow when there is **no** session id (headless/CI/e2e must not be trapped).
   - **F10 (R11/R12):** add a subagent-**edit** signal to `read_session_signal` in `memory/transcript.py` — verify the `subagents/agent-*.jsonl` envelope against a real sample, parse `Edit`/`Write` tool-uses the same way the main transcript is parsed (`transcript.py:84-121`), and have `_session_drifted_source` (`:241-270`) use edit-count, not file presence. **Leave `is_significant` (`nudge.py:26-30`) and its `subagent_file_count` input untouched** (deliberate — the audit's withdrawn A8 boundary). Build-style runs (subagent edits) must still return `True`.

## Tests (the audit's critical coverage gaps)

9. **Unit tests for the CLAUDE.md helper** (`tests/context/output/test_claude_md.py`, NEW) — via python-tester. `@pytest.mark.unit`.
   - Every branch of `reconcile_claude_md`: root managed-block + residue → root deleted, `.claude/` = residue + one block; root managed-block only (whitespace residue) → root deleted; root user content + no block → consolidated, root deleted; pre-existing `.claude/CLAUDE.md` user content + block → merged, no duplication; **idempotent second run → `action == noop`, byte-identical**; **inode/symlink same-file → noop, file survives**; **unbalanced/duplicate markers → no raise, one block out**; **user prose quoting markers → preserved + idempotent**; OSError on unreadable root → warning, root untouched; **injected canonical-write failure → root intact, warning**.

10. **Integration test: fresh install/build seeded with a root CLAUDE.md** (`tests/context/output/test_claude_md_build.py`, NEW) — via python-tester. `@pytest.mark.integration`.
    - Copy `SAMPLE_REPO` into `tmp_path`, write a root `CLAUDE.md` (parametrize: with / without a managed block), run `build_all` / `dispatch(["init", ...])`, assert root gone + single consolidated `.claude/CLAUDE.md`. Add a case for the **enriched-preserved re-install** branch (task 4).

11. **Install user-scope registration test** (extend `tests/test_install.py`) — via python-tester. `@pytest.mark.integration`.
    - monkeypatch `HOME`; seed `~/.claude/CLAUDE.md` containing "dummyindex" **without** the `_SKILL_REGISTRATION` sentinel → assert the block is appended; second case with the sentinel present → assert no change / no duplicate (verifies task 5).

12. **`refresh-indexes` legacy-layout test** (`tests/cli/test_migrate.py`, NEW) — via python-tester. `@pytest.mark.integration`.
    - Seed a pre-v0.10 layout (legacy `graph/` dir + root `CLAUDE.md`); run the `refresh-indexes` path; assert the `graph/` migration **and** the CLAUDE.md consolidation both ran (verifies tasks 2 + the unchanged `migrate_legacy_layout`).

13. **Gate real-anchor + propagation tests** (`tests/context/test_reconcile_gate.py` + `tests/context/test_drift.py`) — via python-tester.
    - **T-C (BLOCK-grade):** build a **genuinely stamped, anchored** `.context/` (real `reconcile-stamp`, NOT a monkeypatch); assert `_has_live_anchor(root) is True` was reached naturally; a committed owned-file modification → `decide_block` returns a block naming the feature. **Remove the `_has_live_anchor` monkeypatches (`:112,:274`) from this new test** and **rewrite `test_silent_when_only_mtime_drift_and_anchor_present` (`~:255`)** so it no longer locks the buggy silence in. (`integration`)
    - Anchor-less mtime block still works (no regression); trivial/opted-out still allowed. (`integration`)
    - **F9:** session-id-present-but-unreadable-transcript → advisory block; **no-session-id headless → allow**. (`unit`/`integration`)
    - **F10:** read-only subagent fan-out → `_session_drifted_source` False; build-style subagent edit → True; read-only subagents + a main-thread source edit → block. (`unit`)
    - **F11:** assert `reconcile_gate`'s non-source check **is** the shared predicate from `build/reconcile.py` (identity / behavioural parity), replacing `test_gate_non_source_covers_reconcile_tool_paths`. (`unit`)
    - **drift (`test_drift.py`):** `compute_drift` populates `drifted_features` on a stamped anchored repo with a committed owned-file edit; `has_drift` True when only `drifted_features` is set; `compute_badge`/`render_drift_summary` reflect it **de-duplicated**. (`unit`/`integration`)

## Verification

14. **Review the diff** — via /code-review
15. **Run the verify gate** — via /dummyindex-verify
