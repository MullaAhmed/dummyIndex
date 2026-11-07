# Plan — Evolution probation lifecycle: eight reversible states, local overlay, asymmetric promote/demote rules, followed-check, enforcement route, expiry/suspension/caps, yield report, blast-radius tiers

Prerequisite: `evolution-evidence-plane` landed (package `dummyindex/context/domains/observe/`).
Code rule: no long comments. One-line docstrings at most. Thresholds are named constants marked `# uncalibrated default`.
New package: `dummyindex/context/domains/probation/`. CLI stays wire-only (`conventions/folder-organization.md`).
Import rule: `probation.sync` may import `evolve_learning` at module level; `evolve_learning` imports `probation.actions` only inside a function.
Time seam: every time-reading function takes `now`; gate-running functions take `runner` and pass it to `run_gate`.

## Tasks

1. **Units** — `dummyindex/context/domains/probation/enums.py`, `constants.py`, `models.py`, `store.py`.
   - `enums.py`: `State` (8 values), `Route` (`count|convention|reconcile|explicit`), `Followed` (`yes|no|unknown`). `str, Enum` like `lesson/enums.py`.
   - `constants.py`: `HARM_MIN=2`, `IGNORED_ROUTE=2`, `PROMOTE_MIN_SESSIONS=10`, `PROMOTE_MIN_DAYS=3`, `MAX_LIVE_PER_TARGET=1`, `MAX_LIVE_TOTAL=10`, `INDEX_MAX_CHARS=1600`, `ITEM_LINE_MAX=200`, `PROBE_MAX_CHARS=200`, `DIGEST_MEMORY=50`.
   - `models.py`: frozen `Item` with `to_dict`/`from_dict` and `with_state(to, reason, now)` appending history.
   - `store.py`: `PROBATION_REL = ".context/cache/evolution/probation"`; `load_items`, `save_item`, `load_state`, `save_state`. Validate `id` with the `living_rules` rule-ID pattern before building a path. Reuse `evolve_gate.safe_file`, `atomic_io.write_text_atomic`; writes under `project_lock(lock_name="observe.lock")`.
   - Tests: `tests/context/domains/test_probation.py` (round-trip, append-only history, bad ID rejected, unknown schema rejected).

2. **Pure rules** — `dummyindex/context/domains/probation/rules.py`.
   - `route(item, items)`, `followed(probe, calls, start_turn, end_turn)`, `harm_reached(item)`, `eligible(item, exposures, calls_by_session)`, `upper_bound(n)`, `content_reasons(body)` (`observe.scan_text` plus URL, fence and `$ ` patterns), `compile_probe(raw)`.
   - No I/O.
   - Tests: extend `tests/context/domains/test_probation.py` (spec acceptance rows for rules).

3. **Sync + session block + report** — `dummyindex/context/domains/probation/sync.py`, `render.py`.
   - `sync.py`: spec L3 through the `observe` API only; `enqueue_learning` with `event_id="chat:" + correction` and a fixed cue template; `commit_evidence_stub`; drift via `living_rules.sha256`; expiry via `observe.retention_days`; `probes` flag.
   - `render.py`: `session_block` (spec L6), `report` and `format_report` (spec L8). `record_exposure` only for shown items; store `last_block_bytes`.
   - Tests: extend `tests/context/domains/test_probation.py` using an `observe` fixture built through its public API with an injected `now`.

