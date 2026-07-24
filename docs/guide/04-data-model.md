# 04 — `.context/` data model

What lives in the folder. Every file has a purpose.

## Top-level layout

```
.context/
├── HOW_TO_USE.md             # agent-facing navigation guide (first read)
├── PROJECT.md                # one-page project summary
├── INDEX.md                  # human TOC of every file in this folder
├── meta.json                 # schema version, generated_at, file/symbol counts
├── tree.json                 # hierarchy: project → dir → file → class → method
├── map/
│   ├── files.json            # every file: path, language, size, hash
│   └── symbols.json          # every symbol: path, range, parent, kind
├── conventions/
│   ├── naming.md             # statistically derived naming rules (human-readable)
│   └── naming.json           # machine-readable form
├── architecture/
│   └── overview.md           # top-level layout + role hints
├── playbooks/                # task-specific recipes
│   ├── add-feature.md
│   ├── add-endpoint.md
│   ├── add-migration.md
│   ├── fix-bug.md
│   └── refactor.md
├── source-docs/              # catalog of existing prose docs (see below)
│   ├── INDEX.json            # machine-readable: per-doc confidence + broken_refs
│   └── INDEX.md              # human-readable with advisory banner
├── features/                 # the behavioral view (see below)
├── session-memory/           # cross-session memory tiers (seeded by ingest; agent-maintained, never regenerated)
├── proposals/                # generated per-task workspaces, one <slug>/ each (written by `context propose`)
├── audits/                   # generated argue-and-audit workspaces, one <slug>/ each
├── gc/
│   └── state.json            # committed GC commit anchor ({"anchor": sha}) — the only file under gc/
├── equipment.json            # optional Claude equip manifest (`context equip apply`)
├── equipment-evals/          # optional Claude equip eval suites
├── debt.md                   # technical-debt ledger (written by `context debt --write`)
├── config.json               # per-repo council preferences (mode, model, command_depths, reconcile_exclude, wired)
├── .gitattributes            # linguist-generated markers for heavy machine-layer JSON
└── .gitignore                # excludes cache/, _doc_backups/, and scratch artefacts
```

