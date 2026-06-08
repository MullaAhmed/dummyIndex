# Reconcile — fold a commit delta into the curated index

The non-destructive update path. `.context/` records the commit it was last
reconciled against (`meta.indexed_commit`). When source moves on, the
deterministic layer reports the delta and **you** (the council) decide where new
code belongs and re-enrich what drifted — **never** re-clustering, **never**
overwriting an `INFERRED` doc with a stub.

> Entry today: `/dummyindex --recouncil` when a `rebuild --changed` or a
> session-start report shows drift. The automatic session-end `update` /
> session-start `refresh` wiring is a separate phase — this doc is the
> procedure those entry points will call.

## The anchor (Model B)

`meta.indexed_commit` is the commit the index was last **reconciled** against —
not merely re-scanned. Only two things move it: a fresh `ingest`, and
`reconcile-stamp` at the end of *this* procedure. A `rebuild --changed` refreshes
the deterministic backbone but **leaves the anchor put**, so the accumulated
delta keeps reporting until you actually reconcile it. That is what makes the
stamp the real transactional boundary.

## Read the delta

```bash
dummyindex context reconcile --json
```

Returns `{indexed_commit, drifted_features, removed_files, unassigned_new_files,
awaiting_enrichment, has_drift}`.

- `has_drift == false` → nothing to do; the anchor is already current. Stop.
- No `indexed_commit` (non-git, or a pre-v0.15.3 index) → the commit-anchored
  path doesn't apply; fall back to a normal `--recouncil` over stale features.

The four delta categories and what each means:

| Field | Meaning | Your action |
|---|---|---|
| `awaiting_enrichment` | A prior pass **placed** these (scaffold/assign) but didn't finish enriching them. Carries a committed `.pending-enrichment` marker. | **Recover first** (see below). |
| `unassigned_new_files` | Added files owned by no feature. | **Place** them (new feature vs attach — your judgment). |
| `drifted_features` | Own a file that changed or was removed since the anchor. Already enriched, just stale. | **Re-enrich** them. |
| `removed_files` | Deleted since the anchor. | Reported only — see *Known limitation*. |

## The loop

Do these in order. Every step is idempotent, so a crash-and-rerun is safe.

### 1. Recover — drain `awaiting_enrichment` *before* taking on new work

These are features a previous (interrupted) reconcile already placed. On a
restart they are invisible everywhere else — a scaffolded feature is no longer
`unassigned` (it now owns its file) and never becomes `drifted` (added files
don't drift). `awaiting_enrichment` is the **only** signal that they still owe
enrichment, and it survives the restart because the marker is committed. Finish
them first so a repeatedly-interrupted session still makes monotonic progress:

For each `<id>` in `awaiting_enrichment`:

1. Enrich it — run the per-feature pipeline for that one id:
   `/dummyindex --recouncil <id>` (specify → plan → critique, scoped to `<id>`).
2. Clear the marker: `dummyindex context mark-enriched --feature <id>`.

### 2. Place the `unassigned_new_files` — your judgment, evidenced

For each unassigned file (group files that clearly belong together and decide
once per group), consult `features/symbol-graph.json` — the same evidence the
trivial-feature consolidation uses (`18-filter-trivial.md`, Outcome A/B):

- The new file's symbols are **imported-by / called-from exactly one existing
  feature** (or one dominates) → **attach** it there:

  ```bash
  dummyindex context assign-files --feature <existing-id> --file <path> [--file <path>]...
  ```

- It's a **distinct capability** with no single owning feature → **scaffold a
  new one**:

  ```bash
  dummyindex context scaffold-feature --id <new-slug> --name "<Human Name>" \
      --summary "<one sentence>" --file <path> [--file <path>]...
  ```

Both ops drop a fresh `.pending-enrichment` marker, so the placed feature now
shows up in `awaiting_enrichment`. Both are resumable: `scaffold-feature` errors
if the id already exists (a prior pass created it — skip), `assign-files` silently
skips already-assigned files. Never hand-pick a `community-*` id — those belong
to deterministic clustering and `scaffold-feature` rejects them.

### 3. Enrich the placed + drifted features (only these)

Re-read the report (`reconcile --json`) so you act on the current state:

- Every `<id>` now in `awaiting_enrichment` (the ones you just placed): enrich
  via `/dummyindex --recouncil <id>`, then
  `dummyindex context mark-enriched --feature <id>`.
- Every `<id>` in `drifted_features`: re-enrich via `/dummyindex --recouncil <id>`.
  These were enriched before, so there is **no marker to clear** — don't run
  `mark-enriched` on them.

**Always pass the feature id.** Bare `/dummyindex --recouncil` re-runs the whole
repo — the opposite of a scoped reconcile.

### 4. Stamp — advance the anchor

```bash
dummyindex context reconcile-stamp
```

This is the only write that moves `meta.indexed_commit`. It **refuses** (exit 1,
nothing written) while any `unassigned_new_files` or `awaiting_enrichment`
remain, and names them — that means a placement or an enrichment was missed; go
do it and re-run. (It deliberately does **not** block on `drifted_features`:
re-enriching never clears drift, only the stamp does, so blocking on drift could
never advance.) If it warns about uncommitted source outside `.context/`, commit
that source — otherwise it re-surfaces as drift on the next reconcile.

`--force` overrides the refusal and prints what it skipped — only for the rare
case where an unassigned file is intentionally owned by no feature.

## Why it's restart-safe

The marker is a committed file, not in-session memory. At any interruption,
re-running `reconcile --json` reconstructs the exact remaining work: placed-but-
unenriched features sit in `awaiting_enrichment`, un-placed files in
`unassigned_new_files`. The stamp can't advance past either. So the worst a
crash costs is a re-run from step 1 — never a silently-forgotten feature, never a
re-cluster.

## Known limitation — removed files

`removed_files` is **reported**, and the feature that owned a deleted file is
flagged `drifted` and re-enriched (so its prose gets fixed). But pruning the dead
path from that feature's `feature.json` `files` array is **not yet automated** —
there is no file-drop op (the placement ops only add). The stale entry is
cosmetic: the file's symbols already drop out of `map/symbols.json` on the next
backbone refresh, so members self-correct; only the machine `files` array keeps
the dead string. Removals never block the stamp.

## Non-goals

- No re-clustering, ever. The deterministic layer detects; you decide placement.
- No taxonomy decision by Python. New-vs-attach is a council judgment.
