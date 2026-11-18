# Phase 4.5 — Tree enrichment (node abstracts)

Fill in the natural-language `abstract` on `tree.json` nodes that are still deterministic stubs (`confidence: EXTRACTED`). A future session walks `tree.json` in the PageIndex style and reads real prose instead of auto-generated stubs. This phase is **orthogonal to the per-feature council**. The dev, architect, and critics never read node abstracts, and they feed *retrieval*. Run it **after** Phase 4 and **before** Phase 5 reconcile. Then any tree-derived index picks up the abstracts.

**On by default in every mode**, including `light` — the caller never has to ask for it. Skip only when the run passed `--no-tree-enrich`.

## What the CLI gives you

```bash
dummyindex context enrich-plan <root>
```

Emits `.context/cache/_enrich_plan.json`:

- `stats` — `total_nodes`, `stub_nodes`, `by_kind` (how many stubs per node kind).
- `batches` — coherent units of work:
  - one `structure` batch (kind `structure`): the project + directory nodes.
  - one `file_subtree` batch per file (kind `file_subtree`): the file node itself, then its in-file symbols (classes, functions, methods). It is the long tail.
- `nodes` — every stub node with `node_id`, `kind`, `title`, `path`, `range`, `stub_abstract`, and `evidence_files` (the source file to read for grounding).
  Each node carries its `kind`. Select what to enrich **by kind** across batches. The navigable skeleton is the kinds `project` / `dir` / `file`. A retrieval walk hits that skeleton first.

## Scope by mode (cost control)

`enrich-plan` lists *every* stub. On a large repo, that list is the whole symbol table. Do **not** enrich all of it by default. Scope the work to the mode:

| Mode | What you enrich (by node `kind`) | Dispatch |
|---|---|---|
| `light` | nothing — skip this phase | — |
| `standard` (default) | the navigable skeleton — kinds `project` / `dir` / `file` (the `structure` batch + the head node of each `file_subtree`) | **one** architect subagent |
| `deep` | the skeleton **+** every in-file symbol (`class` / `function` / `method`) | architect for the skeleton; one dev (resolve via `dev-pick` for the file's feature) per `file_subtree` |

The skeleton (project → dirs → files) is what the tree walk reaches first. Standard mode gives most of the retrieval benefit at the cost of one subagent. Deep mode also pays per source file for symbol-level abstracts.

## Procedure

1. **Plan.** Run `dummyindex context enrich-plan <root>`. If `stats.stub_nodes` is 0, there is nothing to do. Skip to Phase 5.
2. **Select by kind, then dispatch (subagents author — you only conduct).**

   Filter `nodes` to the kinds in scope for the mode. Standard mode uses `project`/`dir`/`file`. Deep mode adds `class`/`function`/`method`.

   Dispatch the persona(s) from the table. In `standard`, dispatch **one** architect over the skeleton nodes. In `deep`, also dispatch **one dev per `file_subtree` batch** over that file's symbol nodes. Resolve the dev via `dev-pick` for the file's feature. Read each persona's `subagent_type:` and apply the first-available fallback rule from `skill.md`.

   Give the subagent its node set (`node_id`, `title`, `path`, `range`, `stub_abstract`). Tell it to **read each node's `evidence_files`**. It returns a JSON object that maps `node_id` to a **one-line abstract** (≤ 120 chars).

   The abstract says *what the node is and does*, grounded in the source. No speculation. If the evidence is thin, keep the stub's wording. Output contract: a single JSON object, nothing else.
3. **Apply.** Merge the subagents' JSON objects into one `{node_id: abstract}` mapping. `Write` it to a tmp file, then:
   ```bash
   dummyindex context enrich-apply <root> --from-json <tmp.json>
   ```
   It updates each node's `abstract` and flips `confidence: EXTRACTED → INFERRED`. Apply **per batch** in deep mode, so partial progress survives an interrupted run. The command is idempotent. Re-applying matching abstracts is a no-op.
4. **Reconcile mismatches.** `enrich-apply` prints any `node_id`s not found in `tree.json`. That means a typo in the subagent's output. Surface them. Drop them from the mapping and re-run if needed. Then continue to Phase 5.

## What NOT to do

- ❌ Do not enrich every `file_subtree` in `standard` mode. That is a `deep`-mode cost.
- ❌ Do not author abstracts yourself. Dispatch subagents. Every word in `.context/` comes from a persona or Python. See `skill.md` "Final word".
- ❌ Do not run this before Phase 4. It is retrieval-facing, not council input, and it must land before Phase 5 reconcile.
- ❌ Do not write abstracts longer than a line. The tree TOC stays scannable.
