# Trivial-feature filter → consolidation decision

A feature flagged "trivial" by the heuristic below does NOT get the full
specify → plan → critique pipeline. Instead it gets an **architect
consolidation pass** that decides where it actually belongs in the docs.

## When the filter fires

A feature is **trivial** if any of:

- `member_count < 3` AND `entry_point_count == 0`. Tiny utility cluster.
- `file_count == 1` AND `entry_point_count == 0`. Single file, no real entry points.
- `name` matches `*-marker`, `typing-*`, `*-aliases`, `*-config`, `*-helpers-*`,
  `*-utils-*`. Naming-based skip.
- All `members` are type aliases or constants (no callable definitions).

The filter runs after the structural review (so renamed features are evaluated
by their new names).

> **Where the count fields live.** `member_count`, `file_count`,
> `entry_point_count`, and `flow_count` are carried in the feature's entry in
> **`features/INDEX.json`** (under the top-level `features` array, keyed
> `feature_id`) — **not** in `features/<id>/feature.json`. `feature.json` carries
> only the raw lists `members` / `files` / `entry_points` / `flow_ids`; if you
> read it directly, compute the counts with `len()` (e.g.
> `len(feature["members"]) < 3`). Reading a `*_count` key off `feature.json`
> returns `None` and the comparison crashes.

## One architect pass per feature — no batching

**Dispatch one Task to the architect per trivial feature.** Do not bulk-process.
Do not assume "obvious noise" can be routed deterministically without an
architect pass — that's the failure mode that produced 21 parser-artifact
features bulk-merged into unrelated parents under an invented `noise-absorbed`
section.

If the trivial-feature list is long, parallelize the architect dispatches — but
each feature still gets its own Task, its own decision, and its own audit-log
entry. The right way to handle volume is concurrency, not a shortcut that skips
the per-feature judgment call.

> Upstream filter (since v0.13.2): empty-`__init__.py` parser artifacts are
> dropped at scaffold time by `_is_parser_artifact` in
> `dummyindex/context/domains/features/builder.py`. They should never reach this
> stage. If one does, that's a builder bug — file it, then apply Outcome C with a
> note explaining the leak.

## The consolidation decision

Dispatch a **single Task to the architect** (subagent_type `Backend Architect`)
with this prompt skeleton:

