# Audit report — reconciliation & onboarding bugs

**Scope:** the two user-reported issues —
1. a pre-existing `CLAUDE.md` / `.claude/` is left **dangling** instead of being folded into the new dummyindex setup;
2. **no reconcile is triggered/checked after the Stop hook**, so the index can silently drift.

**Panel:** correctness, architecture, tests (`dummyindex-reviewer` ×2 + `python-tester`). **Model:** opus-4.7 (config requested `opus-4.8`, but the audit CLI's `--model` enum predates it — a minor pre-existing drift, see Note A). **Rounds:** Round 0 (independent) + Round 1 (rebuttal). The panel converged in one rebuttal round; the single residual disagreement (A5's decomposition) was adjudicated against the source by the conductor — the code wins.

---

## Executive summary

**Both reported problems are real, but issue 2's literal framing is wrong.**

- **Issue 1 — CONFIRMED (1 high, 1 high-merged, supporting).** A pre-existing root `CLAUDE.md` *is* left dangling. The only code that folds/relocates a root `CLAUDE.md` (`migrate_claude_md_location`) is wired **solely** into `refresh-indexes` — every fresh `install` / `init` / first build calls `bootstrap_claude_md(.claude/CLAUDE.md)` directly and never inspects the root file. Worse, even when reached the migrator **does not** fold a root `CLAUDE.md` that lacks a managed block (a hand-written user file) — it returns early. The whole `migrate.py` module has **zero tests**. This is one defect with several entry points; the fix is a single extracted helper called by both first-build and refresh, with a corrected body.

- **Issue 2 — a Stop reconcile gate DOES exist and fire, so "nothing checks for reconcile" is refuted — BUT the gate has a real silent-drift hole (CONFIRMED high).** On an **anchored** repo (any repo that has run `reconcile-stamp` once — i.e. the normal steady state), a session that **modifies and commits a file owned by an existing feature** produces no block: the mtime signal that would catch it is suppressed once an anchor is live, and the `drifted_features` signal that *does* detect committed modifications is never plumbed into the gate. The user's symptom (drift escapes the Stop hook) is genuine; their stated cause (no gate) is not.

**Headline confirmed findings:** 2 high (one per issue) + their merged duplicates, 1 medium, several low/info, and **3 zero-coverage test gaps** (2 critical) that explain why both bugs reached `main` green. Nothing remained genuinely unresolved after adjudication.

---

## Confirmed findings (ranked)

### Issue 1 — pre-existing CLAUDE.md left dangling

**F1 — HIGH — `confirmed`** — A pre-existing root `CLAUDE.md` is never folded into the managed setup on a fresh `install` / `init` / first build.
*Evidence:* `installer/install.py:271` (`_auto_init_project`) and `context/build/runner.py:263` (`build_all`) both call `bootstrap_claude_md(<root>/.claude/CLAUDE.md)` directly. The only migrator, `migrate_claude_md_location` (`cli/migrate.py:73`), is reachable **only** via `migrate_legacy_layout` (`cli/migrate.py:70`) ← `cli/refresh.py:32` (`refresh-indexes`) — a command a fresh install never runs (call-graph verified: no other caller exists). Result: two competing files — the user's untouched root `CLAUDE.md` (no managed block, no dummyindex pointer) and a new `.claude/CLAUDE.md`. *(raised as correctness C1, architecture A1/A2; unanimous concur.)*
*Fix:* route first-build bootstrap through the relocation helper (see F3).

**F2 — HIGH (merged into the F1 fix) — `confirmed`** — Even when it *is* reached, `migrate_claude_md_location` does not fold a root `CLAUDE.md` that has **no managed block** (a hand-written user file); it returns early and leaves the root file dangling.
*Evidence:* `cli/migrate.py:108-121` — when `legacy_had_managed_block` is `False` it either returns early (`:108-111`) or writes only a fresh managed `.claude/CLAUDE.md` (`:114`) and returns (`:119-121`), never reading/merging the user's root content. The architecture panel ruled this is the *same* defect as F1, not a separate one: the helper's **contract** is wrong, so the extraction must fix the body (fold any root `CLAUDE.md`, managed or not) and add the call-sites together. *(correctness C2, escalated by architecture; unanimous concur.)*

**F3 — MEDIUM — `confirmed`** — The "fold a pre-existing CLAUDE.md" responsibility is architecturally misplaced: it lives in a `cli/` module named for *legacy-layout migration* and documented as "Called by the `refresh-indexes` command" (`cli/migrate.py:3`), so no install/onboard module owns it.
*Evidence:* logic-in-a-wire-only-CLI-module + refresh-only reachability (`cli/migrate.py:73-138`). *Fix:* extract into a `context/output/` domain helper that **returns a structured result** (not `print` to stderr, `cli/migrate.py:53-66,100,116` — finding A4) and is called by both `runner.build_all` (covers init/ingest/install) and `refresh.py`. F1+F2+F3+A4 collapse onto this one extraction. *(architecture A3/A4; concur.)*

