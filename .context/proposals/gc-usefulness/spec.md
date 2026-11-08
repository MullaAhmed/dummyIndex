# Spec — Make context-hygiene GC useful: unblock retirement, recommend actions, draft closeouts, batch confirm

## Intent

User verdict: "gc is useless". Code confirms it. Five defects, each verified on this repo:

1. **Every retirement is blocked.** `durable_references` treats the generated `.context/INDEX.md` file inventory as a durable inbound reference. INDEX.md lists every workspace file. 12 of 13 proposals report `durable references remain: .context/INDEX.md`; for 10 it is the only hit (`dummyindex/context/domains/proposals/retirement.py:75`; writer `dummyindex/context/build/runner.py:270`).
2. **Done work never looks done.** 8 of 12 `planned` proposals have a fully ticked checklist. 3 more miss one item each: a test run, an eval, a live-host GATE. Only closeout flips `status` (`proposals/closeout.py:573`). `gc status` shows raw tags and no next action.
3. **Closeout is too costly.** The manifest needs a SHA256 for every workspace file and a disposition per file. No helper drafts it. Nobody closes anything, so nothing becomes deletable.
4. **Dry-run lies.** `gc delete` without `--yes` prints "would delete" and runs no guard. `--yes` then refuses.
5. **The nudge is dead.** The committed anchor `bdbd098` is unknown to the repo. `commits_since` is `None`, so `should_signal` never fires (`gc/anchor.py:117`).

Goal: the smallest change that lets one `/dummyindex-gc` run turn finished proposals into one reviewed, user-confirmed batch of deletions. Reuse the `gc` and `proposals` domains. Add no new CLI verb.

## Contracts

### C1 — Generated inventory is not a durable reference
- `durable_references(context_dir, workspace)` skips exactly `context_dir / "INDEX.md"`. Same idiom as the graph-payload skip.
- `.context/features/INDEX.md` and every other file keep today's rule. A test or feature doc naming the workspace still blocks.
- The fix applies to both `retirement_block` and `closeout._close`; both call `durable_references`.
- Stale INDEX.md lines after a delete are harmless. The next build rewrites INDEX.md.

### C2 — Deterministic recommendation per candidate
- New closed enum `Recommendation` in `gc/enums.py`: `delete`, `close`, `review`, `keep`. It is a pre-council hint. The council verdict stays `Disposition`.
- Hoist `_PROPOSAL_KINDS` from `gc/delete.py` to `gc/constants.py` as `PROPOSAL_KINDS`. `delete.py` and `recommend.py` both map a kind to the receipt kind with `"proposal" if kind in PROPOSAL_KINDS else "audit"`.
- New pure function `recommend(candidate, context_dir) -> tuple[Recommendation, str]` in `gc/recommend.py`. The string is a one-line reason. It reads `candidate` fields plus two file-existence checks: `receipt_path(...)` and its `.pending.json` sibling.
- Rules, first match wins:

| # | Kind | Condition | Recommendation |
|---|---|---|---|
| 1 | proposal | status `in_progress` | `keep` |
| 2 | any | `.pending.json` closeout intent exists | `review` |
| 3 | any | closeout receipt exists | `delete` |
| 4 | proposal | `orphan-empty` signal | `delete` |
| 5 | proposal | `checklist-complete` signal | `close` |
| 6 | audit | `report-written` signal | `close` |
| 7 | archived | always | `review` |
| 8 | proposal, audit | `age_days >= STALE_AGE_DAYS` (30) | `review` |
| 9 | any | otherwise | `keep` |

- `recommend` never runs `retirement_block`. That walk costs ~0.9 s per candidate here. Guard verdicts come from the dry-run (C4).
- `Candidate` gains `recommendation: str | None = None` and `reason: str | None = None`. `scan` fills both. Docstrings in `models.py` and `signals.py` stop saying "no verdict" for the candidate; `classify` stays tag-only.

