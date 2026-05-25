# Trivial-feature filter → consolidation decision

A feature flagged "trivial" by the heuristic below does NOT get the full
5-persona council. Instead it gets a **chairman consolidation pass** that
decides where it actually belongs in the docs.

## When the filter fires

A feature is **trivial** if any of:

- `member_count < 3` AND `entry_point_count == 0`. Tiny utility cluster.
- `file_count == 1` AND `entry_point_count == 0`. Single file, no real entry points.
- `name` matches `*-marker`, `typing-*`, `*-aliases`, `*-config`, `*-helpers-*`, `*-utils-*`. Naming-based skip.
- All `members` are type aliases or constants (no callable definitions).

The filter runs after the structural review (so renamed features are
evaluated by their new names).

## The consolidation decision (replaces the old "5-line stub README")

Dispatch a **single Task to the chairman** with this prompt skeleton:

> You are the **Chairman**. Decide what to do with the trivial feature
> `<feature_id>`.
>
> ## Inputs
>
> - `features/<feature_id>/feature.json` — members, files, entry points.
> - `features/<feature_id>/README.md` — the deterministic stub.
> - `features/symbol-graph.json` — call/import edges for the whole repo.
> - `features/INDEX.json` — every non-trivial feature with its files +
>   member count.
>
> ## Your job
>
> Pick exactly one of three outcomes and execute it.
>
> ### Outcome A — merge into an existing feature (most common)
>
> If the trivial feature's symbols are *imported by* or *called from*
> exactly one non-trivial feature (or one dominates the rest), this is
> a supporting utility of that feature. Run:
>
> ```bash
> dummyindex context features-merge \
>     --from <feature_id> --into <target_feature_id> \
>     --as-section supporting
> ```
>
> ### Outcome B — promote to a real feature
>
> If the trivial feature actually represents a distinct capability that
> the heuristic miscounted as small (e.g. a single-file webhook handler
> with one entry point that doesn't show up because the graph lost its
> in-degree), don't merge. Instead:
>
> 1. Update `feature.json` with a real name + summary via:
>    ```bash
>    dummyindex context features-rename \
>        --from <feature_id> --to <new-slug> \
>        --name "<Human name>" --summary "<one sentence>"
>    ```
> 2. Treat as non-trivial — run the standard council
>    (`20-stage1-perspectives.md` → `40-stage3-synthesis.md`).
>
> ### Outcome C — keep as a tiny standalone (rare)
>
> Only for genuinely standalone leaf utilities with no callers AND no
> obvious parent feature. Write a 5-line README via `Write`:
>
> ```markdown
> # <name>
>
> `confidence: INFERRED`
>
> Standalone utility. <one sentence describing what it does>.
>
> **Files:** `<file1>`, `<file2>`
>
> **Why not consolidated:** No call sites from any non-trivial feature.
> ```
>
> ## When done
>
> Log the decision (use the action verb you took):
>
> ```bash
> dummyindex context council-log --feature <id> --stage 0 \
>     --agent chairman --status complete \
>     --note "merged-into:<target>" | "promoted" | "standalone"
> ```

## Why consolidate instead of leaving stubs

The old behavior left every trivial feature as a dangling 5-line README,
which made `features/INDEX.json` noisy and forced agent navigation to wade
through utility-only entries to find real features. Merging a tiny
`url-helpers` into the real `auth` feature as a `supporting` section is
both more accurate (it's a property of auth, not its own feature) and
more useful (someone reading auth's docs now sees its supporting code).

## Override

`/dummyindex --no-trivial-filter` skips the consolidation pass entirely
and runs the full council on every feature. Useful for testing the
heuristic or when "trivial" was misclassified.

## Output (per outcome)

- **A merged:** source folder removed, target gains
  `supporting.md` block, INDEX.json shrinks by one entry.
- **B promoted:** feature renamed + ran through full council, lands in
  INDEX.json with `confidence: INFERRED`.
- **C standalone:** 5-line README written, single log entry.

After the consolidation pass, proceed to flow refinement
(`50-flow-narrative.md`) for the surviving non-trivial features.
