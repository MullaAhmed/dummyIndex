# Playbook — retire stale context (hygiene GC)

Use this when generated per-task docs have piled up — abandoned proposal scaffolds, superseded `plan.md`s, finished audits whose findings were long since fixed — and you want to retire them. The disposition is **delete, not archive**: generated docs under `proposals/` and `audits/` are GC'd (deleted) when stale/superseded/dead, never parked in an `_archive/`. The whole sweep is the `/dummyindex-gc` skill (council judgment + your confirmation); this playbook names the order of the `dummyindex context gc` verbs underneath it.

The order is: **`gc status` → review candidates → council judges stale/superseded/dead → user-confirm → `gc delete` → `gc stamp` → reconcile if code changed.**

## 1. Survey the candidates — `gc status`
- Run `dummyindex context gc status` (add `--json` for machine output). It lists every candidate doc under `proposals/` + `audits/` with its signals (`orphan-empty`, `status:<v>`, `checklist-complete`/`checklist-partial`, `report-written`, `untracked`, `age-<n>d`) and the commit-throttle state (`commits_since` / `anchor` / `threshold`).
- This is read-only. Nothing is deleted; you are just reading the report the council will reason over.

## 2. Review + let the council judge
- Run `/dummyindex-gc`. It fans out subagents that walk the candidate docs PageIndex-style (`dummyindex context query`) and judge each **stale / superseded / dead / no-longer-useful** against the current code and the work in flight — the signals from step 1 are inputs, not the verdict.
- A signal is not a sentence: a `done`-but-still-relevant plan stays; only the genuinely dead gets a delete verdict.

## 3. Confirm — nothing is deleted without your say-so
- The skill surfaces the proposed delete-list and **waits for your explicit confirmation**. Deletion is always user-confirmed. If unsure about a candidate, keep it.

## 4. Delete the dead — by disposition
- **Dead docs** → `dummyindex context gc delete --kind proposal|audit --slug <slug> --yes` (one workspace at a time). Without `--yes` it is a dry-run that deletes nothing. A git-untracked workspace also needs `--allow-untracked` (the deletion is then permanent); an `in_progress`/`checklist-partial` proposal needs `--force-partial`.
- **Trivially-dead code** (a 0-caller private symbol that passes every exclusion guard) → route through implementer+tester; remove it only if the full suite stays green. `gc` never edits source itself.
- **Broader / riskier dead code** → open a new proposal (`dummyindex context propose`) and take it through build + review. Never auto-remove it.

## 5. Re-baseline the throttle — `gc stamp`
- After the sweep, run `dummyindex context gc stamp` to advance the committed GC anchor (`.context/gc/state.json`) to HEAD. This resets `commits_since` to 0 so the SessionStart nudge goes quiet until the next batch of commits lands. Off-git, `stamp` is a no-op.

## 6. Reconcile if code changed
- If step 4 removed any code (trivially-dead path), that is a code change like any other: run the reconcile procedure so `.context/` reflects it — `dummyindex context reconcile` (read-only delta) → the `/dummyindex` reconcile procedure (`council/65-reconcile.md`) → `dummyindex context reconcile-stamp`. A docs-only sweep (deletions under `proposals/`/`audits/`) needs no reconcile.

## Common pitfalls
- Treating a signal as a verdict — `done` or `age-200d` alone does not mean "delete". The council decides; you confirm.
- Running `gc delete` without `--yes` and assuming it deleted (it is a dry-run) — or passing `--yes` before the user has confirmed.
- Trying to delete a sentinel (`_archive`, any leading-`_` dir) — the CLI refuses; those are never deletable.
- Hand-deleting source files as "dead code" instead of routing them through implementer+tester or a proposal.
- Forgetting `gc stamp` after the sweep, so the SessionStart nudge keeps firing.
