# Stage 1 — `/specify` (dev drafts spec.md + plan.md)

One author per feature. The dev is dispatched as the **stack specialist** for
the feature's primary domain. Produces `spec.md` (what) and `plan.md` (how).

## Inputs (per feature)

- `feature.json` — members, files, entry points, flow ids.
- Source files under `files` (sample the largest 8 + entry points if >15 files).
- `features/<id>/docs.md` if present — the doc-to-feature linker output.
- `conventions/*.md` for the repo.

## Step 1 — Resolve the stack specialist

```bash
dummyindex context dev-pick --feature <id>
```

Prints JSON: `{"persona_id": "...", "subagent_type": "...", "framework": "..."}`.

- `subagent_type` is one of `Backend Architect`, `Frontend Developer`,
  `Data Engineer`, `AI Engineer`, `Senior Developer` — dispatch the Task with
  this exact value.
- `framework` fills the `{{framework}}` slot in `agents/dev.md`.
- If dev-pick errors, fall back to `subagent_type: Senior Developer` (the
  frontmatter default in `agents/dev.md`).

## Step 2 — Dispatch one dev

1. Read `agents/dev.md`.
2. Substitute the `{{framework}}` slot with dev-pick's `framework`.
3. Fill the `{{framework_docs}}` slot via the Context7 protocol in
   `council/55-context7.md` — resolve the library ids for the framework + the
   libraries this feature actually imports, fetch focused docs, and paste the
   verbatim excerpts in. **If no Context7 MCP server is exposed (any `*context7*`
   namespace — see `council/55-context7.md`), leave the slot
   empty and fall back** — the dev reasons single-shot from the source. The
   `.context/` artifacts have the same shape either way.
4. Build the prompt: persona body (with both slots filled) + feature context
   (feature.json + source file list) + the doc-evidence directive verbatim.
5. Dispatch `Task` with dev-pick's `subagent_type`.

The dev writes `spec.md` + `plan.md` via `section-write` and logs completion.

## Doc-evidence directive (include verbatim)

> Catalogued prose docs carry `confidence` (high/medium/low) and `broken_refs`.
> Quote only `high`/`medium` after spot-checking each cited identifier against
> `map/symbols.json`. Treat `low` as historical context, never as authority. If
> a doc contradicts the code, the code wins — flag the conflict in the audit
> trail.

## Step 3 — Snapshot the draft

Before stage 2 runs, snapshot the dev's unrevised `plan.md` so the architect's
revision is diffable:

```bash
cp .context/features/<id>/plan.md .context/features/<id>/council/01-dev-draft.md
```

## Logging

Started before dispatch, complete after the dev writes back:

```bash
dummyindex context council-log --feature <id> --stage 1 --agent dev --status started
dummyindex context council-log --feature <id> --stage 1 --agent dev --status complete
```

## Skip logic

- `latest_status(<id>, stage=1, agent=dev) == complete` AND source hash
  unchanged → skip.
- Trivial features never reach this stage (see `filter-trivial.md`).

## Failure handling

If the dev returns `failed` or `spec.md`/`plan.md` are missing: log the failure,
surface to the user ("dev failed for <id>; re-run with `--recouncil <id>`"), and
move to the next feature. Stages 2/3 for this feature don't run without a plan.

## Output

- `features/<id>/spec.md`, `features/<id>/plan.md`.
- `features/<id>/council/01-dev-draft.md` (the snapshot).
- Log entries.

Next → `30-plan.md`.
