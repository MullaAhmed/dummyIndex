# Plan — Ponytail-derived improvements: debt ledger, equip invariant canary, audit over-engineering lens, correctness-gated retrieval eval, .context freshness statusline

> Ordered, file-path-naming tasks grouped by execution wave. Each impl task is **TDD (test first)**. Reused symbols cited from the real source. Revised after the critique panel — see the spec's **Decisions** (D1–D5) for the resolved risks this plan now encodes. No `.context/equipment.json` yet, so tasks carry no `— via <plugin>` tags; `equip apply --for-proposal` (step 9) renders the project agents build will dispatch.
>
> **Shared-file serialization points** (kept across waves so two concurrent tasks never collide): `context/enums.py` + `cli/__init__.py` (CLI registration — task 16, after both command bodies); `equip/lifecycle/status.py` is touched only by the single canary task (7). `audit/catalog.py` is touched by tasks 9 (W2) and 13 (W3) — different waves, so serial.

## Wave 1 — foundations (disjoint files, no cross-task deps)

1. **Debt marker vocabulary** — `pipeline/extract/python_rationale.py`. Factor the debt subset into a shared `DEBT_PREFIXES = ("# TODO:", "# FIXME:", "# HACK:", "# DEBT:")`; add `# DEBT:` to `_RATIONALE_PREFIXES`. *Reuses:* `_RATIONALE_PREFIXES`. *Note:* adding a rationale prefix changes rationale-node extraction **repo-wide** — expect a deterministic-backbone diff on the next `rebuild --changed` (not accidental churn).

2. **`EquipmentItem.invariants` field** — `context/domains/equip/models.py`. Add `invariants: tuple[str, ...] = ()` to the frozen `EquipmentItem`; `from_dict` reads it (default `()`), `to_dict` **omits it when empty** (D3 — preserves v3 byte-identity, no `SCHEMA_VERSION` bump). Treat as metadata alongside `grounded_in`. *Reuses:* `EquipmentItem`, `SCHEMA_VERSION`.

3. **Over-engineering persona card** — new `skills/audit/agents/over-engineering.md`. Mirror `maintainability.md` frontmatter (`subagent_type: Code Reviewer`) + sections; body encodes the 5-tag taxonomy, one-line-per-finding format, biggest-cut-first ranking, `net: -N lines, -M deps possible` footer, complexity-only carve-out, and the self-check exemption. *Reuses:* `PersonaCard` schema, the `audit-log` block.

4. **Retrieval eval fixtures + sample-index harness** — new `tests/eval/retrieval_fixtures.json` (+ test scaffolding). Reuse the `SAMPLE_REPO` + `build_all` fixture from `tests/context/domains/test_query.py` to get a stable index (D5); author ≥12 `{question, expected_feature_id, expected_path}` pairs against it, each sharing ≥1 non-stopword token with a file/symbol of its expected feature. *Reuses:* `SAMPLE_REPO`, `build_all`, `tokenize`.

5. **Drift badge string helper (PURE)** — `context/drift.py`. Add `compute_badge(report: DriftReport) -> str` returning `[ctx ✓]` / `[ctx: N drift]` — **no filesystem I/O** (keeps `drift.py` a pure compute/render layer). *Reuses:* `DriftReport.has_drift`, `DriftReport.by_feature`.

## Wave 2 — build on the foundations (disjoint files)

6. **Debt harvester** — new `context/domains/debt/harvest.py` + `models.py` (frozen `DebtRow`/`DebtLedger`). Enumerate Python `.py` files from `detect()`; **relativize each path** via the `drift._rel_or_none` pattern; match a marker only on a true stripped comment line; parse the **raw** `# DEBT:` structured form (`<ceiling>`; `upgrade: <trigger>`); tag rows with no trigger `no-trigger`; degrade malformed markers to `no-trigger`; skip unreadable files; sort path-then-line for determinism. *Reuses:* `detect` (`pipeline/io/detect.py`), `_rel_or_none` (`context/drift.py`), `DEBT_PREFIXES` (task 1). **TDD** (incl. string-continuation false-positive + markdown-heading + unreadable-file fixtures).

7. **Canary classifier + never-clobber guard (D2)** — `context/domains/equip/enums.py`, `equip/lifecycle/status.py`, `cli/equip/dispatch.py`. Add `ItemState.CUSTOMIZED` + `INVARIANT_BROKEN`; in `classify_item`, when `disk != origin_hash` and `item.invariants` is non-empty, return `CUSTOMIZED` if every invariant substring survives in the on-disk text else `INVARIANT_BROKEN` (empty invariants ⇒ `USER_MODIFIED`, unchanged). Add `is_user_owned(state) -> bool` ({`USER_MODIFIED`,`CUSTOMIZED`,`INVARIANT_BROKEN`}) and **replace every `state is ItemState.USER_MODIFIED` guard** — `refresh` + `uninstall` (`status.py`), `apply` (`dispatch.py:~414`) — with it, so the new states are never overwritten or re-baselined. Add `RefreshReport.alarm_invariant_broken`. *Reuses:* `classify_item`, `ItemState`, `content_hash`, `refresh`, `uninstall`, `RefreshReport`, `is_lifecycle_managed`, the `dispatch.py` apply path. **TDD**: empty-invariants ⇒ new states unreachable; `CUSTOMIZED`/`INVARIANT_BROKEN` survive `apply`+`refresh`+`uninstall` byte-for-byte; re-`apply` keeps `INVARIANT_BROKEN` (no laundering).