### C3 — `gc status` says what to do
- Human output: each candidate line ends with `-> <recommendation>: <reason>`.
- Header: `context gc status: N candidate(s): D delete, C close, R review, K keep`.
- When `D + C + R == 0` (including zero candidates), print `context gc status: ran, nothing to retire`.
- `--json`: each candidate gains `recommendation` and `reason`. Top level gains `summary: {delete, close, review, keep}`. Counts equal the per-candidate tally. All existing keys stay.
- Exit code stays 0.

### C4 — Dry-run runs the full guard ladder
- `delete_workspace(..., dry_run=False)` gains a keyword. With `dry_run=True` it calls `_delete_workspace_locked` without `project_lock`, runs guards 1–6, and returns before `shutil.rmtree`. No lock file, no write.
- `DeleteResult` gains `would_delete: bool = False`. Dry-run success sets it. `reason` is not overloaded.
- CLI without `--yes` calls `delete_workspace(dry_run=True)`. Exit codes mirror `--yes`: guard error → `error: ...`, exit 2; untracked refusal → `context gc delete: refused — ...`, exit 0; success → `context gc delete (dry-run): would delete <kind> --slug <slug>` plus `  pass --yes to delete (nothing removed)`, exit 0.
- The dry-run verdict is advisory. `--yes` re-runs every guard.

### C5 — Closeout draft
- `gc closeout --draft --kind proposal|audit --slug S [--root DIR]`. `--manifest` is not needed with `--draft`. No `--out` flag.
- New `draft_manifest(context_dir, kind, slug) -> dict` and `write_draft(context_dir, kind, slug) -> Path` in `proposals/draft.py`, beside `closeout.py`.
- Draft keys:
  - `reviewed_files`: `workspace_inventory(workspace)`.
  - `state`: proposal → `implemented` only when the checklist has `total > 0` and `done == total`. Audit → `implemented` only when `report_written` is true. Else `planned`.
  - `disposition`: `completed` when `state` is `implemented`. Else `abandoned`.
  - `transfers`: `[]`. `pending_verification`: `[]`.
  - `discarded`: `{file: ""}` for every inventory file not in `ADMIN_FILES`.
- Empty discard reasons are deliberate. `closeout_from_file` on an unedited draft fails with `discarded entries require an explicit reason`.
- Path: `.context/cache/gc/closeout-<kind>-<slug>.json`. `cache/` is gitignored by the generated `.context/.gitignore` and sits outside every workspace.
- An existing draft is never overwritten. The CLI prints `error: draft exists: <path>; delete it to redraft` and exits 2. A filled draft is never lost.
- A bad slug or a missing workspace exits 2. Success prints the path, exit 0.

### C6 — Orphaned anchor fires the nudge
- `should_signal`: compute `gc_commits_since` once. When it is `None`, fire only if `anchor_orphaned` is true. Same fire-once memo.
- `anchor_orphaned` returns False in a shallow clone (`git rev-parse --is-shallow-repository` prints `true`).
- `gc signal` prints `GC anchor orphaned (history rewrite) — run /dummyindex-gc, then gc stamp --to HEAD` in that case. It calls `anchor_orphaned`, not a third `gc_commits_since`.
- `scan` reports `should_signal = (commits is not None and commits >= threshold) or anchor_orphaned`.
- No anchor recorded, off-git and shallow clones stay silent.

