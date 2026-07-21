# Reconcile — fold a commit delta into the curated index

The non-destructive update path. `.context/` records the commit it was last
reconciled against (`meta.indexed_commit`). When source moves on, the
deterministic layer reports the delta and **you** (the council) decide where new
code belongs and re-enrich what drifted — **never** re-clustering, **never**
overwriting an `INFERRED` doc with a stub.

> Entry points: invoke `/dummyindex --recouncil` on Claude Code or
> `$dummyindex --recouncil` on Codex. These are **skill** invocations, not a
> `dummyindex` CLI verb. Run this procedure when `rebuild --changed`, explicit
> status, or host guidance shows drift. Claude also has an always-on session-end
> reconcile gate (`dummyindex context reconcile-gate`, a Stop hook) that blocks
> exit when a substantial session leaves `.context/` stale and directs the
> session here; Codex installs no dummyindex Stop hook. Either way, the procedure
> ends by committing the refresh as its own commit (step 5) so every update is
> tracked in git.

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
| `removed_files` | Deleted since the anchor (the owning feature is also flagged `drifted`). | **Prune** them (see step 2.5): unassign the dead paths, or remove the feature if all its files are gone. |

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
   `/dummyindex --recouncil <id>` on Claude or `$dummyindex --recouncil <id>`
   on Codex (specify → plan → critique, scoped to `<id>`).
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

### 2.5. Prune the `removed_files` — the subtractive half

A deleted source file leaves a dead path in its owning feature's `files` list
(the owner is flagged `drifted`). For each owning feature, map which of its
files are in `removed_files`:

- **Some** files gone, others live → drop the dead paths, keep the feature:

  ```bash
  dummyindex context unassign-files --feature <id> --file <dead-path> [--file ...]
  ```

  (Tolerates paths already gone from disk — that's the point. It re-drops the
  marker, so the feature re-enriches in step 3.)

- **All** of a feature's files gone → the feature is dead; delete it:

  ```bash
  dummyindex context features-remove --feature <id>
  ```

  (Refuses if any owned file still exists on disk — then it's only partially
  dead, so `unassign-files` the gone paths instead. `--force` overrides.)

Idempotent and resumable: re-running after a crash unassigns/removes only
what's still present.

### 3. Enrich the placed + drifted features (only these)

Re-read the report (`reconcile --json`) so you act on the current state:

- Every `<id>` now in `awaiting_enrichment` (the ones you just placed): enrich
  via `/dummyindex --recouncil <id>` on Claude or `$dummyindex --recouncil
  <id>` on Codex, then
  `dummyindex context mark-enriched --feature <id>`.
- Every `<id>` in `drifted_features`: re-enrich via `/dummyindex --recouncil
  <id>` on Claude or `$dummyindex --recouncil <id>` on Codex.
  These were enriched before, so there is **no marker to clear** — don't run
  `mark-enriched` on them.

**Always pass the feature id.** Bare `/dummyindex --recouncil` or
`$dummyindex --recouncil` re-runs the whole
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

### 5. Commit the index — a dedicated commit per update

The stamp wrote `meta.json` and the loop rewrote feature docs, but nothing is
committed yet. Land the whole refresh as **its own commit**, separate from the
code commits that caused the drift, so git history shows exactly when (and
against what) the index was last reconciled:

```bash
git add .context
git commit -m "docs(context): reconcile <feature-ids> (anchor <short-sha>)"
```

Order matters and is already enforced by the tools:

- **Commit code first, reconcile second.** The stamp anchors `indexed_commit`
  to **HEAD**; if source is still uncommitted it warns (`dirty_source`) because
  that source would re-surface as drift next time. So step 4 should run with a
  clean source tree — only `.context/` left dirty.
- **Stamp before this commit.** The stamp is what makes `meta.json` current;
  committing `.context/` afterwards captures the stamped meta in the same commit.
- **This commit never self-drifts.** Drift detection filters `.context/` paths
  everywhere (`_is_context_path`, `working_tree_dirty`), so a commit that only
  touches `.context/` adds nothing to the next reconcile's delta. The anchor
  legitimately points at the *code* HEAD, not at this docs commit.

Use `docs(context):` (or `chore(context):`) so release tooling doesn't read the
index refresh as a feature/fix and bump the package version.

**Submodules:** when the gate flags a submodule's index, run the whole
procedure scoped to it — `reconcile-stamp --root <path>` and the commit from
*inside* that submodule (`git -C <path> add .context && git -C <path> commit …`).
Each repo gets its own dedicated index commit; bump the superproject's submodule
pointer separately if you track it there.

## Why it's restart-safe

The marker is a committed file, not in-session memory. At any interruption,
re-running `reconcile --json` reconstructs the exact remaining work: placed-but-
unenriched features sit in `awaiting_enrichment`, un-placed files in
`unassigned_new_files`, dead paths in `removed_files`. The stamp can't advance
past placement/enrichment work. So the worst a crash costs is a re-run from step
1 — never a silently-forgotten feature, never a re-cluster.

## Non-goals

- No re-clustering, ever. The deterministic layer detects; you decide placement.
- No taxonomy decision by Python. New-vs-attach is a council judgment.
