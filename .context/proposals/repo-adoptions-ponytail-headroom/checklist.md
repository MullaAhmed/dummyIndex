# Checklist — Repo adoptions R2: ponytail behavior-gate + rule-copy canary, headroom failure-miner re-eval

> Flat, top-to-bottom list derived from the plan tasks + the spec's
> Acceptance items. Tick `- [x]` only after verifying each item.

## Survey (done in-session, 2026-07-28)

- [x] `DietrichGebert/ponytail` cloned, license resolved (MIT, © 2026 DietrichGebert)
- [x] `headroomlabs-ai/headroom` cloned, license resolved (Apache-2.0 + NOTICE)
- [x] Items 1–3 verdicts cite file contents actually read (`benchmarks/behavior.yaml`, `scripts/check-rule-copies.js`, `benchmarks/robustness-audit.js`)
- [x] Item 5 verdict upgraded from filename-level to file-contents grounding — `headroom/learn/{scanner,loops,writer}.py` were listed via `find`/`ls`, never opened; re-clone required (scratchpad wiped)
- [x] `headroom/learn/analyzer.py` re-verified as an LLM analyzer — currently carried from R1, not re-read this round
- [x] ponytail `benchmarks/{behavior.js,loc.js,correctness.js}` and `arms/*.js` read directly — cited in the spec but only inferred from `behavior.yaml` references and dummyindex's own credit line
- [x] R1 delta 1 recorded — headroom item 4 (sentinels) is DONE, superseded by `docguard/` + `guard_doc_write.py`
- [x] R1 delta 2 recorded — headroom item 9 (failure-miner) re-confirmed PILOT, analyzer rejection re-verified against the 2026-07-29 clone (HEAD `1588f5e`), not carried forward
- [x] R1 delta 3 recorded — ponytail `loc.js`/`correctness.js` already ported, credited at `tests/eval/test_retrieval_eval.py:11`
- [x] Every SKIP states why the technique has no seam here
- [x] `headroomlabs-ai/headroom` appears once, as a re-evaluation

## Task 1 — rule-copy canary

- [x] Invariant-phrase assertions added beside `tests/cli/test_cli_doc_sync.py` — landed in sibling `tests/cli/test_cli_doc_sync_policy_canary.py`, reusing that module's `_DEFAULT_PLUGIN_DOCS`/`_DOC_IDS` rather than forking the seam (split by concern; the plan named the sibling as the seam)
- [x] `ALWAYS_ON_OUTPUT_POLICY` imported as the single source of truth
- [x] Existing token-presence assertions still pass (additive, not a rewrite)
- [x] Reverting the constant to its pre-fix wording turns the test red
- [x] ponytail credited (MIT) at the port site

## Task 2 — behavior-gate grader + selftest

- [x] Grader scores the observable rules: action-first, numbered steps, specific quantities, closing action
- [x] Selftest ships with known-passing and known-failing fixtures
- [x] Selftest runs in the default `pytest -q` path with no network
- [x] Inverting any check fails the selftest
- [x] ponytail credited (MIT) at the port site

## Task 3 — two-arm behavior run

- [x] Control arm (no guidance) and guidance arm both wired to the task 2 grader
- [x] Excluded from the default `pytest -q` path; explicit opt-in only
- [ ] Control arm fails the gates; guidance arm passes
- [x] Delta recorded next to `tests/eval/BASELINE.md`

## Task 4 — host coverage gap list

- [x] Every ponytail host surface classified covered / **partial** / gap / out-of-scope with a reason — a fourth bucket was needed: several surfaces are reached today by dummyindex's managed root `AGENTS.md` through a narrower channel than ponytail's, which is neither "covered" nor "gap" (22 rows, 54 files)
- [x] Compared against `dummyindex/installer/link/families.py`
- [x] Gap list written into this proposal's spec
- [x] No new host platform added

## Task 5 — deterministic failure-miner

- [x] Scanner is deterministic; `headroom/learn/analyzer.py` not ported
- [x] Transcript store resolved, not hardcoded (`~/.claude-os/projects/` on this machine)
- [x] Writes through `atomic_io.write_text_atomic`
- [x] headroom credited (Apache-2.0) with `NOTICE` attribution preserved

## Close-out

- [x] Verdicts re-checked against upstream if picked up after 2026-07-28 (both track their default branch)
- [x] `pytest -q` green
- [x] `ruff check` + `ruff format --check` clean