### C7 — Skill: recommendation-driven batch sweep
`dummyindex/skills/gc/SKILL.md` keeps its ordered steps, the contract line, the `CONFIRM WITH THE USER` heading, every `non-dispatchable` / `human-decision` marker and the dogfood GATE. Changes:
- Step 1: read `recommendation` and `reason`. `keep` candidates get no council walk.
- Step 2: walk only `close`, `review` and `delete` candidates.
- Step 3: per `close` or accepted `review` candidate, the conductor runs `gc closeout --draft`, fills transfers or discard reasons from council evidence, and runs closeout. Then it runs the `gc delete` dry-run and records the verdict. A `delete` recommendation can still fail the dry-run; the table shows the dry-run verdict.
- Step 4: present **one batch table**: slug, recommendation, evidence, closeout result, dry-run verdict. Ask for **one explicit confirmation**. The user may strike rows. Only listed rows are covered. Rows that need `--allow-untracked` or `--force-partial` are **excluded from the batch** and confirmed one by one.
- Step 5: run `gc delete --yes` per confirmed row. One failure does not stop the others. A row refused at `--yes` is reported `blocked at delete`.
- Step 6: `gc stamp` after the report, every run.
- Final output: a chat **sweep report** — counts per recommendation, closed, deleted, blocked with reason, kept. When nothing qualified it states `ran, found nothing to retire`.

### C8 — Evolution seam (interface only)
- GC enumerates only `proposals/` and `audits/`. It never lists or deletes `.context/gc/evolution.jsonl`, `.context/gc/evolve/` or `.context/gc/evidence*`.
- A future evolution cleanup plugs in by returning `Candidate` rows with a new `CandidateKind` plus a `Recommendation`. GC shows them in the same batch table. Deletion stays an evolution-owned CLI verb.

### Invariants
- No deletion without explicit user confirmation. The CLI still needs `--yes`.
- `gc status`, the dry-run and `--draft` never modify a workspace.
- GC never edits source code.
- The knowledge-lifecycle guard keeps its strength except the INDEX.md false positive.
- New code carries no long comments: at most one short line on a non-obvious statement, docstrings at most 3 lines.

## Decisions

Settled under KISS/YAGNI. Not open.

- **D1 Batch confirmation.** One explicit user confirmation covers one reviewed batch table. Unlisted rows are never deleted. Rows needing `--allow-untracked` or `--force-partial` stay per-item. Deletion stays user-confirmed.
- **D2 No batch CLI verb.** The skill loops `gc delete --yes` per confirmed row.
- **D3 Done = checklist complete.** No git commit or branch signal. Squash merges erased slugs: 4 checklist-complete proposals have 0 `git log --grep` hits.
- **D4 Closeout stays the only status writer.** No separate auto-mark-done. A hand-set `done` without a receipt is not trusted; only the receipt counts.
- **D5 Stale age = 30 days.** A constant in `gc/constants.py`. No config key.
- **D6 Narrow INDEX.md skip.** Skip in `durable_references`. Do not change INDEX.md generation.
- **D7 Dry-run mirrors `--yes` without the lock.** Same guards, same exit codes, no `rmtree`, no lock file.
- **D8 Orphaned anchor nudges.** Once per session. Shallow clones stay silent.
- **D9 Drafts live in `.context/cache/gc/` and are never overwritten.** Empty discard reasons block an unreviewed draft.
- **D10 Sweep report is chat output.** A report file would itself become GC debris.
- **D11 Stamp every run.** Blocked rows need human repair; repeated nudges do not fix them. The report lists them.
- **D12 `Recommendation` is separate from `Disposition`.** Hint before the council versus verdict after it.
- **D13 `HOW_TO_USE` template is out of scope.** The skill, playbook and `context --help` carry the new flow.
- **D14 Evolution cleanup is interface-only.** See C8.

## Acceptance

All items are local pytest or local read-only CLI runs. New tests carry `@pytest.mark.unit` or `@pytest.mark.integration`.

