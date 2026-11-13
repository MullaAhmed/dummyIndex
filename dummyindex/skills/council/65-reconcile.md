# Reconcile — fold a commit delta into the curated index

This is the non-destructive update path. `.context/` records the commit that it was last reconciled against (`meta.indexed_commit`). When source moves on, the deterministic layer reports the delta.

**You** (the council) decide where new code belongs. You also re-enrich what drifted. **Never** re-cluster. **Never** overwrite an `INFERRED` doc with a stub.

> Entry points: invoke `/dummyindex --recouncil` on Claude Code or `$dummyindex --recouncil` on Codex. These are **skill** invocations, not a `dummyindex` CLI verb. Run this procedure when `rebuild --changed`, explicit status, or host guidance shows drift.

> Claude also has an always-on session-end reconcile gate (`dummyindex context reconcile-gate`, a Stop hook). That gate blocks exit when a substantial session leaves `.context/` stale. It directs the session here. Codex installs no dummyindex Stop hook. Either way, the procedure ends by committing the refresh as its own commit (step 5). Every update is then tracked in git.

## The anchor (Model B)

`meta.indexed_commit` is the commit the index was last **reconciled** against. It is not merely re-scanned. Only two things move it: a fresh `ingest`, and `reconcile-stamp` at the end of *this* procedure.

A `rebuild --changed` refreshes the deterministic backbone. It **leaves the anchor put**. The accumulated delta keeps reporting until you reconcile it. That makes the stamp the real transactional boundary.

## Read the delta

```bash
dummyindex context reconcile --json
```

Returns `{indexed_commit, drifted_features, removed_files, unassigned_new_files, awaiting_enrichment, has_drift}`.

- `has_drift == false` means nothing to do. The anchor is already current. Stop.
- No `indexed_commit` (non-git, or a pre-v0.15.3 index) means the commit-anchored path does not apply. Fall back to a normal `--recouncil` over stale features.

The four delta categories and what each means:

| Field | Meaning | Your action |
|---|---|---|
| `awaiting_enrichment` | A prior pass **placed** these (scaffold/assign) but did not finish enriching them. Carries a committed `.pending-enrichment` marker. | **Recover first** (see below). |
| `unassigned_new_files` | Added files owned by no feature. | **Place** them (new feature vs attach — your judgment). |
| `drifted_features` | Own a file that changed or was removed since the anchor. Already enriched, just stale. | **Re-enrich** them. |
| `removed_files` | Deleted since the anchor (the owning feature is also flagged `drifted`). | **Prune** them (see step 2.5): unassign the dead paths, or remove the feature if all its files are gone. |

## The loop

Do these steps in order. Every step is idempotent, so a crash-and-rerun is safe.

### 1. Recover — drain `awaiting_enrichment` *before* taking on new work

These are features that a previous, interrupted reconcile already placed. On a restart, they are invisible everywhere else. A scaffolded feature is no longer `unassigned`, because it now owns its file. It never becomes `drifted`, because added files do not drift.

`awaiting_enrichment` is the **only** signal that they still owe enrichment. It survives the restart, because the marker is committed. Finish them first. A repeatedly interrupted session then still makes monotonic progress.

For each `<id>` in `awaiting_enrichment`:

1. Enrich it. Run the per-feature pipeline for that one id: `/dummyindex --recouncil <id>` on Claude or `$dummyindex --recouncil <id>` on Codex. The pipeline runs specify, then plan, then critique, scoped to `<id>`.
2. Clear the marker: `dummyindex context mark-enriched --feature <id>`.

### 2. Place the `unassigned_new_files` — your judgment, evidenced

For each unassigned file, group files that clearly belong together. Decide once per group. Consult `features/symbol-graph.json`. It is the same evidence that the trivial-feature consolidation uses (`18-filter-trivial.md`, Outcome A/B).

- The new file's symbols are **imported-by / called-from exactly one existing feature** (or one dominates). Then **attach** the file there:

  ```bash
  dummyindex context assign-files --feature <existing-id> --file <path> [--file <path>]...
  ```

- The file is a **distinct capability** with no single owning feature. Then **scaffold a new one**:

  ```bash
  dummyindex context scaffold-feature --id <new-slug> --name "<Human Name>" \
      --summary "<one sentence>" --file <path> [--file <path>]...
  ```

Both ops drop a fresh `.pending-enrichment` marker. The placed feature now shows up in `awaiting_enrichment`. Both are resumable.

`scaffold-feature` errors if the id already exists, because a prior pass created it. Skip it then. `assign-files` silently skips files that are already assigned. Never hand-pick a `community-*` id. Those belong to deterministic clustering, and `scaffold-feature` rejects them.

### 2.5. Prune the `removed_files` — the subtractive half

