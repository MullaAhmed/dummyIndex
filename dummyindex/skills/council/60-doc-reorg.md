# Doc reorg — reorganise the repo's real docs in place (DESTRUCTIVE, opt-in)

Runs **only** on `/dummyindex --reorg-docs`. Never part of the normal pipeline.
This is the one phase that edits the user's actual `README`/`docs/**` — so it is
gated hard and made fully reversible. dummyindex's other phases only ever write
under `.context/`.

## Hard gates (do them in order — do not skip)

1. **Preflight already ran (Phase 0).** Re-read its `git` line. If the tree is
   dirty, the guard below will refuse.
2. **Guard.** Run:
   ```bash
   dummyindex context doc-reorg guard <root>
   ```
   Exit 1 → tell the user to commit or stash first and **stop**. A clean tree is
   what makes `git restore` / `git clean` a complete undo. Only continue dirty if
   the user explicitly insists (then proceed knowing rollback is on them).
3. **Backup.** Snapshot every doc before touching anything:
   ```bash
   dummyindex context doc-reorg backup <root>
   ```
   Record the printed backup dir — you'll hand it to the user for rollback.

## Analyse (read-only — a subagent is fine here)

Read the in-repo docs (`dummyindex context doc-reorg list <root>`) plus the
source-docs catalog at `.context/source-docs/INDEX.json` for staleness signals
(`broken_refs`, `age_bucket`, `confidence`). Learn the repo's **house style**
from the docs themselves — heading depth, voice, code-fence conventions, length.
Produce a written plan first and save it:

- Write the plan to `.context/DOC_RECONCILE.md`: duplicates to merge,
  contradictions to fix (cite the AST when a doc contradicts the code —
  the AST wins), stale sections, gaps, and the target structure/style.
- Surface the plan to the user **before editing.**

## Apply (DESTRUCTIVE — do the edits in THIS session, not a subagent)

**Make every doc edit yourself, in the main session, with the `Edit`/`Write`
tools** — so the user sees and confirms each change through the normal
permission flow. Do **not** delegate the rewriting to a dispatched subagent;
subagent edits bypass that per-file confirmation, which defeats the gate.

- Follow the saved plan. Match the learned house style.
- Moving/splitting/merging files is allowed — but every change is one the user
  watches land.

## After

Tell the user, verbatim, how to undo:

> Backup: `<backup_dir>`.
> Undo content changes: `dummyindex context doc-reorg restore --from <backup_dir>`.
> Full rollback (also removes files the reorg created), tree was clean:
> `git restore -- <doc paths>` then `git clean -fd <doc dirs>`.

`restore` is content-honest: it brings back originals and **reports** (does not
delete) files the reorg created — those are dropped with `git clean`.