- [ ] C1: in `tests/context/domains/test_closeout.py`, a workspace named only in `.context/INDEX.md` gets `[]` from `durable_references`. Named in `.context/features/INDEX.md` or `tests/x.py`, it still gets that path. Named in both INDEX.md and `tests/x.py`, only `tests/x.py` is returned.
- [ ] C2: `tests/context/domains/gc/test_recommend.py` has one parametrized case per table row, plus precedence cases: `in_progress` + receipt → `keep`; `.pending.json` + receipt → `review`; `orphan-empty` + age 90 → `delete`; archived + receipt → receipt maps to `proposal-<slug>.json` and gives `delete`; hand-set `done` without receipt and complete checklist → `close`.
- [ ] C3: a status fixture with one candidate per recommendation prints the exact header `context gc status: 4 candidate(s): 1 delete, 1 close, 1 review, 1 keep`. `--json` `summary` equals `{"delete": 1, "close": 1, "review": 1, "keep": 1}`. The key-set asserts in `test_status_json_emits_expected_shape` include `summary`, `recommendation`, `reason`.
- [ ] C3: an empty `proposals/` fixture and an all-`keep` fixture both print `context gc status: ran, nothing to retire`.
- [ ] C4: dry-run on a receipt-less material proposal exits 2; stderr contains `knowledge review/closeout receipt required`; the workspace exists.
- [ ] C4: dry-run on a closed-out proposal exits 0; stdout contains `context gc delete (dry-run): would delete proposal --slug` and `pass --yes to delete (nothing removed)`; `workspace_inventory` is equal before and after.
- [ ] C4: dry-run on an untracked proposal without `--allow-untracked` exits 0 and prints `refused`; the workspace exists.
- [ ] C4: dry-run returns `would_delete=True` while the test holds `project_lock`; the same call with `dry_run=False` raises `GcTargetError`.
- [ ] C5: `--draft` writes `.context/cache/gc/closeout-proposal-<slug>.json`; `reviewed_files` equals `workspace_inventory`; the workspace inventory is unchanged; every non-admin file maps to `""`.
- [ ] C5: an empty or missing checklist drafts `state: planned`, `disposition: abandoned`. An audit without `report.md` drafts `planned`. A complete checklist drafts `implemented` / `completed`.
- [ ] C5: a second `--draft` exits 2 with `draft exists` and leaves the first file byte-identical. A bad slug and a missing workspace exit 2.
- [ ] C5: `closeout_from_file` on an unedited draft raises `CloseoutError` with `discarded entries require an explicit reason`.
- [ ] End-to-end in `tests/cli/test_gc_cli.py`: `_init_repo`; write a `planned` proposal with a complete checklist; write `.context/INDEX.md` naming it; `_commit_all`; `gc status` shows `-> close`; `gc closeout --draft`; fill every discard reason with `obsolete`; `gc closeout --manifest <draft>`; `_commit_all`; dry-run prints `would delete`; `gc delete --yes` exits 0; the workspace is gone; the receipt remains.
- [ ] C6: in `tests/context/domains/gc/test_anchor.py`, an orphaned anchor makes `should_signal` True once, then False in the same session; a blank `session_id` never suppresses; no anchor stays False; a shallow-clone fixture stays False. `gc status --json` reports `should_signal: true` for the orphaned fixture. `gc signal` prints `GC anchor orphaned (history rewrite) — run /dummyindex-gc, then gc stamp --to HEAD`.
- [ ] C7: `tests/test_skills_doc_hygiene.py` asserts the gc skill contains `one batch table`, `one explicit confirmation`, `excluded from the batch`, `gc closeout --draft`, `blocked at delete` and `ran, found nothing to retire`. The existing ordered-contract, non-dispatchable and no-bare-delete tests pass unchanged.
- [ ] Curated docs carry no proposal path: `git grep -n "proposals/gc-usefulness" -- .context/playbooks .context/features/gc dummyindex/skills dummyindex/cli` returns no hits.
- [ ] Bootstrap dry-run report on this repo: `dummyindex context gc status --json` shows `close` for every `planned` proposal with a complete checklist. For each `close` row, `dummyindex context gc delete --kind proposal --slug <slug>` (no `--yes`) gives a reason that does not name `.context/INDEX.md`. Nothing is deleted. Paste the counts into the build report.
- [ ] Full suite green: `python -m pytest tests/ -q --tb=short`.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `gc`
- `proposals`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
