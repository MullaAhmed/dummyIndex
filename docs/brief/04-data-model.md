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
├── features/                 # the behavioral view (see below)
└── .gitignore                # excludes cache/
```

## `.context/features/`

The behavioral layer. Folder · file · feature · flow.

```
features/
├── INDEX.json                # machine-readable feature list (agents start here)
├── INDEX.md                  # human-readable table
├── HOW_TO_NAVIGATE.md        # how to walk features/ programmatically
├── COMMUNITIES.md            # community + god-node report (was graph/GRAPH_REPORT.md)
├── symbol-graph.json         # raw NetworkX (was graph/graph.json) — for tools that want everything
├── graph.json                # denormalized: folder/file/feature/flow nodes for the viewer
├── graph.html                # D3 viewer (human-facing visualization)
└── <feature-id>/
    ├── feature.json          # canonical machine description
    ├── README.md             # chairman's synthesized overview
    ├── architecture.md       # architect's section
    ├── implementation.md     # senior developer's section
    ├── data-model.md         # database engineer's section
    ├── security.md           # security analyst's section
    ├── product.md            # product manager's section
    ├── council/              # full audit trail
    │   ├── 01-architect.md
    │   ├── 02-senior-developer.md
    │   ├── 03-database-engineer.md
    │   ├── 04-security-analyst.md
    │   ├── 05-product-manager.md
    │   ├── 10-reviews.md         # cross-review matrix (stage 2)
    │   ├── 20-chairman.md        # synthesis log + open questions
    │   └── _council-log.json     # resumption state
    └── flows/
        ├── <flow-id>.json    # ordered call sequence with path:range per step
        └── <flow-id>.md      # plain-language narrative
```

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
- 4 node kinds: `folder`, `file`, `feature`, `flow`.
- 3 edge relations: `parent` (folder → folder), `contains` (folder → file, feature → flow), `touches` (feature/flow → file).

### `features/symbol-graph.json`

- The raw NetworkX node-link from layer 1.
- Every symbol, every call, with Leiden community ids.
- The structural source from which features are derived.

## Generated vs. hand-edited

- `.context/` is **fully generated**. Never edit by hand.
- All edits go through CLI commands (atomic, idempotent).
- A fresh `rebuild` regenerates everything except the council audit trail (cache).
- The council audit trail (`features/<id>/council/`) survives rebuilds unless the feature's content hash changed.

## Cache

- `.context/cache/` — per-machine, gitignored.
- Stores AST extraction by content hash.
- Survives across rebuilds. Path-independent.
- Never reference cache files in agent answers.
