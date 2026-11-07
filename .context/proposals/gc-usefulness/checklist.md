# Checklist — Make context-hygiene GC useful: unblock retirement, recommend actions, draft closeouts, batch confirm

> Waves run in order. Items inside a wave touch disjoint files. Tick `- [x]` only after verifying.
> Every code item: no long comments, docstrings at most 3 lines, tests marked `unit`/`integration`.

## Wave 1 — guard fix + scaffolding
- [x] Skip exactly `.context/INDEX.md` in `durable_references`; C1 tests incl. `features/INDEX.md` and `tests/x.py` controls (dummyindex/context/domains/proposals/retirement.py, tests/context/domains/test_closeout.py)
- [x] Add `Recommendation`, `STALE_AGE_DAYS`, `PROPOSAL_KINDS`, `Candidate.recommendation/reason`, `DeleteResult.would_delete`, all defaulted (dummyindex/context/domains/gc/enums.py, dummyindex/context/domains/gc/constants.py, dummyindex/context/domains/gc/models.py)

## Wave 2 — independent domain pieces
- [x] `recommend` implementing the C2 table, exported from the gc package; per-row + precedence tests (dummyindex/context/domains/gc/recommend.py, dummyindex/context/domains/gc/__init__.py, tests/context/domains/gc/test_recommend.py)
- [x] `delete_workspace(dry_run=...)` skips `project_lock`, runs guards 1–6, returns `would_delete=True` before `rmtree`; uses `PROPOSAL_KINDS` (dummyindex/context/domains/gc/delete.py, tests/context/domains/gc/test_delete.py)
- [x] `draft_manifest` + `write_draft`: inventory hashes, honest state/disposition, empty discard reasons, cache path, refuse overwrite (dummyindex/context/domains/proposals/draft.py, dummyindex/context/domains/proposals/__init__.py, tests/context/domains/test_closeout_draft.py)

## Wave 3 — throttle + scan
- [x] Orphaned anchor fires `should_signal` once per session, shallow clone silent; `scan` fills recommendations and the widened `should_signal` (dummyindex/context/domains/gc/anchor.py, dummyindex/context/domains/gc/scan.py, tests/context/domains/gc/test_anchor.py)

## Wave 4 — CLI
- [x] `gc status` recommendations/header/summary/`ran, nothing to retire`; guarded dry-run; `closeout --draft`; orphaned signal line; usage + help text; split dry-run tests; end-to-end draft → closeout → delete test (dummyindex/cli/gc.py, dummyindex/cli/help.py, tests/cli/test_gc_cli.py)

## Wave 5 — skill + curated docs
- [x] Skill: recommendation-driven walk, `gc closeout --draft`, one batch table + one explicit confirmation, risky rows excluded from the batch, `blocked at delete`, sweep report with `ran, found nothing to retire`; hygiene asserts (dummyindex/skills/gc/SKILL.md, tests/test_skills_doc_hygiene.py)
- [x] Playbook + gc feature spec reflect C1–C8 with source citations, no proposal paths (.context/playbooks/gc-context.md, .context/features/gc/spec.md)

## Wave 6 — acceptance
- [x] C1 acceptance: INDEX.md-only reference returns `[]`; `features/INDEX.md` and `tests/x.py` still block
- [x] C2 acceptance: every table row and precedence case passes in `test_recommend.py`
- [x] C3 acceptance: exact header `4 candidate(s): 1 delete, 1 close, 1 review, 1 keep`, matching `summary`, `ran, nothing to retire` on empty and all-keep fixtures
- [x] C4 acceptance: receipt-less dry-run exits 2 and keeps the workspace; closed-out dry-run prints `would delete`, inventory unchanged; untracked dry-run prints `refused`, exit 0; dry-run works under a held lock
- [x] C5 acceptance: draft path, inventory match, unchanged workspace, honest states, `draft exists` refusal, unedited draft rejected by `closeout_from_file`
- [x] End-to-end acceptance: INDEX.md-listed complete proposal goes `close` → draft → closeout → dry-run `would delete` → `delete --yes` removes it, receipt kept
- [x] C6 acceptance: orphaned anchor fires once, blank session never suppresses, no-anchor and shallow stay silent, `gc signal` prints the orphaned line
- [x] C7 acceptance: skill hygiene phrase asserts pass; existing ordered-contract, non-dispatchable and no-bare-delete tests pass unchanged
- [x] No proposal path in curated docs: `git grep -n "proposals/gc-usefulness" -- .context/playbooks .context/features/gc dummyindex/skills dummyindex/cli` returns nothing
- [x] Bootstrap dry-run report on this repo: `gc status --json` shows `close` for every complete `planned` proposal; no `close` row's `gc delete` dry-run (no `--yes`) names `.context/INDEX.md`; nothing deleted; counts pasted into the build report
- [ ] Full suite green: `python -m pytest tests/ -q --tb=short`