**F4 — LOW — `confirmed`** — Global skill registration in `~/.claude/CLAUDE.md` uses a substring probe `"dummyindex" in content` (`installer/install.py:171`), which yields a false "already registered" whenever the user's global file merely mentions the word.
*Fix:* probe for the actual registration sentinel/marker, mirroring the `BEGIN_MARKER` check used elsewhere. *(correctness C3; concur.)*

**F5 — INFO — `confirmed`** — When a legacy managed block *is* stripped, residue is rewritten as `.strip() + "\n"` (`cli/migrate.py:106,125`), collapsing the user's leading/trailing blank-line structure. Content preserved; cosmetic. *(correctness C4.)*

### Issue 2 — reconcile gate after the Stop hook

**F6 — HIGH — `confirmed`** *(absorbs architecture A5 — see Adjudication)* — On an **anchored** repo, a session that modifies and commits a file owned by an existing feature escapes the Stop gate silently.
*Evidence (verified end-to-end):*
- `compute_reconcile_report` correctly detects committed modifications to owned files into `drifted_features` (`context/build/reconcile.py:174-179`).
- But `DriftReport` has **no** `drifted_features` field and `compute_drift` forwards only `rows`, `unassigned_new_files`, `awaiting_enrichment` (`context/drift.py:64-77, 171-175`) — `drifted_features` is dropped.
- `_gate_relevant` blocks on `unassigned_new_files`/`awaiting_enrichment`, or on mtime `rows` **only when `not _has_live_anchor`** (`context/reconcile_gate.py:291-295`). A normal repo that has stamped once has a live anchor (`:229-238`), so the mtime `rows` from the modified file are ignored, and `drifted_features` never reaches the gate at all.
- Call-graph confirms `drifted_features` is consumed only by `cli/rebuild.py`, `cli/reconcile.py`, `cli/status.py` — never by `drift.py` or `reconcile_gate.py`.
*Fix:* plumb `drifted_features` through `DriftReport` → `_gate_relevant` (block when non-empty on an anchored repo), or stop suppressing the mtime `rows` branch when an anchor is live. **One seam.** *(correctness C6, architecture A5-merged, tests T-new; unanimous on the bug.)*

**F7 — INFO/REFUTED FRAMING — `refuted`** — The literal user claim "nothing checks for reconcile after the Stop hook" is false. `_STOP_HOOK` wires `dummyindex context reconcile-gate` (`context/hooks.py:115-128,163`), `cli/reconcile_gate.py:27` calls `decide_block`, and a stale-after-substantial-session block reaches Claude Code via stdout. This is tested (`tests/context/test_hooks.py`, `tests/cli/test_reconcile_gate_e2e.py`). The real defect is F6's incompleteness, not absence. *(correctness C5, tests T9; concur.)*

**F8 — LOW — `confirmed`** (downgraded from medium) — With an **empty** `session_id`, the per-session block-once memo never persists (`reconcile_gate.py:202-209,212-226`), so block-once degrades to relying solely on `stop_hook_active`.
*Note:* the stronger Round-0 claim — that a single `stop_hook_active=true` could cause a *never-block* — was **conceded**: Claude Code sets `stop_hook_active` only on the re-entrant Stop following a prior block, never the first Stop, so `reconcile_gate.py:315` is a correct re-entry guard (validated by `test_reconcile_gate_e2e.py:103-110`). Only the empty-id degradation survives. *(correctness C7.)*

**F9 — MEDIUM — `confirmed`** — The gate hard-allows the stop whenever the main transcript is missing/unreadable (`reconcile_gate.py:332-333`), even when an index is genuinely stale. A real edited-source session whose transcript path the hook couldn't resolve escapes silently.
*Fix:* on an unresolvable transcript with a gate-relevant index, emit a conservative advisory rather than a hard allow. *(correctness C9; concur.)*

**F10 — LOW — `confirmed`** — `_session_drifted_source` counts **any** subagent file (`subagent_file_count > 0`, `reconcile_gate.py:257-258`) as source drift, so a read-only research fan-out (Explore/Plan) can trip a spurious block (over-block, annoyance — not silent drift). *Fix:* gate on whether subagent transcripts contain edit tool-uses. *(correctness C10; architecture disputed *ownership* — it belongs to the `memory.transcript` signal, not gate architecture — but the behaviour stands.)*

**F11 — MEDIUM — `confirmed` (DRY/seam smell)** — `_NON_SOURCE_PREFIXES` (`reconcile_gate.py:39`) duplicates `reconcile.py`'s tool-path set, kept in sync only by a test (`test_gate_non_source_covers_reconcile_tool_paths`) rather than a shared constant. *Fix:* export one canonical non-source predicate from `build/reconcile.py`. *(architecture A7; concur.)*

### Test-coverage gaps (these are *why* both bugs shipped green)

