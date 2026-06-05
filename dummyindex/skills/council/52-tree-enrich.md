# Phase 4.5 — Tree enrichment (node abstracts)

Fill in the natural-language `abstract` on `tree.json` nodes that are still
deterministic stubs (`confidence: EXTRACTED`), so a future session's
PageIndex-style walk over `tree.json` reads real prose instead of
auto-generated stubs. This is **orthogonal to the per-feature council** — the
dev/architect/critics never read node abstracts; they feed *retrieval*. Run it
**after** Phase 4 and **before** Phase 5 reconcile (so any tree-derived index
picks the abstracts up).

**Skip entirely in mode `light`.**

## What the CLI gives you

```bash
dummyindex context enrich-plan <root>
```

Emits `.context/_enrich_plan.json`:

- `stats` — `total_nodes`, `stub_nodes`, `by_kind` (how many stubs per node kind).
- `batches` — coherent units of work:
  - one `structure` batch (kind `structure`): the project + directory nodes.
  - one `file_subtree` batch per file (kind `file_subtree`): the **file node itself,
    followed by that file's in-file symbols** (classes / functions / methods) — the
    long tail.
- `nodes` — every stub node with `node_id`, `kind`, `title`, `path`, `range`,
  `stub_abstract`, and `evidence_files` (the source file to read for grounding).
  Each node carries its `kind`, so you select what to enrich **by kind** across
  batches — the navigable skeleton a retrieval walk hits first is kinds
  `project` / `dir` / `file`.

## Scope by mode (cost control)

`enrich-plan` lists *every* stub, which on a large repo is the whole symbol
table. Do **not** enrich all of it by default — scope to the mode:

| Mode | What you enrich (by node `kind`) | Dispatch |
|---|---|---|
| `light` | nothing — skip this phase | — |
| `standard` (default) | the navigable skeleton — kinds `project` / `dir` / `file` (the `structure` batch + the head node of each `file_subtree`) | **one** architect subagent |
| `deep` | the skeleton **+** every in-file symbol (`class` / `function` / `method`) | architect for the skeleton; one dev (resolve via `dev-pick` for the file's feature) per `file_subtree` |

The skeleton (project → dirs → files) is what the tree walk reaches first, so
standard mode buys most of the retrieval benefit for one subagent's cost. Deep
mode additionally pays per source file for symbol-level abstracts.

## Procedure

1. **Plan.** Run `dummyindex context enrich-plan <root>`. If `stats.stub_nodes`
   is 0, there's nothing to do — skip to Phase 5.
2. **Select by kind, then dispatch (subagents author — you only conduct).**
   Filter `nodes` to the kinds in scope for the mode (standard: `project`/`dir`/`file`;
   deep: also `class`/`function`/`method`). Then dispatch the persona(s) from the
   table — in `standard`, **one** architect over the skeleton nodes; in `deep`,
   additionally **one dev per `file_subtree` batch** over that file's symbol nodes
   (resolve the dev via `dev-pick` for the file's feature). Read each persona's
   `subagent_type:` and apply the first-available fallback rule from `skill.md`.
   Give the subagent its node set (`node_id`, `title`, `path`, `range`,
   `stub_abstract`) and tell it to **read each node's `evidence_files`** and return
   a JSON object mapping `node_id` → a **one-line abstract** (≤ 120 chars) that says
   *what the node is and does*, grounded in the source. No speculation; if the
   evidence is thin, keep the stub's wording. Output contract: a single JSON object,
   nothing else.
3. **Apply.** Merge the subagents' JSON objects into one `{node_id: abstract}`
   mapping, `Write` it to a tmp file, then:
   ```bash
   dummyindex context enrich-apply <root> --from-json <tmp.json>
   ```
   It updates each node's `abstract` and flips `confidence: EXTRACTED → INFERRED`.
   Apply **per batch** in deep mode so partial progress survives an interrupted
   run (the command is idempotent — re-applying matching abstracts is a no-op).
4. **Reconcile mismatches.** `enrich-apply` prints any `node_id`s not found in
   `tree.json` (a typo in the subagent's output). Surface them; drop them from the
   mapping and re-run if needed. Then continue to Phase 5.

## What NOT to do

- ❌ Don't enrich every `file_subtree` in `standard` mode — that's a `deep`-mode cost.
- ❌ Don't author abstracts yourself — dispatch subagents (every word in `.context/`
  comes from a persona or Python; see `skill.md` "Final word").
- ❌ Don't run this before Phase 4 — it's retrieval-facing, not council input, and
  must land before Phase 5 reconcile.
- ❌ Don't write abstracts longer than a line — the tree TOC stays scannable.
