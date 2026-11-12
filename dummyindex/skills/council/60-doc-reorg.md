# Doc reorg — reorganise the repo's real docs in place (DESTRUCTIVE)

Runs as **Phase 5.5 of the normal pipeline**, with no opt-in and no flag. `--reorg-docs` still works as an explicit way to run this phase alone. This is the one phase that edits the user's actual `README`/`docs/**`. The other dummyindex phases only write under `.context/`. Being always-on does **not** relax the safety gates below.

Reversibility and per-file confirmation are what make an always-on destructive phase acceptable. Run every gate, in order.

## Hard gates (do them in order — do not skip)

1. **Preflight already ran (Phase 0).** Re-read its `git` line. If the tree is dirty, the guard below will refuse.
2. **Guard.** Run:
   ```bash
   dummyindex context doc-reorg guard <root>
   ```
   Exit 1 means the guard refused the run. Tell the user to commit or stash first, then **skip this phase** and report the skip in Phase 6. Do not fail the run. A clean tree makes `git restore` / `git clean` a complete undo. `backup` refuses a dirty tree on its own, so no way exists to proceed past this gate by accident.
3. **Backup.** Snapshot every doc before touching anything:
   ```bash
   dummyindex context doc-reorg backup <root>
   ```
   Record the printed backup dir. You will hand it to the user for rollback.

## Analyse (read-only — a subagent is fine here)

Read the in-repo docs (`dummyindex context doc-reorg list <root>`). Also read the source-docs catalog at `.context/source-docs/INDEX.json` for staleness signals (`broken_refs`, `age_bucket`, `confidence`). Learn the repo's **house style** from the docs themselves. Look at heading depth, voice, code-fence conventions, and length. Produce a written plan first and save it:

- Write the plan to `.context/DOC_RECONCILE.md`. It lists duplicates to merge, contradictions to fix, stale sections, gaps, and the target structure and style. When a doc contradicts the code, cite the AST. The AST wins.
- Surface the plan to the user **before editing.**

## Apply (DESTRUCTIVE — do the edits in THIS session, not a subagent)

**Make every doc edit yourself, in the main session, with the `Edit`/`Write` tools.** The user then sees and confirms each change through the normal permission flow. Do **not** delegate the rewriting to a dispatched subagent. Subagent edits bypass that per-file confirmation. That defeats the gate.

- Follow the saved plan. Match the learned house style.
- Moving, splitting, or merging files is allowed, but every change is one the user watches land.

## After

Tell the user, verbatim, how to undo:

> Backup: `<backup_dir>`.
> Undo content changes: `dummyindex context doc-reorg restore --from <backup_dir>`.
> Full rollback (also removes files the reorg created), tree was clean:
> `git restore -- <doc paths>` then `git clean -fd <doc dirs>`.

`restore` is content-honest. It brings back originals. It **reports** files the reorg created, but does not delete them. Those files are dropped with `git clean`.
