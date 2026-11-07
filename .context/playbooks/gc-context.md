# Playbook — retire stale context (hygiene GC)

Use this when generated per-task docs have piled up — abandoned proposal scaffolds, superseded `plan.md`s, finished audits whose findings were long since fixed — and you want to retire them. The disposition is **delete, not archive**: generated docs under `proposals/` and `audits/` are GC'd (deleted) when stale/superseded/dead, never parked in an `_archive/`. The whole sweep is the `/dummyindex-gc` skill (council judgment + your confirmation); this playbook names the order of the `dummyindex context gc` verbs underneath it.

The order is: **`gc status` → council walks close/review/delete → `gc closeout --draft` → closeout → dry-run → one batch confirm → `gc delete --yes` → `gc stamp` → sweep report → reconcile if code changed.**

## 1. Survey the candidates — `gc status`
- Run `dummyindex context gc status` (add `--json` for machine output). It lists every candidate doc under `proposals/` + `audits/` with its signals (`orphan-empty`, `status:<v>`, `checklist-complete`/`checklist-partial`, `report-written`, `untracked`, `age-<n>d`) and the commit-throttle state (`commits_since` / `anchor` / `threshold`).
- Each candidate ends in `-> <recommendation>: <reason>`. Recommendation is `delete`, `close`, `review` or `keep`.
- Header counts: `context gc status: N candidate(s): D delete, C close, R review, K keep`. With nothing to retire it prints `context gc status: ran, nothing to retire`.
- `--json` adds `recommendation` and `reason` per candidate and a top-level `summary` with the same counts.
- Rules, first match wins: in_progress → keep; pending closeout intent → review; closeout receipt → delete; orphan-empty → delete; checklist complete → close; audit report written → close; archived → review; age ≥ 30 days → review; otherwise → keep.
- The recommendation is a hint, not a verdict. The council decides. Guard verdicts come later from the dry-run.
- This is read-only. Nothing is deleted; you are just reading the report the council will reason over.

## 2. Council walks the candidates
- Run `/dummyindex-gc`. It skips `keep` rows and fans out subagents for `close`, `review` and `delete` rows. They walk the candidate docs PageIndex-style (`dummyindex context query`) and judge each **stale / superseded / dead / no-longer-useful** against the current code and the work in flight.
- A signal is not a sentence: a `done`-but-still-relevant plan stays; only the genuinely dead gets a delete verdict.

## 3. Close out finished work — draft, fill, closeout, dry-run
- For each `close` row, or each `review` row the user accepts: `dummyindex context gc closeout --draft --kind proposal|audit --slug <slug>`.
- The draft lands at `.context/cache/gc/closeout-<kind>-<slug>.json`. It is never overwritten. If one exists, delete it first to redraft.
- Fill the draft from council evidence: transfers for accepted knowledge, or a discard reason for each discarded file. An empty reason is rejected. Do not skip this review.
- Run `dummyindex context gc closeout --kind <kind> --slug <slug> --manifest <draft>`. Then re-run `gc status` to confirm the `delete` recommendation.
- Dry-run each candidate: `dummyindex context gc delete --kind <kind> --slug <slug>` without `--yes`. It runs the same guards as `--yes`, takes no lock and deletes nothing.
- Dry-run exit 2 means a guard blocked it; read stderr. Exit 0 with `would delete` means the guards pass.
- The dry-run verdict is advisory. `--yes` re-runs every guard.

## 4. Confirm — one batch, one explicit answer
- Present one batch table: slug, recommendation, evidence, closeout result, dry-run verdict.
- Ask for one explicit confirmation. The user may strike rows. Only listed rows are covered.
- Rows that need `--allow-untracked` or `--force-partial` are excluded from the batch. Confirm each of them one by one.
- If unsure about a candidate, keep it.

## 5. Delete the dead — by disposition
- **Dead docs** → `dummyindex context gc delete --kind proposal|audit --slug <slug> --yes`, one confirmed row at a time. One failure does not stop the others. A row refused at `--yes` is reported `blocked at delete` with its reason. A git-untracked workspace also needs `--allow-untracked` (the deletion is then permanent); an `in_progress`/`checklist-partial` proposal needs `--force-partial`.
- **Trivially-dead code** (a 0-caller private symbol that passes every exclusion guard) → route through implementer+tester; remove it only if the full suite stays green. `gc` never edits source itself.
- **Broader / riskier dead code** → open a new proposal (`dummyindex context propose`) and take it through build + review. Never auto-remove it.

## 5b. Loop state lives next door — leave it alone
- The same `gc/` area also holds the self-improvement loop's committed state: `.context/gc/evolution.jsonl` (append-only decision history) and per-run workspaces under `.context/gc/evolve/<run>/`. These are **never GC candidates** — the sweep enumerates only `proposals/` + `audits/` — and the evolve scope guard reciprocally refuses to target the GC anchor or the decision history. Don't hand-prune them either: they are CLI-owned, and `/dummyindex-evolve` (not this playbook) manages their lifecycle.

## 6. Re-baseline the throttle — `gc stamp`
- Run `dummyindex context gc stamp` every run, after the sweep. It advances the committed GC anchor (`.context/gc/state.json`) to HEAD and resets `commits_since` to 0. Blocked rows need human repair; repeated nudges do not fix them. Off-git, `stamp` is a no-op.
- Generated `.context/INDEX.md` is not a durable reference, so it no longer blocks retirement. `features/INDEX.md` and other files still block.
- An orphaned anchor (history rewrite) triggers one nudge per session. Shallow clones stay silent.
- `HOW_TO_USE.md` still describes the old status output until its template is updated.

## 6b. Sweep report — chat output only
- Print the report in chat, not a file. Counts per recommendation, closed, deleted, blocked (with reason), kept.
- When nothing qualified, print `ran, found nothing to retire`.

## 7. Reconcile if code changed
- If step 5 removed any code (trivially-dead path), that is a code change like any other: run the reconcile procedure so `.context/` reflects it — `dummyindex context reconcile` (read-only delta) → the `/dummyindex` reconcile procedure (`council/65-reconcile.md`) → `dummyindex context reconcile-stamp`. A docs-only sweep (deletions under `proposals/`/`audits/`) needs no reconcile.

## Common pitfalls
- Treating a signal or recommendation as a verdict — `done`, `age-200d` or `delete` alone does not mean "delete". The council decides; you confirm.
- Running `gc delete` without `--yes` and assuming it deleted (it is a dry-run) — or passing `--yes` before the user has confirmed.
- Trusting a dry-run as a guarantee. Dry-run runs the guards, but `--yes` re-runs them. Exit 2 means a guard blocked it.
- Hand-writing a closeout manifest. Use `gc closeout --draft`, fill it, then run `--manifest`. Hand-written manifests skip the review.
- Trying to delete a sentinel (`_archive`, any leading-`_` dir) — the CLI refuses; those are never deletable.
- Hand-deleting source files as "dead code" instead of routing them through implementer+tester or a proposal.
- Forgetting `gc stamp` after the sweep, so the SessionStart nudge keeps firing.
