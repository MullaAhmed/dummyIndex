# Plan — Evolution evidence plane: bounded Stop-hook observation, two-stage correction detection, load-time exposure log, keyed local ledger, hostile-transcript filters

Code rule: no long comments. One-line docstrings at most. Limits are named constants.
New package: `dummyindex/context/domains/observe/`. Domain only; no `cli/` change.
Import direction: `evidence` → `observe`. `observe` never imports `evidence` (no cycle).
Time seams: every function that stamps or prunes by date takes `now: datetime | None`; the budget takes `clock`.

## Tasks

1. **Units** — `dummyindex/context/domains/observe/enums.py`, `models.py`, `keys.py`, `security.py`.
   - `enums.py`: `CorrectionStatus` (`open|resolved|expired`), `Verdict` (`attributed|unrelated|unknown`), `ExposureVia` (`read|skill|inject`). `str, Enum` like `lesson/enums.py`.
   - `models.py`: frozen `Correction`, `Exposure`, `Attribution` with `to_dict`/`from_dict`; fields per spec C6, C8, C9.
   - `keys.py`: `evidence_key(home=None)` (exclusive create, `FileExistsError` re-read, POSIX chmod); `keyed_id(*parts, key=None)` with its own canonical-JSON helper (same form as `evidence.digest`, not imported); `evolution_enabled()`; `retention_days(home=None)` plain read of `~/.claude/settings.json`.
   - `security.py`: `scan_text(text)`; two compiled patterns (spec C7).
   - Tests: `tests/context/domains/test_observe_units.py`. `tests/conftest.py` already isolates HOME/USERPROFILE.

2. **Local ledger + importer** — `observe/ledger.py`, `observe/importer.py`, `dummyindex/context/domains/evolve_promotion.py`.
   - `evolve_promotion.py`: add `"observe.lock"` to the `project_lock` allowlist. Nothing else.
   - `ledger.py`: `LEDGER_REL`, `EXPOSURE_REL`; `load`, `save(context_dir, ledger, now=None)` (prunes by `day`), `append_exposures` (drops duplicate `call`), `read_exposures(item=None)`. All writes assume the caller holds `observe.lock`. Reuse `evolve_gate.safe_file`, `atomic_io.write_text_atomic`.
   - `importer.py`: `import_claude(path, root, cursor, ledger, now=None)`.
     - Cursor resume, prefix fingerprint and incomplete-row retry follow `evidence._jsonl`; reimplement the 10 lines here (no import of `evidence`).
     - Human text via `memory.miner.scan._human_prompt_text` plus extended `_INJECTED` prefixes (constant here; `evidence.py` imports it).
     - Turn counter in the cursor; 64 KB tool-result buffer reset at each human turn.
     - Exposure from `Read`/`Skill` `tool_use` blocks; allowed prefixes per spec C6; resolve and, on `os.name == "nt"`, case-fold before `relative_to`; `rules` via `living_rules.rules_in`; `cli` via `config.current_dummyindex_version`.
     - Correction on `_CORRECTION` hit; `id` per spec C8; `quarantine` from `scan_text`; `candidates` from same-session lower-turn exposures, including prior `inject` rows.
     - `DETECTOR_VERSION = 1`.
   - Tests: `tests/context/domains/test_observe_import.py` with constructed JSONL fixtures (spec acceptance rows for this file).

3. **Stage-2 interface + exports** — `observe/attribution.py`, `observe/__init__.py`.
   - `resolution_packet`, `record_attribution`, `open_corrections`, `corrections`, `attributions`, `exposures`, `session_tool_calls`, `commit_evidence_stub`, `record_exposure` (spec C6, C9). Writers take `observe.lock`; `record_exposure` skips on contention.
   - Raw text via `.context/cache/evidence-sources.json` plus `byte_offset`; read-only.
   - `session_tool_calls` reuses `memory.miner.signatures.canonical_signature`.
   - `commit_evidence_stub` writes under `.context/gc/evidence/`; assert `living_rules.durable_evidence` accepts it in the test.
   - `__init__.py` re-exports the spec C9 list plus `keyed_id`, `scan_text`, `DETECTOR_VERSION`.
   - Tests: `tests/context/domains/test_observe_attribution.py`.

4. **Rewire `scan_hosts`** — `dummyindex/context/domains/evidence.py`.
   - Take `observe.lock` first; on contention return `{"skipped": "locked"}`.
   - Claude files go through `observe.importer.import_claude`; Codex JSONL/SQLite keep `_jsonl`/`_database`, writing into the local ledger.
   - Add `budget_s=20.0`, `clock=time.monotonic`, `now=None`, the size+mtime fast path, `complete`, and the `evolution_enabled()` early return.
   - Remove the per-event `gc/evidence/<id>.json` write and the `enqueue_learning` call; keep `"learning": None`.
   - `read_ledger` merged view; committed `_save` writes schema 2; migration order: local write, then committed rewrite (spec C3).
   - `expose_case` logic unchanged apart from the committed shape.
   - Tests: update `tests/context/domains/test_evidence.py`. Add `"userType": "external"` to Claude fixture rows; replace the committed-content assertion at line 86 with local-ledger counts; add migration, clock-budget, fast-path (monkeypatched open counter), lock, kill-switch and digest-grep cases.

5. **Stop hook registration** — `dummyindex/context/hooks.py`.
   - Append the spec C1 entry to `_STOP_HOOK["hooks"]`. `_guard_body` already copies extra keys (`{**h, "command": cmd}`); keep it untouched.
   - Tests: `tests/context/test_hooks.py` per the spec C1 acceptance rows, including the global-scope body.

6. **Doc reconcile** — `.context/features/evolution/concerns.md`.
   - Replace the "Text classification" limit: regex capture only; attribution needs a resolver; Codex corrections are unattributable; exposure misses loads outside `Read`/`Skill`; local evidence expires with host transcripts; human-correction learning waits for the lifecycle layer.
   - No `proposals/` or `audits/` path.

7. **Acceptance run** — `pytest tests/context/domains/test_observe_units.py tests/context/domains/test_observe_import.py tests/context/domains/test_observe_attribution.py tests/context/domains/test_evidence.py tests/context/domains/test_evolve.py tests/context/domains/test_evolve_learning.py tests/cli/test_evolve_cli.py tests/context/test_hooks.py` and `ruff check dummyindex/context/domains/observe dummyindex/context/domains/evidence.py dummyindex/context/domains/evolve_promotion.py dummyindex/context/hooks.py`. Fixtures only; no live host sessions.

## Reused symbols
`evidence_scan_hosts`, `evidence_jsonl`, `evidence_event`, `evidence_read_ledger`, `evidence_save`, `evidence_expose_case`, `living_rules_rules_in`, `living_rules_durable_evidence`, `evolve_promotion_project_lock`, `evolve_gate_safe_file`, `atomic_io_write_text_atomic`, `scan_human_prompt_text`, `signatures_canonical_signature`, `config_current_dummyindex_version`, `hooks_guard_body`.