4. **Actions + learning seam** — `dummyindex/context/domains/probation/actions.py`, `probation/__init__.py`, `dummyindex/context/domains/evolve_learning.py`.
   - `actions.py`: `enter(...)` (caps, content check, probe compile, item file); `promote(context_dir, ids=None, *, now=None, runner=None)`; `demote(context_dir, item_id, *, now=None, runner=None)`. Reuse `living_rules.plan_rule`, `living_rules.rules_in`, `evolve.validate_candidate`, `evolve_gate.run_gate`, `evolve_gate.check_receipt`, `evolve_promotion.promote_files`, `evolve.record_event` (existing `gate`/`promote`/`rollback` kinds).
   - `__init__.py`: export `sync`, `session_block`, `report`, `format_report`, `enter`, `promote`, `demote`, `State`.
   - `evolve_learning.py`: add `_run_dir(context_dir, event)` (cache base for `chat:` events, `gc/evolve` otherwise) and use it in `prepare_learning` and `finish_learning`. For `chat:` events: content check and `applies_when`/`probe` validation in prepare; in finish, skip committed `record_event`, call `probation.actions.enter` on pass, set `verdict: blocked` with the refusal reason otherwise. Other events unchanged.
   - Tests: new `tests/context/domains/test_probation_actions.py` (fake `runner`); update `tests/context/domains/test_evolve_learning.py` (tiny fixture test file, existing pattern).

5. **CLI wiring** — `dummyindex/cli/evolve_probation.py`, `dummyindex/cli/evolve.py`, `dummyindex/cli/help.py`.
   - `evolve_probation.py`: `run_attribute(args)`, `run_probation(args)`; flag parsing like `cli/evolve.py` `_parse_flags`; lazy domain imports.
   - `cli/evolve.py`: two handler rows and the unknown-verb list string. Nothing else.
   - `cli/help.py`: two lines in the `evolve` block.
   - Tests: new `tests/cli/test_evolve_probation_cli.py`.

6. **Session-start print** — `dummyindex/cli/memory.py`.
   - In the `SESSION_START` branch, after the memory block: `read_hook_stdin()` for `session_id`, then print `probation.session_block(...)` when non-empty, inside `try/except Exception`.
   - Tests: `tests/context/domains/memory/test_memory_cli.py`.

7. **Skill text** — `dummyindex/skills/evolve/probation-protocol.md` (new), `dummyindex/skills/evolve/SKILL.md`.
   - Protocol: spec L10 rubric and order, the bound wording, reconcile/explicit routes. No `proposals/` or `audits/` path.
   - `SKILL.md`: one pointer line in "Automatic closeout learning" and two CLI reference lines; merge the `evolve evidence`/`evolve rules` sentences to pay for them. Run `tests/cli/test_check_budget.py` first, then after the edit.

8. **Doc reconcile** — `.context/features/evolution/spec.md`, `.context/features/evolution/plan.md`.
   - Spec: chat-derived learning enters local probation; states, asymmetric rules, tiers and yield report in ≤8 lines. Plan: `probation/` bullet and the `evolve_learning` branch.
   - No `proposals/` or `audits/` path; `tests/cli/test_check_budget.py` passes.

9. **Acceptance run** — `pytest tests/context/domains/test_probation.py tests/context/domains/test_probation_actions.py tests/context/domains/test_evolve_learning.py tests/context/domains/test_evolve.py tests/context/domains/memory/test_memory_cli.py tests/cli/test_evolve_probation_cli.py tests/cli/test_evolve_cli.py tests/cli/test_check_budget.py tests/cli/test_cli_doc_sync.py tests/cli/test_subcommand_help.py` (the last two as regression; no evolve-verb guard exists) and `ruff check dummyindex/context/domains/probation dummyindex/context/domains/evolve_learning.py dummyindex/cli`. Fixtures only; no live host sessions.

## Reused symbols
`evolve_learning_enqueue_learning`, `evolve_learning_prepare_learning`, `evolve_learning_finish_learning`, `living_rules_plan_rule`, `living_rules_rules_in`, `living_rules_sha256`, `evolve_validate_candidate`, `evolve_record_event`, `evolve_gate_run_gate`, `evolve_gate_check_receipt`, `evolve_gate_safe_file`, `evolve_promotion_promote_files`, `evolve_promotion_project_lock`, `atomic_io_write_text_atomic`, `memory_read_hook_stdin`, `lesson_validate_lesson`, plus the `observe` API in the spec.
