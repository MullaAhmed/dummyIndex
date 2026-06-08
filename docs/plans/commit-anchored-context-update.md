# Commit-anchored incremental context update

> Status: spec / awaiting build sign-off. Supersedes the destructive
> `rebuild --changed → full build_all` path. Tracked as "fix #5".

## Problem

`dummyindex context rebuild --changed` is not incremental. When any source
file changes, `incremental.py:103` falls through to a full `build_all`, which:

- re-runs deterministic graph **community-detection from scratch** →
  generic `community-N` feature IDs, discarding the council's curated
  taxonomy (the Phase 2 `features-rename`s are never replayed);
- writes a fresh `features/INDEX.json` pointing only at the `community-N`
  stubs, **orphaning** every enriched feature folder on disk;
- re-scaffolds `spec.md` from a deterministic stub (`builder.py:257`, no
  preserve guard) and regenerates `tree.json` abstracts.

It has **no commit awareness** and **no preservation of enrichment**, yet it
is auto-run as the `/dummyindex-build` loop-closer. Net effect observed in a
real repo: a coherent enriched index (14 named features) was replaced by 17
`community-N` deterministic stubs in one `rebuild --changed`. Recoverable only
because `.context/` happened to be git-committed.

## Goal

`.context/` updates are **git-diff-driven, non-destructive, and preserve the
curated taxonomy + enrichment**. The deterministic layer detects the delta and
surfaces it; the **council/LLM decides taxonomy placement** (new feature vs
addition to an existing one) and re-enriches. No layer ever silently
re-clusters over curated features or overwrites an `INFERRED` doc with a stub.

## Design

### 1. `.context/` records its anchor commit
`meta.json` gains `indexed_commit: <sha>` (alongside `updated_at`). It is the
commit the on-disk index was last reconciled against. Written only after a
successful reconcile.

### 2. Deterministic update engine (no judgment)
Input: `git diff <indexed_commit>..HEAD --name-status` **plus** uncommitted
working-tree changes. Classify each path:

- **changed** (file owned by ≥1 feature) → mark those features **drifted**
  (refresh only their deterministic backbone — symbols/tree for the changed
  files; **preserve** `spec.md`/`plan.md`/`concerns.md`; set a stale flag).
- **removed** → drop from the owning feature's file list; flag the feature.
- **net-new** (owned by no feature) → record as **unassigned** in the
  reconcile report. **Never auto-cluster, never invent `community-N`.**

Output: a reconcile report (drifted features + unassigned new files +
removals). The engine **never** re-runs community detection and **never**
overwrites enriched docs. Feature→file ownership comes from each
`feature.json`'s `files` list.

### 3. Council / session reconciliation (the judgment layer)
The running session reads the report and:

- for each **unassigned** file/cluster, the council **decides**: scaffold a
  **new feature** OR **attach** to an existing one — applied via atomic ops
  (a new `assign-files`/`scaffold-feature` op + existing `features-rename`);
- **re-enriches** the drifted + newly-placed features (and only those);
- records the new `indexed_commit = HEAD`.

### 4. Entry points (same engine)
- **session-end `update`** — reconcile the delta since `indexed_commit`.
- **session-start `refresh`** — the SessionStart drift report (`plan-update`)
  becomes commit-diff-based and includes unassigned new files.
- `rebuild --changed`'s full-rebuild fallthrough is **removed**; a true
  from-scratch re-cluster is gated behind an explicit `--full` (or a fresh
  `ingest`), which warns that it discards curated taxonomy.

### 5. Fallback
Non-git repo, or missing/invalid `indexed_commit` → today's hash-manifest path
and a first full build. (git is the backup; no separate snapshot.)

## Phasing

1. ✅ **Deterministic commit-diff layer + stop the clobber** *(highest priority —
   ends the data loss):* add `indexed_commit` to `meta.json`; build the
   `git diff`→classification + reconcile report; make the update non-destructive
   (preserve enriched docs, no re-cluster); gate the destructive full rebuild
   behind `--full`.
2. ✅ **Atomic placement ops** — `assign-files`/`scaffold-feature` so the council
   can place unassigned files without re-clustering.
3. ✅ **Council reconciliation phase** — `reconcile` (read-only report) +
   `reconcile-stamp` (the anchor-advance boundary, refuses past un-reconciled
   work) + `mark-enriched` (clears the `.pending-enrichment` marker the
   placement ops drop) + `council/65-reconcile.md` (read report → recover
   `awaiting_enrichment` → place unassigned → re-enrich drifted/placed → stamp).
   **Correction landed here:** `rebuild --changed` must **not** advance
   `indexed_commit` (Model B — the anchor tracks the last *reconcile*, not the
   last scan); only `ingest` (the floor) and `reconcile-stamp` move it.
4. **Wire entry points** *(pending)* — session-end `update` + commit-aware
   session-start `refresh`; deprecate/guard the old rebuild path; update
   README/lifecycle docs (setup/ongoing-mode narrative) accordingly.

## Non-goals
- Changing enrichment quality or the council's per-feature pipeline.
- The deterministic layer making any taxonomy decision.

## Resolved decisions
- **New-file placement:** council/LLM decides (new feature OR attach to an
  existing feature) — never guessed deterministically, never `community-N`.
- **Backup:** `.context/` is git-tracked; git is the safety net — no snapshot.
- **Anchor semantics (Model B):** one `indexed_commit` field = "last reconciled
  commit". A non-destructive `rebuild --changed` refreshes the backbone but
  leaves it put, so the delta keeps reporting until `reconcile-stamp` advances
  it. The stamp refuses past `unassigned_new_files` / `awaiting_enrichment`
  (the data-loss guard, one layer up); it does **not** block on
  `drifted_features` (only the stamp clears drift).

## Known limitations
- **Removed files are not pruned from feature file lists.** `removed_files` is
  reported and the owning feature is flagged `drifted` → re-enriched (prose
  fixed), but no atomic op drops the dead path from `feature.json`'s `files`
  array (the placement ops only add). It's cosmetic — the file's symbols leave
  `map/symbols.json` on the next backbone refresh, so members self-correct — and
  removals never block the stamp. A `drop-files` op is a follow-up unit, not part
  of phases 1–3.