8. **Badge write at the CLI boundary** — `cli/plan_update.py`. After computing drift, `mkdir(parents=True, exist_ok=True)` `.context/cache/` and write the `compute_badge(...)` string via `atomic_io.write_text_atomic`, in its own try/except that never propagates into the drift report. *Reuses:* `compute_badge` (task 5), `write_text_atomic` (`context/domains/atomic_io.py`), the existing `plan_update.run` flow. **TDD** (missing/unwritable cache dir ⇒ hook still succeeds).

9. **Register persona capability pref** — `context/domains/audit/catalog.py`. Add `"over-engineering": ("review",)` to `_PERSONA_CAPABILITY_PREFS`. *Reuses:* `_PERSONA_CAPABILITY_PREFS`, `resolve_catalog`. **TDD** (resolved / capability-fallback / unresolvable→general-purpose).

10. **Retrieval eval harness + gate** — new `tests/eval/test_retrieval_eval.py` + committed `tests/eval/BASELINE.md`. Build the `SAMPLE_REPO` index, run `query()` per fixture, compute MRR + hit-rate@3 + mean `total_estimated_tokens`, assert against the `BASELINE.md` floors, print the metrics; include the permanent negative-control and the per-fixture token-overlap validation. Establish `BASELINE.md` numbers from a first observed run, set floors a documented margin below. *Reuses:* `query`, `QueryResult.total_estimated_tokens`, `tokenize`. (This task **is** the test.)

## Wave 3 — command bodies + surfacing (depends on Wave 2; disjoint files)

11. **Debt CLI body** — new `cli/debt.py` exporting `run(argv) -> int` (flat module, exactly like `cli/query.py` — not a subpackage). Calls the harvester (task 6); prints the ledger to stdout, `--write` persists `.context/debt.md`, `--json` emits the stable structure (mirror `query.render_markdown`/`render_json`). *Reuses:* harvester (task 6), the `query.py` render pattern. **TDD.**

12. **Statusline CLI body + scripts** — new `cli/statusline.py` (`run`, flat module) + shipped `statusline.sh`/`statusline.ps1`. The scripts **read the `.context/cache/` badge file directly** (no Python on the per-prompt hot path); `cli/statusline.py` is the cold-path fallback and catches every exception → empty stdout, `exit 0` (also for missing `.context/`/cache/malformed). *Reuses:* the badge cache path/format (task 8). **TDD** (malformed/absent ⇒ silent exit 0).

13. **Renderer populates invariants (D4)** — `context/domains/equip/generate/specialists.py` (+`catalog.py` assembly as needed). When assembling a generated specialist's `EquipmentItem`, set `invariants` to a few load-bearing convention substrings the tool must preserve — as **manifest metadata**, mirroring how `grounding_docs`→`grounded_in` is assembled, **never injected into the rendered bytes**. Depends on task 7 (guards must treat the new states as user-owned **before** any item carries invariants — avoids a mid-build clobber window). *Reuses:* `SpecialistTemplate`, the `grounded_in` assembly path, `EquipmentItem.invariants` (task 2). **TDD** (rendered specialist has non-empty invariants; delete-one→`INVARIANT_BROKEN` round-trip).

14. **Statusline nudge (emit-only)** — `context/hooks.py`. At SessionStart, read `statusLine` from **both** the local and global settings (reuse `_settings_path_for` for each), swallowing `MalformedSettingsError`; if neither defines it, emit a one-line nudge carrying the snippet. **Writes nothing to settings.json.** *Reuses:* `claude_settings.load_settings`, `_settings_path_for`, `_SESSION_START_GATE`. **TDD** (local set ⇒ silent; global set ⇒ silent; neither ⇒ nudge; settings bytes unchanged).

## Wave 4 — wire the new subcommands (single atomic edit of the shared files)

15. **Register `debt` + `statusline` subcommands** — `context/enums.py` (add `ContextSubcommand.DEBT` + `STATUSLINE`) **and** `cli/__init__.py` (add the two `from . import` entries + the two `_HANDLERS` mappings, mirroring `ContextSubcommand.QUERY: query.run`). One task editing both shared files atomically, after the command bodies (tasks 11/12) exist. *Reuses:* `ContextSubcommand`, the `_HANDLERS` dispatch table. **TDD** (both subcommands dispatch).

## Wave 5 — reconcile, review, acceptance (depends on all prior)

16. **Reconcile into `.context/`** — run `dummyindex context rebuild --changed` for the backbone, then the **reconcile procedure** (place/enrich the drifted features community-0/3/6/8, then `dummyindex context reconcile-stamp`). Verify `compute_drift` reports no `unassigned_new_files`/`awaiting_enrichment` for the new modules. (main-session)

17. **Review the full diff** — `/code-review` over the complete diff; resolve CRITICAL/HIGH. (main-session, process step)

18. **Acceptance — full suite green** — `pytest` with ≥80% coverage on each new module; all spec `## Acceptance` criteria observed. (main-session)
