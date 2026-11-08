# How to use `.context/`

Canonical machine-readable context for AI coding agents (Claude Code, Cursor, Codex, Aider). dummyIndex generates it. The deterministic backbone (map, tree, naming, source-docs) refreshes via `dummyindex context rebuild --changed`. That preserves curated feature docs. It never re-clusters an enriched index.

Curated content (feature `spec.md`/`plan.md`/`concerns.md`, conventions) updates through reconcile. `dummyindex context reconcile` reports the delta: read-only, **writes nothing**. Then run `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. The skill places new files and re-enriches drifted features. Finish with `dummyindex context reconcile-stamp` to advance the commit anchor.

Bounded retrieval: `dummyindex context query` and `dummyindex context graph`. Default cap is 16,000 bytes. The symbol graph may be a manifest over `symbol-graph.parts/`. Use the shared reader or graph CLI, not plain node-link JSON. Collision-affected IDs change when a new conflicting definition enters the scan. Unresolved references list candidates.

## Read this folder *first* for any non-trivial work

Before grepping, reading files, or asking the user for context, consult these in order:

| Question | Look at |
|---|---|
| "What is this project?" | `PROJECT.md` |
| "What's the layout?" | `architecture/overview.md`, then `tree.json` |
| "How does feature `Z` work?" / "What's the flow when…?" | **Start at `features/INDEX.json`** (entries live under a top-level `features` array, each keyed **`feature_id`** — *not* `id` — with `name`/`summary` plus `member_count`/`file_count`/`entry_point_count`/`flow_count`) — then `features/<feature_id>/feature.json` (raw `members`/`files`/`entry_points`/`flow_ids` lists, no `*_count` keys) + `features/<feature_id>/spec.md`. Drill into `plan.md` (implementation) / `concerns.md` (risks). See `features/HOW_TO_NAVIGATE.md`. |
| "Where is `X` defined?" | `map/symbols.json` — every class / function / method has `path` + `range` |
| "What files contain `Y`?" | `map/files.json` — full file inventory with language + size |
| "How does `X` relate to `Y`?" / "Communities / hidden dependencies?" | `dummyindex context graph` queries the symbol graph (`contains`, `method`, `inherits`, `imports`, `calls` edges + Leiden communities; legacy JSON or bounded shards). Ambiguous definitions return cited candidates. |
| "What's the naming style?" | `conventions/naming.md` — honor this when adding new code |
| "How is code grouped into folders?" | `conventions/folder-organization.md` |
| "What patterns / idioms does this repo use?" | `conventions/coding-practices.md` |
| "How are tests written here?" | `conventions/testing.md` |
| "How does this repo talk to its database?" | `conventions/data-access.md` |
| "How do I add / change / fix X?" | `playbooks/` — task-specific recipes |
| "How do I retire stale proposals/audits?" | `playbooks/gc-context.md` — the context-hygiene GC sweep (`/dummyindex-gc` on Claude, `$dummyindex-gc` on Codex) |

## Retrieval principle: walk the tree, don't grep

This index uses **PageIndex-style reasoning-based retrieval**. Procedure for any non-trivial question:

1. **(Optional fast first cut)** Run `dummyindex context query "<task or question>"`. It scores each feature by token overlap with its name, summary, files and symbols. It prints top-K with cited markdown excerpts: a deterministic ranked shortlist, no LLM. Use it to pick features to open, then keep reasoning. Add `--top-k N` to widen, `--json` for machine output.
2. Read `features/INDEX.json`, the table of contents. `coverage.json` accounts for indexed files, file-only navigation, unassigned source and excluded paths with reasons. It also records source ownership, extraction status and identity ambiguities. Query output caps at 16,000 UTF-8 bytes. Set `--max-bytes N` to bound it.
3. Reason over names and summaries. Pick 1–3 features the task touches. The `query` ranking is a hint, not the verdict. Reason over the TOC yourself.
4. Read the chosen `feature.json` and `spec.md`.
5. Drill into `plan.md` (implementation) and `concerns.md` (risks).
6. Follow `path:range` citations to source to verify.

**Never grep the source tree first.** The tree is already mapped. Reasoning over the map beats string-matching source.

## Concrete examples

**Asked to add a new feature?** Read `playbooks/add-feature.md`. Walks through: check duplicates in `map/symbols.json`; mirror an existing feature's structure (find via `tree.json`); honor `conventions/naming.md`; write tests first.

**Asked to find or modify something specific?** Don't grep blindly. `map/symbols.json` lists every symbol's `path:range`. Load it once, find the match, jump to the code.

**Asked an architectural question?** Start with `PROJECT.md` and `architecture/overview.md`. Most questions answer themselves at that level. Drill into `tree.json` only for finer detail.

**Doing a rename or refactor?** `map/symbols.json` lists every site to consider. Combine with conventional grep for callers.

## When the index is wrong

The code is the source of truth. If the index disagrees with a file, trust the file. Then fix the index by the path that matches what is stale:

- **Stale deterministic artefacts** (moved or renamed symbol, new or deleted file, out-of-date `map/` or `tree.json`): run `dummyindex context rebuild --changed`. It re-hashes every source file and refreshes only changed deterministic bits. On a curated index it **preserves feature taxonomy and enrichment**. It does **not** touch `features/<id>/*.md` or re-cluster. It never undoes curated work.
- **Stale or missing feature docs** (drifted spec, plan or concerns; new code in no feature). `rebuild --changed` does **not** fix these. Edit the doc in-session by hand (see Conventions for agents). Or run reconcile: `dummyindex context reconcile` shows the delta. It is read-only and **writes nothing**. It does not re-cluster, so it is safe any time. Then `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex places and enriches. Finish with `dummyindex context reconcile-stamp`.
- **When your explicit instruction contradicts a `.context/` spec or plan, you win.** Code and user intent are the source of truth. Note the divergence and proceed. Flag it so a later reconcile folds it in.

## Feature-oriented navigation

`features/` is the **behavioral** view. `tree.json` is the structural view. Start at `features/INDEX.json` when asked how something works or what a flow does. It points at per-feature `feature.json` and `flows/<flow-id>.json`. Answer without grepping. Folder names get renamed during enrichment, but `feature_id` stays stable. Always navigate by ID.

## What gets committed and why

Everything in `.context/` is **meant to be committed**, except `cache/` and the scratch artefacts listed in `.context/.gitignore`. A fresh clone must navigate this index without the CLI. The reconcile loop anchors on committed state.

Heavy machine-layer artefacts (`tree.json`, `map/files.json`, `map/symbols.json`, `features/symbol-graph.json`, `features/graph.json`, `features/graph.html`) are marked `linguist-generated` in the managed `.context/.gitattributes`. GitHub collapses their large rebuild diffs in PR review. Local `git diff` and merges stay untouched.

The committed layout, top-down:

| Path | What it is |
|---|---|
| `PROJECT.md`, `INDEX.md`, `architecture/` | project overview + entry index |
| `map/`, `tree.json`, `source-docs/` | deterministic backbone (regenerated by `rebuild --changed`) |
| `features/` | curated behavioral view (per-feature `spec.md`/`plan.md`/`concerns.md`) |
| `conventions/`, `playbooks/` | authored house style + task recipes |
| `proposals/<slug>/`, `audits/<slug>/` | **generated per-task workspaces**, swept by the hygiene GC (below) |
| `gc/state.json` | **committed** GC commit anchor (`{"anchor": sha}`); the per-session nudge memo lives in gitignored `cache/`, never here |
| `gc/evolution.jsonl`, `gc/evolve/<run>/` | **committed** evolve loop state (append-only decision history + per-run harvest/candidates/staged artifacts) written by `context evolve`; CLI-owned, never hand-edited |
| `fleet/run-<id>/` | **committed** fleet-run artifacts (`RUN-MANIFEST.md` first, `state.json` last) written by `context fleet init`; resumed via the CLI verbs, never hand-edited |
| `cache/`, `_doc_backups/` | per-machine scratch, **gitignored**, never referenced |

## Context-hygiene GC (lifecycle of generated docs)

dummyindex generates per-task workspaces: `.context/proposals/<slug>/` (plan artifacts) and `.context/audits/<slug>/` (argue-and-audit panels). Workspaces are **disposable**. Superseded plans, abandoned scaffolds and long-fixed audits mislead the next agent. The **context-hygiene GC** retires them.

**Generated docs are GC'd: deleted, not archived.** No `_archive/` tier going forward. The old `proposals/_archive/` convention is itself a delete candidate. Disposition is decisive deletion. Distill nothing. Keep nothing around in case. A `done`-but-still-relevant plan stays. Only genuinely **stale / superseded / dead / no-longer-useful** docs go.

**How the sweep runs.** It is an LLM council step: `/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex. Subagents walk candidate docs PageIndex-style (via `dummyindex context query`). They judge each against current code and work in flight, then propose a delete-list. Deletion is *always* user-confirmed: nothing is deleted until you confirm. Dead **docs** are deleted directly. **Trivially-dead code** is a 0-caller private symbol that passes every exclusion guard. It takes the normal implementer and tester path, and only if the full suite stays green. Anything broader routes to a new proposal, never auto-removed. GC never edits or removes source code directly.

**When it's nudged.** A commit-count throttle, not a clock. When >= N commits (default 10) land since the last GC anchor, Claude's SessionStart hook emits a one-line `N commits since last hygiene sweep — run /dummyindex-gc` nudge. Codex installs no dummyindex GC hook. Invoke `$dummyindex-gc` explicitly. The sweep stamps a fresh anchor to reset the counter. Either skill runs on demand any time.

**Deterministic plumbing:** `dummyindex context gc`, four verbs. Order of use: see `playbooks/gc-context.md`.

| Verb | What it does |
|---|---|
| `gc status [--json]` | read-only sweep report — every candidate doc with its signals, plus the throttle state (`commits_since` / `anchor` / `threshold` / `should_signal`). The skill and Claude's SessionStart hook consume this. |
| `gc delete --kind proposal\|audit (--slug S \| --path P)` | delete **one** workspace dir. A dry-run without `--yes` (deletes nothing); refuses a sentinel/escaping target and an untracked workspace (needs `--allow-untracked`). Never touches source code. |
| `gc stamp [--to SHA]` | advance the committed GC anchor in `gc/state.json` to HEAD (off-git no-op). |
| `gc signal` | Claude's SessionStart throttle probe. Prints the nudge iff over threshold and not already signalled this session. |

## CI, linting & secret scanners

- `sha256` fields in `map/files.json` and `source-docs/INDEX.json` are **content fingerprints** of source files, not credentials. Entropy scanners (e.g. detect-secrets' "Hex High Entropy String") flag them as false positives.
- **Don't blanket-exclude `.context/` from every pre-commit hook.** You lose JSON validity, merge-conflict and large-file checks on the index. Scope the exclusion to the entropy scanner only. Example for detect-secrets:

  ```yaml
  - id: detect-secrets
    exclude: ^\\.context/(map/|source-docs/INDEX\\.json)
  ```

  Or audit the hits once into your `.secrets.baseline` allowlist.
- Generated files end with one newline and no trailing whitespace. Whitespace fixers pass without rewrites.

## Conventions for agents

- **Two layers, two rules.** Deterministic artefacts (`map/files.json`, `map/symbols.json`, `tree.json`, `conventions/naming.md`, `source-docs/INDEX.json`, `features/*` indexes and graphs) regenerate on `rebuild --changed`. **Don't hand-edit them.** Your edits get overwritten. The curated layer (`features/<id>/spec.md`, `plan.md`, `concerns.md`, and authored `conventions/*.md` except `naming.md`) is council-owned. Edit it in-session to clear drift. `rebuild --changed` preserves it. Hand-edit a feature doc to fix it. Never hand-edit a generated map or index.
- `cache/` is per-machine and gitignored. Never reference it.
- Always check `conventions/naming.md` before naming a new symbol or file.