**T-A — CRITICAL — `confirmed`** — `migrate_claude_md_location` / `migrate_legacy_layout` have **zero** tests; no test module imports `dummyindex.cli.migrate` (`cli/migrate.py:13-139`). *(tests T1/T6.)*

**T-B — CRITICAL — `confirmed`** — The dangling scenario itself — fresh install/build on a repo that already has a root `CLAUDE.md` (with and without a managed block) — is covered by no test; `tests/test_install.py:377-392` only asserts `.claude/CLAUDE.md` exists and never seeds a root file (`installer/install.py:271`, `runner.py:263`). A red-before-green test here reproduces F1/F2. *(tests T2/T7.)*

**T-C — HIGH — `confirmed`** — No test asserts the gate **blocks** on a committed modification to an owned file on an **anchored** repo, and the gate cannot even produce that block today. `_has_live_anchor` is monkeypatched in *every* gate test (`tests/context/test_reconcile_gate.py:112,274`), so the real anchored→`drifted_features` path never runs; `test_silent_when_only_mtime_drift_and_anchor_present` (`:255-265`) actually locks F6's buggy behaviour in as "correct." This absence is structural corroboration of F6. *(tests T-new/T13/T10.)*

Lower-value confirmed test gaps (add alongside the fixes): user-content-preserved & empty-residue-unlink paths (`migrate.py:124-136`), `migrate.py` OSError read path, empty-`session_id` block-once fallback, `_load_gate_state` malformed/pruning. *(tests T3/T4/T5/T12/T14.)*

---

## Adjudication of the one dispute (A5 vs C6)

Round 1 left one disagreement: correctness + tests held that architecture's **A5** ("a freshly-installed index is structurally blind until a first anchor is stamped") is the *same* root cause as **C6**; architecture held they are **two distinct seams**.

**Ruling: A5's distinct-bug claim is `refuted` by the code; it is the same mechanism as F6/C6.** Reading `context/drift.py:152-175`: the mtime `rows` signal fires for a modified owned file (mtime bump + sha-change vs manifest) and, on an **anchor-less** repo, `_gate_relevant` honors `rows` (`reconcile_gate.py:293`, `not _has_live_anchor` is `True`) → the gate **blocks**. So the anchor-less/fresh state is the *working* state for modified files, not a blind one. The blindness begins precisely when an anchor goes live (mtime suppressed, `drifted_features` never plumbed) — which **is** F6. Moreover A5's proposed remedy ("stamp a first anchor at build") would *convert* the working mtime-covered state into the broken F6 state — actively harmful. One seam.

*Residual narrow corner (not a high):* a **net-new** file added in the very first session *before any* `reconcile-stamp` is caught by neither `rows` (unmapped file → no row) nor `unassigned_new_files` (needs a git diff against an anchor that doesn't exist yet). This is a low/medium edge, distinct from F6, and is the only defensible kernel of A5 — track it separately, do not block the F6 fix on it.

---

## Withdrawn / refuted (considered, dropped)

- **A8** (gate coupled to `memory` significance internals) — `withdrawn`: deliberate, documented reuse, not a layering violation.
- **T15** (`_root_label` fallback untested) — `withdrawn`: covered transitively.
- **C8** (multi-index memo only under session root) — `withdrawn`/info: the single root-scoped, per-session-id memo is the intended one-block-per-session contract.
- **C7 "never-block"** and **A5 "fresh-index blind"** — `refuted` as stated (see F8 and Adjudication); their surviving kernels are captured in F8 and the narrow corner above.

---

## Recommended remediation order (read-only audit — fixes are a separate cycle)

1. **One extraction for Issue 1 (F1+F2+F3+F4+A4):** move CLAUDE.md relocation into a `context/output/` helper with a corrected contract ("fold any root `CLAUDE.md`, managed-block or not; strip the root; return a structured result"), call it from `runner.build_all` and `refresh.py`, and add tests T-A/T-B (seed a root `CLAUDE.md` before install, assert single source of truth).
2. **One seam for Issue 2 (F6):** plumb `drifted_features` into `DriftReport` → `_gate_relevant` (block on committed modifications to owned files for anchored repos), and add test T-C with a real anchored `.context/` (stop monkeypatching `_has_live_anchor`).
3. **Then** the medium/low gate hardening: F9 (transcript-missing conservative path), F11 (shared non-source predicate), F8/F10 (block-once + subagent-edit refinement), and the narrow new-files-before-first-anchor corner.

---

## Note A — audit-CLI model-enum drift (incidental)

`.context/config.json` sets `model: opus-4.8`, but `dummyindex context audit start --model` accepts only `opus-4.7|sonnet-4.6|haiku-4.5` and does **not** read the config value, so it rejected the config model and forced an explicit `--model opus-4.7`. The `onboard` command's `ModelChoice` enum *does* include `opus-4.8`. Minor, out of audit scope, but worth a one-line fix to keep the model enums consistent across `onboard` and `audit`.