A deleted source file leaves a dead path in its owning feature's `files` list. The owner is flagged `drifted`. For each owning feature, map which of its files are in `removed_files`:

- **Some** files gone, others live. Drop the dead paths, and keep the feature:

  ```bash
  dummyindex context unassign-files --feature <id> --file <dead-path> [--file ...]
  ```

  The command tolerates paths already gone from disk. That is the point. It drops the marker again, so the feature re-enriches in step 3.

- **All** of a feature's files gone. The feature is dead, so delete it:

  ```bash
  dummyindex context features-remove --feature <id>
  ```

  The command refuses if any owned file still exists on disk. Then the feature is only partially dead, so run `unassign-files` on the gone paths instead. `--force` overrides the refusal.

The step is idempotent and resumable. Re-running after a crash unassigns or removes only what is still present.

### 3. Enrich the placed + drifted features (only these)

Re-read the report (`reconcile --json`), so you act on the current state:

- Every `<id>` now in `awaiting_enrichment` (the ones placed in this pass): enrich it via `/dummyindex --recouncil <id>` on Claude.
  On Codex, enrich it via `$dummyindex --recouncil <id>`. Then run `dummyindex context mark-enriched --feature <id>`.
- Every `<id>` in `drifted_features`: re-enrich it via `/dummyindex --recouncil <id>` on Claude or `$dummyindex --recouncil <id>` on Codex. These features were enriched before. They have **no marker to clear**. Do not run `mark-enriched` on them.

**Always pass the feature id.** A bare `/dummyindex --recouncil` or `$dummyindex --recouncil` re-runs the whole repo. That is the opposite of a scoped reconcile.

When you write `.context/` documents, follow the Writing standard in `00-overview.md` (ASD-STE100). After you write, run `dummyindex context check --style`.

### 4. Stamp — advance the anchor

Before stamping, run `dummyindex context check --style`. Fix the flagged lines in the docs you edited.

```bash
dummyindex context reconcile-stamp
```

This is the only write that moves `meta.indexed_commit`. It **refuses** (exit 1, nothing written) while any `unassigned_new_files` or `awaiting_enrichment` remain. It names them. That means a placement or an enrichment was missed. Go do it, and re-run.

The stamp deliberately does **not** block on `drifted_features`. Re-enriching never clears drift, only the stamp does. Blocking on drift could therefore never advance. If it warns about uncommitted source outside `.context/`, commit that source. Otherwise it re-surfaces as drift on the next reconcile.

`--force` overrides the refusal and prints what it skipped. Use it only in the rare case where an unassigned file is intentionally owned by no feature.

### 5. Commit the index — a dedicated commit per update

The stamp wrote `meta.json`, and the loop rewrote feature docs. Nothing is committed yet. Land the whole refresh as **its own commit**, separate from the code commits that caused the drift. Git history then shows exactly when, and against what, the index was last reconciled:

```bash
git add .context
git commit -m "docs(context): reconcile <feature-ids> (anchor <short-sha>)"
```

The tools enforce this order:

- **Commit code first, reconcile second.** The stamp anchors `indexed_commit` to **HEAD**. If source is still uncommitted, it warns (`dirty_source`), because that source would re-surface as drift next time. So step 4 should run with a clean source tree. Only `.context/` should be dirty.
- **Stamp before this commit.** The stamp makes `meta.json` current. Committing `.context/` afterwards captures the stamped meta in the same commit.
- **This commit never self-drifts.** Drift detection filters `.context/` paths everywhere (`_is_context_path`, `working_tree_dirty`). A commit that touches only `.context/` adds nothing to the next reconcile's delta. The anchor points at the *code* HEAD, not at this docs commit.

Use `docs(context):` (or `chore(context):`). Then release tooling treats the index refresh as docs work, and it does not bump the package version.

**Submodules:** when the gate flags a submodule's index, run the whole procedure scoped to it. Use `reconcile-stamp --root <path>`, and make the commit from *inside* that submodule (`git -C <path> add .context && git -C <path> commit …`). Each repo gets its own dedicated index commit. Bump the superproject's submodule pointer separately, if you track it there.

## Why it's restart-safe

The marker is a committed file, not in-session memory. After any interruption, re-running `reconcile --json` rebuilds the exact remaining work. Placed-but-unenriched features sit in `awaiting_enrichment`. Un-placed files sit in `unassigned_new_files`.

Dead paths sit in `removed_files`. The stamp cannot advance past placement or enrichment work. So the worst a crash costs is a re-run from step 1. It never silently forgets a feature, and it never re-clusters.

## Non-goals

- No re-clustering, ever. The deterministic layer detects. You decide placement.
- No taxonomy decision by Python. New-vs-attach is a council judgment.