`proposals/<slug>/` and `audits/<slug>/` are **disposable per-task workspaces** — swept and deleted (never archived) by the context-hygiene GC (`/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex). `debt.md` and every `equipment-evals/` suite only appear once the command that writes them has been run.

## `.context/features/`

The behavioral layer. Folder · file · feature · flow.

```
features/
├── INDEX.json                # machine-readable feature list (agents start here)
├── INDEX.md                  # human-readable table
├── HOW_TO_NAVIGATE.md        # how to walk features/ programmatically
├── symbol-graph.json         # raw NetworkX — communities, for tools that want everything
├── graph-communities.json    # one card per Leiden community (stable slug, top members by PageRank)
├── seed-rank.json            # personalized-PageRank shortlist that drives the seed's selection
├── graph.json                # the curated codebase scan (schema v2)
├── graph.html                # self-contained viewer over graph.json (3 tiers: map / communities / symbols)
└── <feature-id>/
    ├── feature.json          # canonical machine description
    ├── spec.md               # WHAT — intent, contracts, user-visible behavior (dev)
    ├── plan.md               # HOW  — architecture, file map, decisions (dev → architect)
    ├── concerns.md           # RISKS — data, security, product surface (critics)
    ├── docs.md               # pointer list to source-docs matching this feature (optional)
    ├── council/              # audit trail
    │   ├── _council-log.json    # resumption state
    │   ├── 01-dev-draft.md      # dev's unrevised plan.md
    │   ├── 02-architect-notes.md # what the architect changed in plan.md, with rationale
    │   └── 10-critiques.md      # raw per-critic findings before merge into concerns.md
    └── flows/
        ├── <flow-id>.json    # ordered call sequence with path:range per step
        └── <flow-id>.md      # plain-language narrative
```

Three layered artifacts, three jobs. No essay redundancy across files. An agent reads the level its task needs: onboarding stops at `spec.md`, refactor reads `plan.md`, review reads `concerns.md`.

## Schemas — the load-bearing JSON

### `tree.json`

- `schema_version`, `root` (recursive `TreeNode`).
- Each node: `node_id`, `kind` (project/dir/file/class/function/method), `title`, `path`, `range`, `abstract`, `confidence`, `children`.
- Walked top-down by agents.

### `map/symbols.json`

- Flat list. Every class, function, method.
- Per symbol: `node_id`, `kind`, `name`, `path`, `range` (start_line, end_line), `parent_id`.
- The "where is X defined?" answer.

### `map/files.json`

- Flat list. Every code file.
- Per file: `path`, `language`, `size_bytes`, `loc`, `sha256`.

### `features/INDEX.json`

- Flat list of features.
- Per feature: `feature_id`, `name`, `path`, `member_count`, `file_count`, `entry_point_count`, `flow_count`, `confidence`.

### `features/<id>/feature.json`

- `feature_id`, `kind`, `name`, `summary`.
- `members` (symbol node_ids).
- `files` (paths).
- `entry_points` (symbol node_ids).
- `flow_ids` (pointers into flows/).
- `confidence` — flips `EXTRACTED → INFERRED` once the council touches it.

### `features/<id>/flows/<flow-id>.json`

- `flow_id`, `feature_id`, `entry_point`, `entry_point_label`, `entry_point_path`.
- `steps[]` — ordered. Each step: `depth`, `node_id`, `label`, `path`, `range`.
- `files[]` — unique files touched.
- `confidence`.

### `features/graph.json` — the codebase scan

The human-facing map: **how this codebase works and how it uses AI**, on one
screen. Schema v2. Capped at 120 nodes / 240 edges on purpose — aim for 40–80
on a substantial repo; the cap is the feature, not a limitation. (v1
denormalized the whole extraction into this
file: folder → file → class → method → feature → flow, ~4k nodes on a
mid-size repo. Complete, and unreadable. Per-symbol data did not go anywhere —
it lives in `map/symbols.json` and `features/symbol-graph.json`, which is what
agents query.)

- `project` — `name`, `slug`, optional `tagline` / `iconDomain` / `date`.
- `stats` — `agents`, `models`, `tools`, `integrations`.
- `topModels` / `topTools` / `topIntegrations` — headline chips (≤ 3 / 10 / 10).
- `graph.nodes[]` — `id`, `label` (≤ 28), `kind`, and optional `sub` (≤ 40),
  `group` (≤ 24), `domain` (bare favicon host), `detail` (≤ 200),
  `sourceRef` (`path[:line]`, ≤ 120), `symbolRef` (a `symbol-graph.json` node
  id or a `graph-communities.json` slug, ≤ 120 — pins the box to the
  extraction layer; `scan-check` resolves it), and `evidence`
  (`EXTRACTED` = survived the seed verbatim, `INFERRED` = council judgment —
  the viewer renders the two distinctly).
- `graph.edges[]` — `from`, `to`, optional `kind` and `label` (≤ 24).
- `confidence` — `EXTRACTED` (deterministic seed) or `INFERRED` (authored).

**Node kinds** (closed alphabet, `ScanNodeKind`): `entry`, `cron`, `agent`,
`model`, `tool`, `service`, `store`, `external`.
**Edge kinds** (`ScanEdgeKind`): `calls`, `reads`, `writes`, `triggers`.

Business logic goes on the **edges** — `{"from": "billing", "to": "stripe",
"kind": "writes", "label": "charges on trial end"}` says more than either box
does.

**Two-stage, like `spec.md`.** Ingest writes a deterministic seed — but a
**ranked shortlist**, not a dump: personalized PageRank over
`symbol-graph.json` (entry points seeded hardest, test files down-weighted,
shortlist persisted to `seed-rank.json`) drives which features and entry
points the seed keeps and in what order, each pinned with `symbolRef` +
`evidence: EXTRACTED`. It knows the shape of the code and nothing about its
meaning, and it cannot see the AI surface at all. The codebase-scan council
stage (`council/58-codebase-scan.md`) **edits the shortlist** — rename, merge,
group by `graph-communities.json` cards, promote the AI surface — and flips
`confidence` to `INFERRED`, which is what makes `refresh-indexes` preserve it
instead of regenerating it. Validate with `dummyindex context scan-check`.

### `features/graph-communities.json` + `features/seed-rank.json`

Deterministic backbone (regenerated by `rebuild --changed`, like `map/`):

- `graph-communities.json` — one card per Leiden community of the symbol
  graph: **stable slug** (dominant feature + top member, never the raw Leiden
  int, which renumbers between runs), `size`, owning `feature`, one-line
  `summary`, top `members` by PageRank with `path:line`. The mid-tier between
  the curated map and the full symbol graph; the scan's `group` scaffold; the
  viewer's tier-2 overview.
- `seed-rank.json` — the PageRank shortlist (`{id, score}`, descending) the
  seed and the viewer's expansion index are built from.

Query the backbone directly with `dummyindex context graph <verb>`
(`callers-of`, `callees-of`, `impact`, `path`, `neighbors`, `dead-code`,
`community`) — bounded, `file:line`-cited answers from
`symbol-graph.json`, no grepping.

### `features/symbol-graph.json`

- The raw NetworkX node-link from layer 1.
- Every symbol, every call, with Leiden community ids.
- The structural source from which features are derived.

### `source-docs/INDEX.json`

- Catalog of existing prose docs found in the repo (or pointed at via `--docs PATH`).
- Per-doc `DocEntry`:
  - `path` — repo-relative POSIX path (or absolute for external docs).
  - `abs_path` — absolute path on disk (audit trail).
  - `doc_type` — `markdown` / `rst` / `pdf` / `html` / `docx` / `xlsx` / `text` / `other`.
  - `title`, `headings[]` — H1 + H2/H1 list (first H1 is the title).
  - `sha256`, `size_bytes`, `mtime` — fingerprint + freshness.
  - `age_delta_seconds` — `newest_code_mtime - doc.mtime` (positive = doc older than newest code; null when no code).
  - `age_bucket` — `fresh` / `recent` / `aging` / `stale` / `old` / `unknown`.
  - `referenced_count` — backticked code-shaped tokens parsed out of the doc.
  - `broken_refs[]` — those that don't match `map/symbols.json` or `map/files.json`. **The strongest staleness signal.**
  - `broken_ratio` — `len(broken_refs) / referenced_count`.
  - `confidence` — `high` (≤10% broken, fresh) / `medium` / `low` (≥40% broken with ≥4 broken refs, or stale/old).
  - `is_external` — `true` when the doc came from a `--docs PATH` outside the repo.
  - `source_root` — which discovery root produced this entry.

- Top-level: `schema_version`, `generated_at`, `repo_root`, `default_discovery_used`, `extra_doc_roots[]`, `doc_count`, `by_confidence` (counts), `docs[]`.

### `features/<id>/docs.md`

- Optional. Written only when source-docs catalog entries reference one of the feature's files or symbols.
- Pointer list (not a content copy). Each line links to the catalog entry, names the match reason (`path:`, `symbol:`, `title`), and surfaces broken refs from the catalog.
- The canonical confidence + staleness stays in `source-docs/INDEX.md`; this file just routes the council to relevant prose.

## Generated vs. hand-edited

`.context/` has **two layers, two rules**:

- **Deterministic backbone** — `map/files.json`, `map/symbols.json`, `tree.json`, `conventions/naming.md`, `source-docs/INDEX.json`, and the `features/*` indexes/graphs. Regenerated by `rebuild --changed`; **don't hand-edit them** — your edits are overwritten.
- **Curated layer** — `features/<id>/spec.md`/`plan.md`/`concerns.md` and the authored `conventions/*.md` (everything except `naming.md`). Council-owned and **edited in-session** to clear drift; `rebuild --changed` preserves it.

- `rebuild --changed` re-hashes source and refreshes only the changed deterministic bits — it does **not** re-cluster or touch `features/<id>/*.md`.
- The council audit trail (`features/<id>/council/`) survives rebuilds unless the feature's content hash changed.

## Cache

- `.context/cache/` — per-machine, gitignored.
- Stores AST extraction by content hash.
- Survives across rebuilds. Path-independent.
- Never reference cache files in agent answers.
