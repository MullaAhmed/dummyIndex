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
├── equipment.json            # equip toolkit manifest (written by `context equip apply`)
├── equipment-evals/          # per-tool eval suites (seeded by `equip apply`)
├── debt.md                   # technical-debt ledger (written by `context debt --write`)
├── config.json               # per-repo council preferences (mode, model, command_depths, reconcile_exclude, wired)
├── .gitattributes            # linguist-generated markers for heavy machine-layer JSON
└── .gitignore                # excludes cache/, _doc_backups/, and scratch artefacts
```

`proposals/<slug>/` and `audits/<slug>/` are **disposable per-task workspaces** — swept and deleted (never archived) by the context-hygiene GC (`/dummyindex-gc`). `debt.md` and every `equipment-evals/` suite only appear once the command that writes them has been run.

## `.context/features/`

The behavioral layer. Folder · file · feature · flow.

```
features/
├── INDEX.json                # machine-readable feature list (agents start here)
├── INDEX.md                  # human-readable table
├── HOW_TO_NAVIGATE.md        # how to walk features/ programmatically
├── symbol-graph.json         # raw NetworkX — communities, for tools that want everything
├── graph.json                # denormalized: folder/file/feature/flow nodes for the viewer
├── graph.html                # D3 viewer (human-facing visualization)
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

### `features/graph.json`

- Denormalized for the HTML viewer.
- 7 node kinds: `folder`, `file`, `class`, `function`, `method`, `feature`, `flow`.
- Edge relations:
  - `parent` — folder → folder (directory hierarchy).
  - `contains` — folder → file, file → class/function, class → method, feature → flow.
  - `touches` — feature → file, feature → symbol, flow → file.
- Class / function / method nodes carry `path` + `range` so the viewer's
  detail panel can cite a specific line. Surgical updates depend on this —
  pick a feature, see "Files · classes · methods" with `path:line`.
- The viewer hides symbol-kind nodes by default (kind-filter chips toggle
  them) since a 500-symbol repo would otherwise overwhelm the force layout.

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