> You are the **Architect**. Decide what to do with the trivial feature
> `<feature_id>`.
>
> ## Inputs
>
> - `features/<feature_id>/feature.json` — members, files, entry points.
> - `features/<feature_id>/spec.md` — the deterministic one-paragraph stub.
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
> If the trivial feature's symbols are *imported by* or *called from* exactly
> one non-trivial feature (or one dominates the rest), this is a supporting
> utility of that feature. Run:
>
> ```bash
> dummyindex context features-merge \
>     --from <feature_id> --into <target_feature_id> \
>     --as-section supporting \
>     --note "merged-from:<feature_id> rationale=<one sentence>"
> ```
>
> Constraints:
>
> - `--as-section` must be a value in `_VALID_MERGE_SECTIONS`
>   (`dummyindex/context/domains/features/constants.py`). At the time of writing
>   the only allowed value is `supporting`. Inventing names like `noise-absorbed`
>   is now rejected at the API boundary.
> - `features-merge` automatically appends a stage-0 architect entry to the
>   **target's** council log. Do not also run `council-log` for the merge — the
>   operation logs itself.
> - The `--note` you pass is what lands in the log entry. Use it to record the
>   actual call-graph evidence that justified the merge
>   (e.g. `"sanitize_response_text imported only by app/job_agent/orchestrator/loop.py"`).
>   `--note` is optional; if omitted, a default `merged-from:<id>` is generated.
>   Always pass an explicit `--note` for non-obvious merges.
>
> ### Outcome B — promote to a real feature
>
> If the trivial feature actually represents a distinct capability that the
> heuristic miscounted as small (e.g. a single-file webhook handler with one
> entry point that doesn't show up because the graph lost its in-degree), don't
> merge. Instead:
>
> 1. Update `feature.json` with a real name + summary via:
>    ```bash
>    dummyindex context features-rename \
>        --from <feature_id> --to <new-slug> \
>        --name "<Human name>" --summary "<one sentence>"
>    ```
> 2. Treat as non-trivial — run the standard pipeline
>    (`20-specify.md` → `30-plan.md` → `40-critique.md`).
> 3. Log the promotion explicitly (Outcome B does not auto-log):
>    ```bash
>    dummyindex context council-log --feature <new-slug> --stage 0 \
>        --agent architect --status complete \
>        --note "promoted; rationale=<one sentence>"
>    ```
>
> ### Outcome C — keep as a tiny standalone (rare)
>
> Only for genuinely standalone leaf utilities with **no callers in the call
> graph AND no obvious parent feature**. Before picking C, you must verify both.
> Quote the check in the council-log note so future audits can confirm the call
> wasn't a reflex.
>
> 1. Write a one-paragraph `spec.md` via `Write`:
>
>    ```markdown
>    # <name>
>
>    `confidence: INFERRED`
>
>    Standalone utility. <one sentence describing what it does>.
>
>    **Files:** `<file1>`, `<file2>`
>
>    **Why not consolidated:** No call sites from any non-trivial feature
>    (checked: <feature ids you looked at>).
>    ```
>
> 2. Log the standalone explicitly (Outcome C does not auto-log):
>
>    ```bash
>    dummyindex context council-log --feature <feature_id> --stage 0 \
>        --agent architect --status complete \
>        --note "standalone; checked-parents=<comma-separated feature ids>; no dominant caller"
>    ```
>
> **Do not pick C** when:
>
> - The trivial feature is a parser artifact (empty `__init__.py`,
>   `confidence: NOISE`, rationale-fragment node). The right answer for parser
>   artifacts is to file a builder bug (it should have been filtered upstream by
>   `_is_parser_artifact`) and apply C with a note that records the leak.
> - The trivial feature is imported by exactly one non-trivial feature. That's
>   Outcome A, not C, even if the utility "feels standalone."

## Trivial features get a one-paragraph spec.md

A trivial feature that isn't merged or promoted gets a one-paragraph `spec.md`
from a template (Outcome C above). It gets **no `plan.md` and no `concerns.md`** —
the full pipeline is reserved for non-trivial features.

## Why consolidate instead of leaving stubs

The old behavior left every trivial feature as a dangling stub, which made
`features/INDEX.json` noisy and forced agent navigation to wade through
utility-only entries to find real features. Merging a tiny `url-helpers` into the
real `auth` feature as a `supporting` section is both more accurate (it's a
property of auth, not its own feature) and more useful (someone reading auth's
docs now sees its supporting code).

## Override

`/dummyindex --no-trivial-filter` skips the consolidation pass entirely and runs
the full pipeline on every feature. Useful for testing the heuristic or when
"trivial" was misclassified.

## Where the architect log entry lands

A subtle but important convention so the audit trail is greppable:

- **Outcome A** auto-logs on the **target** (`--into <id>`). The source feature
  folder is deleted by the merge, so logging on the source would orphan the
  entry. The architect entry on the target reads `merged-from:<source>` and
  carries the explicit `--note` you passed.
- **Outcomes B and C** log on the **source** feature (it survives — B is a
  rename, C is a kept-standalone). The `council-log` example commands in those
  sections target the surviving feature id.

If you ever need to audit "what trivial features got consolidated into X?", grep
`X/council/_council-log.json` for stage-0 architect entries. If you need to audit
"what was the architect's reasoning for Y still existing?", read
`Y/council/_council-log.json`.

## Output (per outcome)

- **A merged:** source folder removed, target gains a `supporting.md` block,
  INDEX.json shrinks by one entry, target's `council/_council-log.json` gains a
  stage-0 architect entry automatically (since v0.13.2).
- **B promoted:** feature renamed + ran through the full pipeline, lands in
  INDEX.json with `confidence: INFERRED`. Architect entry written explicitly via
  `council-log`.
- **C standalone:** one-paragraph `spec.md` written, single explicit log entry
  recording the parent-check results.

After the consolidation pass, proceed to flow refinement (`50-flow-narrative.md`)
for the surviving non-trivial features.

## Verifying a consolidation pass

After all architect tasks complete, sanity-check the run:

- `cat .context/features/INDEX.json | jq '.features | length'` — shrunk by
  exactly the number of trivial features handled?
- `find .context/features -name supporting.md` — every file in the list
  corresponds to a real Outcome A merge?
- `find .context/features -name '*.md' -path '*/features/*' -maxdepth 3` — any
  section files outside the allowlist (e.g. `noise-absorbed.md`, `extras.md`)?
  If yes, something bypassed the API; revert.
- For every Outcome A target, the target's `council/_council-log.json` has a
  stage-0 architect `merged-from:` entry. (`features-merge` guarantees this since
  v0.13.2, but verifying catches manual file surgery.)
